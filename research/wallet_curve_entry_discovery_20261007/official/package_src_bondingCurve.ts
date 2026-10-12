import { NATIVE_MINT_2022 } from "@solana/spl-token";
import { PublicKey } from "@solana/web3.js";
import BN from "bn.js";

import {
  CurveDepthExceededError,
  QuoteBondingCurveNotEligibleError,
  QuoteCurveAwaitingMigrationError,
  QuoteReservesOutOfRangeError,
  UnsupportedQuoteMintError,
} from "./errors";
import { computeFeesBps, getFee, ONE_BILLION_SUPPLY } from "./fees";
import { isLegacyQuoteMint } from "./pda";
import { BondingCurve, FeeConfig, Global, QuoteControl } from "./state";

/**
 * The `virtualQuoteReserves` a new curve quoted in `quoteMint` starts from,
 * the way `create_v2` seeds it: SOL (WSOL or the zero key) from
 * `Global.initialVirtualSolReserves`, a mint whitelisted on `Global` from
 * `Global.initialVirtualQuoteReserves` (even when quote control lists it too),
 * and a mint admitted through quote control from its entry. The Token-2022
 * native mint always throws `UnsupportedQuoteMintError`: `create_v2` rejects
 * it before consulting either list.
 *
 * @param quoteControl - The decoded `QuoteControl` PDA, or `null` when the
 * account does not exist yet (an empty list). Pass it whenever the mint may
 * be a quote-control mint: a mint in neither list then throws
 * `UnsupportedQuoteMintError`, as `create_v2` would reject it. When omitted,
 * an unlisted mint falls back to `Global.initialVirtualQuoteReserves` — what
 * callers that predate quote control always got — and quote-control mints
 * are seeded wrong.
 * @param pumpQuote - When `quoteMint` is a pump coin listed nowhere: its
 * curve (and pool once migrated), from which `create_v2` derives the seed
 * (`pumpQuoteReserves`).
 */
export function initialVirtualQuoteReservesFor(
  global: Global,
  quoteMint: PublicKey,
  quoteControl?: QuoteControl | null,
  pumpQuote?: PumpQuoteCurve,
): BN {
  if (isLegacyQuoteMint(quoteMint)) {
    return global.initialVirtualSolReserves;
  }

  // Checked before either list, as `create_v2` does: pump-fees treats this
  // key as SOL, but it cannot quote a curve whichever list admits it.
  if (quoteMint.equals(NATIVE_MINT_2022)) {
    throw new UnsupportedQuoteMintError(quoteMint);
  }

  // `quoteMint` is non-zero here, so an empty (zero-key) whitelist slot can
  // never match.
  if (global.whitelistedQuoteMints.some((mint) => mint.equals(quoteMint))) {
    return global.initialVirtualQuoteReserves;
  }

  const entry = quoteControl?.mints.find((candidate) =>
    candidate.mint.equals(quoteMint),
  );
  if (entry) {
    return entry.initialVirtualQuoteReserves;
  }

  if (pumpQuote) {
    if (!pumpQuote.mint.equals(quoteMint)) {
      throw new Error(
        `pumpQuote is for ${pumpQuote.mint.toBase58()}, not the quote mint ${quoteMint.toBase58()}`,
      );
    }
    return pumpQuoteReserves(global, pumpQuote, quoteControl)
      .virtualQuoteReserves;
  }

  if (quoteControl !== undefined) {
    throw new UnsupportedQuoteMintError(quoteMint);
  }

  return global.initialVirtualQuoteReserves;
}

/**
 * A pump coin Q offered as a `create_v2` quote mint (listed neither on
 * `Global` nor in quote control): what the program reads to admit it and
 * seed the new curve.
 */
export interface PumpQuoteCurve {
  /** Q's mint. */
  mint: PublicKey;
  /** Q's decoded bonding curve. */
  bondingCurve: BondingCurve;
  /** Q's live mint supply. */
  mintSupply: BN;
  /**
   * Once Q's curve has migrated: its canonical pool's base vault balance,
   * quote vault balance and `Pool.virtualQuoteReserves` (may be negative).
   */
  pool?: { baseReserves: BN; quoteReserves: BN; virtualQuoteReserves: BN };
  /**
   * The `QuoteControl` PDA as fetched with Q (`null` when it does not exist):
   * a depth-0 Q quoted in a quote-control mint seeds from its entry. Used
   * when the caller passes no `quoteControl` of its own.
   */
  quoteControl?: QuoteControl | null;
}

const U64_MAX = new BN("18446744073709551615");

/** pump `BondingCurve::is_migrated`: every reserve zeroed by the migration. */
export function isBondingCurveMigrated(bondingCurve: BondingCurve): boolean {
  return (
    bondingCurve.realQuoteReserves.isZero() &&
    bondingCurve.virtualQuoteReserves.isZero() &&
    bondingCurve.realTokenReserves.isZero() &&
    bondingCurve.virtualTokenReserves.isZero()
  );
}

// What a fresh curve in Q's own quote would be seeded with (depth-0 Q), or
// Q's own starting reserves (deeper Q).
function pumpQuoteTarget(
  global: Global,
  quote: PumpQuoteCurve,
  quoteControl: QuoteControl | null,
): BN {
  const curve = quote.bondingCurve;
  if (curve.depth > 0) {
    return curve.initialVirtualQuoteReserves;
  }
  if (curve.quoteMint.equals(PublicKey.default)) {
    return global.initialVirtualSolReserves;
  }
  if (global.whitelistedQuoteMints.some((m) => m.equals(curve.quoteMint))) {
    return global.initialVirtualQuoteReserves;
  }
  const entry = quoteControl?.mints.find((candidate) =>
    candidate.mint.equals(curve.quoteMint),
  );
  if (!entry) {
    throw new QuoteBondingCurveNotEligibleError(quote.mint);
  }
  return entry.initialVirtualQuoteReserves;
}

/**
 * The `virtualQuoteReserves` and `depth` `create_v2` gives a coin quoted in
 * pump coin Q, with the program's admission checks: `depth` is `Q.depth + 1`
 * and must not exceed `global.maxCurveDepth`, Q must not be mayhem mode, and
 * the seed is Q's price applied to a reference seed. Throws the typed error
 * the program's refusal maps to (`CurveDepthExceededError`,
 * `QuoteBondingCurveNotEligibleError`, `QuoteCurveAwaitingMigrationError`,
 * `QuoteReservesOutOfRangeError`).
 *
 * @param quoteControl - The decoded `QuoteControl` PDA, or `null` when it
 *   does not exist; consulted for a depth-0 Q's own quote. Omitted, the one
 *   fetched with Q (`quote.quoteControl`) is used.
 */
export function pumpQuoteReserves(
  global: Global,
  quote: PumpQuoteCurve,
  quoteControl?: QuoteControl | null,
): { virtualQuoteReserves: BN; depth: number } {
  const curve = quote.bondingCurve;
  const depth = curve.depth + 1;
  if (depth > global.maxCurveDepth) {
    throw new CurveDepthExceededError(depth, global.maxCurveDepth);
  }
  if (curve.isMayhemMode) {
    throw new QuoteBondingCurveNotEligibleError(quote.mint);
  }
  const target = pumpQuoteTarget(
    global,
    quote,
    quoteControl !== undefined ? quoteControl : (quote.quoteControl ?? null),
  );

  let base: BN;
  let quoteSide: BN;
  if (isBondingCurveMigrated(curve)) {
    if (!quote.pool) {
      throw new Error(
        `Pump coin ${quote.mint.toBase58()} has migrated: its pool reserves are required`,
      );
    }
    base = quote.pool.baseReserves;
    quoteSide = quote.pool.quoteReserves.add(quote.pool.virtualQuoteReserves);
  } else {
    if (curve.complete) {
      throw new QuoteCurveAwaitingMigrationError(quote.mint);
    }
    base = curve.virtualTokenReserves;
    quoteSide = curve.virtualQuoteReserves;
  }
  // The program refuses these with Overflow / DivisionByZero.
  if (quoteSide.isNeg()) {
    throw new Error(
      `Pump coin ${quote.mint.toBase58()}: negative effective pool quote reserves (Overflow)`,
    );
  }
  if (quoteSide.isZero()) {
    throw new Error(
      `Pump coin ${quote.mint.toBase58()}: zero quote reserves (DivisionByZero)`,
    );
  }

  const derived = target.mul(base).div(quoteSide);
  if (derived.gt(U64_MAX)) {
    throw new Error(
      `Pump coin ${quote.mint.toBase58()}: derived reserves overflow u64 (Overflow)`,
    );
  }
  const raise = derived
    .mul(global.initialRealTokenReserves)
    .div(
      global.initialVirtualTokenReserves.sub(global.initialRealTokenReserves),
    );
  if (derived.ltn(1) || raise.gt(quote.mintSupply)) {
    throw new QuoteReservesOutOfRangeError(quote.mint, derived);
  }
  return { virtualQuoteReserves: derived, depth };
}

/**
 * The curve `create_v2` would initialize for `quoteMint`.
 *
 * @param quoteControl - See `initialVirtualQuoteReservesFor`; required for a
 * quote-control mint to be seeded correctly.
 * @param creatorFeeBps - The `creator_fee_bps` the create is sent with
 * (`createV2Instruction`'s `creatorFeeBps`); omitted or zero means the
 * schedule rate. `create_v2` always stores `canEditCreatorFee = false`.
 * @param isHolderReward - Whether the create is sent with `holderReward`
 * (`createV2Instruction`'s `holderReward`): the curve's creator is then the
 * coin's `holderRewardsPda(mint)`, which this function cannot derive without
 * the mint, so `creator` stays the zero key either way.
 * @param pumpQuote - When `quoteMint` is a pump coin listed nowhere; sets
 * the derived seed and `depth` (see `pumpQuoteReserves`).
 */
export function newBondingCurve(
  global: Global,
  quoteMint: PublicKey = PublicKey.default,
  quoteControl?: QuoteControl | null,
  creatorFeeBps?: BN,
  isHolderReward = false,
  pumpQuote?: PumpQuoteCurve,
): BondingCurve {
  // The type never admitted `null`, but the pre-quote-control code treated any
  // falsy quote as SOL at runtime and untyped callers rely on it.
  const quote = quoteMint ?? PublicKey.default;
  const virtualQuoteReserves = initialVirtualQuoteReservesFor(
    global,
    quote,
    quoteControl,
    pumpQuote ?? undefined,
  );
  // A listed quote wins over the pump-quote path, as in `create_v2`.
  const isPumpQuoted =
    pumpQuote != null &&
    !isLegacyQuoteMint(quote) &&
    !global.whitelistedQuoteMints.some((mint) => mint.equals(quote)) &&
    !quoteControl?.mints.some((entry) => entry.mint.equals(quote));

  return {
    virtualTokenReserves: global.initialVirtualTokenReserves,
    virtualQuoteReserves,
    realTokenReserves: global.initialRealTokenReserves,
    realQuoteReserves: new BN(0),
    tokenTotalSupply: global.tokenTotalSupply,
    complete: false,
    creator: PublicKey.default,
    isMayhemMode: global.mayhemModeEnabled,
    isCashbackCoin: false,
    // Stored the way the program stores it: the zero key for SOL curves.
    quoteMint: isLegacyQuoteMint(quote) ? PublicKey.default : quote,
    creatorFeeBps: creatorFeeBps ?? new BN(0),
    canEditCreatorFee: false,
    isHolderReward,
    creatorFee: new BN(0),
    protocolFees: new BN(0),
    depth: isPumpQuoted ? pumpQuote.bondingCurve.depth + 1 : 0,
    initialVirtualQuoteReserves: virtualQuoteReserves,
    postCompleteBaseOut: new BN(0),
    postCompleteQuoteIn: new BN(0),
  };
}

function getBuySolAmountFromTokenAmountQuote({
  minAmount,
  virtualTokenReserves,
  virtualQuoteReserves,
}: {
  minAmount: BN;
  virtualTokenReserves: BN;
  virtualQuoteReserves: BN;
}): BN {
  return minAmount
    .mul(virtualQuoteReserves)
    .div(virtualTokenReserves.sub(minAmount))
    .add(new BN(1));
}

function getBuyTokenAmountFromSolAmountQuote({
  inputAmount,
  virtualTokenReserves,
  virtualQuoteReserves,
}: {
  inputAmount: BN;
  virtualTokenReserves: BN;
  virtualQuoteReserves: BN;
}): BN {
  return inputAmount
    .mul(virtualTokenReserves)
    .div(virtualQuoteReserves.add(inputAmount));
}

function getSellSolAmountFromTokenAmountQuote({
  inputAmount,
  virtualTokenReserves,
  virtualQuoteReserves,
}: {
  inputAmount: BN;
  virtualTokenReserves: BN;
  virtualQuoteReserves: BN;
}): BN {
  return inputAmount
    .mul(virtualQuoteReserves)
    .div(virtualTokenReserves.add(inputAmount));
}

/**
 * @param params.quoteMint - Selects the quote when `bondingCurve` is `null`
 * (a curve about to be created); an existing curve's own `quoteMint` is
 * authoritative for fee selection.
 * @param params.quoteControl - The decoded `QuoteControl` PDA (or `null` when
 * it does not exist), needed to seed a new curve quoted in a quote-control
 * mint; see `initialVirtualQuoteReservesFor`.
 * @param params.creatorFeeBps - Used only when `bondingCurve` is `null`: the
 * `creator_fee_bps` the create is sent with, so the first buy is quoted at
 * the rate the program will charge. An existing curve's own `creatorFeeBps`
 * is authoritative.
 */
export function getBuyTokenAmountFromSolAmount({
  global,
  feeConfig,
  mintSupply,
  bondingCurve,
  amount,
  quoteMint,
  quoteControl,
  creatorFeeBps,
  pumpQuote,
}: {
  global: Global;
  feeConfig: FeeConfig | null;
  mintSupply: BN | null;
  bondingCurve: BondingCurve | null;
  amount: BN;
  quoteMint: PublicKey;
  quoteControl?: QuoteControl | null;
  creatorFeeBps?: BN;
  /** Used only when `bondingCurve` is `null` and the quote is a pump coin. */
  pumpQuote?: PumpQuoteCurve;
}): BN {
  if (amount.eq(new BN(0))) {
    return new BN(0);
  }

  let isNewBondingCurve = false;

  if (bondingCurve === null || mintSupply === null) {
    bondingCurve = newBondingCurve(
      global,
      quoteMint,
      quoteControl,
      creatorFeeBps,
      false,
      pumpQuote ?? undefined,
    );
    mintSupply = global.tokenTotalSupply;
    isNewBondingCurve = true;
  }

  // migrated bonding curve
  if (bondingCurve.virtualTokenReserves.eq(new BN(0))) {
    return new BN(0);
  }

  const { virtualQuoteReserves, virtualTokenReserves } = bondingCurve;
  const { protocolFeeBps, creatorFeeBps: chargedCreatorFeeBps } =
    computeFeesBps({
      global,
      feeConfig,
      mintSupply,
      virtualQuoteReserves,
      virtualTokenReserves,
      quoteMint: bondingCurve.quoteMint,
      creatorFeeBps: bondingCurve.creatorFeeBps,
    });

  const totalFeeBasisPoints = protocolFeeBps.add(
    isNewBondingCurve || !PublicKey.default.equals(bondingCurve.creator)
      ? chargedCreatorFeeBps
      : new BN(0),
  );

  const inputAmount = amount
    .subn(1)
    .muln(10_000)
    .div(totalFeeBasisPoints.addn(10_000));

  const tokensReceived = getBuyTokenAmountFromSolAmountQuote({
    inputAmount,
    virtualTokenReserves: bondingCurve.virtualTokenReserves,
    virtualQuoteReserves: bondingCurve.virtualQuoteReserves,
  });

  return BN.min(tokensReceived, bondingCurve.realTokenReserves);
}

/**
 * @param params.quoteMint - Selects the quote when `bondingCurve` is `null`
 * (a curve about to be created); an existing curve's own `quoteMint` is
 * authoritative for fee selection.
 * @param params.quoteControl - The decoded `QuoteControl` PDA (or `null` when
 * it does not exist), needed to seed a new curve quoted in a quote-control
 * mint; see `initialVirtualQuoteReservesFor`.
 * @param params.creatorFeeBps - Used only when `bondingCurve` is `null`; see
 * `getBuyTokenAmountFromSolAmount`.
 */
export function getBuySolAmountFromTokenAmount({
  global,
  feeConfig,
  mintSupply,
  bondingCurve,
  amount,
  quoteMint,
  quoteControl,
  creatorFeeBps,
  pumpQuote,
}: {
  global: Global;
  feeConfig: FeeConfig | null;
  mintSupply: BN | null;
  bondingCurve: BondingCurve | null;
  amount: BN;
  quoteMint: PublicKey;
  quoteControl?: QuoteControl | null;
  creatorFeeBps?: BN;
  /** Used only when `bondingCurve` is `null` and the quote is a pump coin. */
  pumpQuote?: PumpQuoteCurve;
}): BN {
  if (amount.eq(new BN(0))) {
    return new BN(0);
  }

  let isNewBondingCurve = false;

  if (bondingCurve === null || mintSupply === null) {
    bondingCurve = newBondingCurve(
      global,
      quoteMint,
      quoteControl,
      creatorFeeBps,
      false,
      pumpQuote ?? undefined,
    );
    mintSupply = global.tokenTotalSupply;
    isNewBondingCurve = true;
  }

  // migrated bonding curve
  if (bondingCurve.virtualTokenReserves.eq(new BN(0))) {
    return new BN(0);
  }

  const minAmount = BN.min(amount, bondingCurve.realTokenReserves);

  const solCost = getBuySolAmountFromTokenAmountQuote({
    minAmount,
    virtualTokenReserves: bondingCurve.virtualTokenReserves,
    virtualQuoteReserves: bondingCurve.virtualQuoteReserves,
  });

  return solCost.add(
    getFee({
      global,
      feeConfig,
      mintSupply,
      bondingCurve,
      amount: solCost,
      isNewBondingCurve,
    }),
  );
}

export function getSellSolAmountFromTokenAmount({
  global,
  feeConfig,
  mintSupply,
  bondingCurve,
  amount,
}: {
  global: Global;
  feeConfig: FeeConfig | null;
  mintSupply: BN;
  bondingCurve: BondingCurve;
  amount: BN;
}): BN {
  if (amount.eq(new BN(0))) {
    return new BN(0);
  }

  // migrated bonding curve
  if (bondingCurve.virtualTokenReserves.eq(new BN(0))) {
    return new BN(0);
  }

  const solCost = getSellSolAmountFromTokenAmountQuote({
    inputAmount: amount,
    virtualTokenReserves: bondingCurve.virtualTokenReserves,
    virtualQuoteReserves: bondingCurve.virtualQuoteReserves,
  });

  return solCost.sub(
    getFee({
      global,
      feeConfig,
      mintSupply,
      bondingCurve,
      amount: solCost,
      isNewBondingCurve: false,
    }),
  );
}

export function getStaticRandomFeeRecipient(): PublicKey {
  const randomIndex = Math.floor(Math.random() * CURRENT_FEE_RECIPIENTS.length);
  return new PublicKey(CURRENT_FEE_RECIPIENTS[randomIndex]);
}

const CURRENT_FEE_RECIPIENTS = [
  "62qc2CNXwrYqQScmEdiZFFAnJR262PxWEuNQtxfafNgV",
  "7VtfL8fvgNfhz17qKRMjzQEXgbdpnHHHQRh54R9jP2RJ",
  "7hTckgnGnLQR6sdH7YkqFTAA7VwTfYFaZ6EhEsU3saCX",
  "9rPYyANsfQZw3DnDmKE3YCQF5E8oD89UXoHn9JFEhJUz",
  "AVmoTthdrX6tKt4nDjco2D775W2YK3sDhxPcMmzUAmTY",
  "CebN5WGQ4jvEPvsVU4EoHEpgzq1VV7AbicfhtW4xC9iM",
  "FWsW1xNtWscwNmKv6wVsU1iTzRN6wmmk3MjxRP5tT7hz",
  "G5UZAVbAf46s7cKWoyKu8kYTip9DGTpbLZ2qa9Aq69dP",
];

export function getStaticRandomFeeRecipientForBuyback(): PublicKey {
  const randomIndex = Math.floor(
    Math.random() * CURRENT_FEE_RECIPIENTS_FOR_BUYBACK.length,
  );
  return new PublicKey(CURRENT_FEE_RECIPIENTS_FOR_BUYBACK[randomIndex]);
}

/**
 * The buyback recipient whose quote ATA the v3 trades pay on a token quote:
 * always the first listed entry (`Global.buybackFeeRecipients[0]`), so a
 * single ATA per quote mint must exist (the trade never creates it). SOL
 * curves pay any listed wallet (`getStaticRandomFeeRecipientForBuyback`).
 */
export function getBuybackFeeRecipientForTokenQuote(): PublicKey {
  return new PublicKey(CURRENT_FEE_RECIPIENTS_FOR_BUYBACK[0]);
}

// Same keys, same order as `Global.buybackFeeRecipients` on mainnet and devnet.
const CURRENT_FEE_RECIPIENTS_FOR_BUYBACK = [
  "5YxQFdt3Tr9zJLvkFccqXVUwhdTWJQc1fFg2YPbxvxeD",
  "9M4giFFMxmFGXtc3feFzRai56WbBqehoSeRE5GK7gf7",
  "GXPFM2caqTtQYC2cJ5yJRi9VDkpsYZXzYdwYpGnLmtDL",
  "3BpXnfJaUTiwXnJNe7Ej1rcbzqTTQUvLShZaWazebsVR",
  "5cjcW9wExnJJiqgLjq7DEG75Pm6JBgE1hNv4B2vHXUW6",
  "EHAAiTxcdDwQ3U4bU6YcMsQGaekdzLS3B5SmYo46kJtL",
  "5eHhjP8JaYkz83CWwvGU2uMUXefd3AazWGx4gpcuEEYD",
  "A7hAgCzFw14fejgCp387JUJRMNyz4j89JKnhtKU8piqW",
];

export function bondingCurveMarketCap({
  mintSupply,
  virtualQuoteReserves,
  virtualTokenReserves,
}: {
  mintSupply: BN;
  virtualQuoteReserves: BN;
  virtualTokenReserves: BN;
}): BN {
  if (virtualTokenReserves.isZero()) {
    throw new Error("Division by zero: virtual token reserves cannot be zero");
  }
  return virtualQuoteReserves.mul(mintSupply).div(virtualTokenReserves);
}

// ---- v3 buys: the post-completion leg ----
//
// A `buy_v3` / `buy_exact_quote_in_v3` past the remaining supply sells the
// remainder at the curve's price, completes the curve and buys the rest from
// the pool the migration will create (not on mayhem curves). These mirror the
// program's arithmetic, fees included.

interface V3Rates {
  protocolFeeBps: BN;
  // Zero on a curve without a creator, as the program charges.
  creatorFeeBps: BN;
}

function v3Rates(
  global: Global,
  feeConfig: FeeConfig | null,
  mintSupply: BN,
  bondingCurve: BondingCurve,
): V3Rates {
  const { protocolFeeBps, creatorFeeBps } = computeFeesBps({
    global,
    feeConfig,
    mintSupply: bondingCurve.isMayhemMode ? mintSupply : ONE_BILLION_SUPPLY,
    virtualQuoteReserves: bondingCurve.virtualQuoteReserves,
    virtualTokenReserves: bondingCurve.virtualTokenReserves,
    quoteMint: bondingCurve.quoteMint,
    creatorFeeBps: bondingCurve.creatorFeeBps,
  });
  return {
    protocolFeeBps,
    creatorFeeBps: bondingCurve.creator.equals(PublicKey.default)
      ? new BN(0)
      : creatorFeeBps,
  };
}

function ceilFee(amount: BN, bps: BN): BN {
  return amount.mul(bps).addn(9_999).divn(10_000);
}

function v3Fees(amount: BN, rates: V3Rates): BN {
  return ceilFee(amount, rates.protocolFeeBps).add(
    ceilFee(amount, rates.creatorFeeBps),
  );
}

// pump `exact_quote_in_fees`: the net quote a budget leaves after fees.
function v3ExactQuoteInNet(budget: BN, rates: V3Rates): BN {
  const totalBps = rates.protocolFeeBps.add(rates.creatorFeeBps);
  let net = totalBps.isZero()
    ? budget
    : budget.muln(10_000).div(totalBps.addn(10_000));
  const cost = net.add(v3Fees(net, rates));
  if (cost.gt(budget)) {
    net = net.sub(cost.sub(budget));
  }
  return net;
}

// The reserves `migrate_v2` would deposit once the curve leg completes it.
function poolToBe(
  global: Global,
  bondingCurve: BondingCurve,
  curveBaseTokenBalance: BN,
  curveTokens: BN,
  curveNetQuote: BN,
): { base: BN; quote: BN } {
  const raised = bondingCurve.realQuoteReserves.add(curveNetQuote);
  const base = curveBaseTokenBalance.sub(curveTokens);
  const quote = isLegacyQuoteMint(bondingCurve.quoteMint)
    ? raised.sub(global.poolMigrationFee)
    : raised;
  // The program refuses an empty pool-to-be; here it almost always means a
  // wrong `curveBaseTokenBalance` (say, read under the other token program).
  if (base.lten(0) || quote.lten(0)) {
    throw new Error(
      `Empty pool-to-be (base ${base.toString()}, quote ${quote.toString()}): check curveBaseTokenBalance`,
    );
  }
  return { base, quote };
}

/**
 * What `buy_v3` charges for `amount` tokens, fees included: the cap to send
 * as `max_sol_cost` before slippage. Past the remaining supply the cost
 * includes the post-completion leg; on a mayhem curve it stops at the
 * remaining supply (send `partialFill` then). Zero on a complete curve
 * (every trade is refused until the migration).
 *
 * @param params.curveBaseTokenBalance - The curve's base ATA balance
 *   (`OnlinePumpSdk.fetchBuyState` returns it); prices the pool-to-be.
 * @throws when `amount` would take the whole pool-to-be (6021
 *   `NotEnoughTokensToBuy` on chain), or when the pool-to-be is empty.
 */
export function getBuyV3QuoteAmountFromTokenAmount({
  global,
  feeConfig,
  mintSupply,
  bondingCurve,
  amount,
  curveBaseTokenBalance,
}: {
  global: Global;
  feeConfig: FeeConfig | null;
  mintSupply: BN;
  bondingCurve: BondingCurve;
  amount: BN;
  curveBaseTokenBalance: BN;
}): BN {
  const remaining = bondingCurve.realTokenReserves;
  if (
    amount.isZero() ||
    bondingCurve.complete ||
    bondingCurve.virtualTokenReserves.isZero()
  ) {
    return new BN(0);
  }
  const rates = v3Rates(global, feeConfig, mintSupply, bondingCurve);
  const curveTokens = BN.min(amount, remaining);
  const curveNet = getBuySolAmountFromTokenAmountQuote({
    minAmount: curveTokens,
    virtualTokenReserves: bondingCurve.virtualTokenReserves,
    virtualQuoteReserves: bondingCurve.virtualQuoteReserves,
  });
  const curveTotal = curveNet.add(v3Fees(curveNet, rates));
  if (amount.lte(remaining) || bondingCurve.isMayhemMode) {
    return curveTotal;
  }

  const pastCurve = amount.sub(remaining);
  const pool = poolToBe(
    global,
    bondingCurve,
    curveBaseTokenBalance,
    remaining,
    curveNet,
  );
  if (pool.base.lte(pastCurve)) {
    throw new Error(
      `buy_v3 of ${amount.toString()} tokens takes the whole pool-to-be (NotEnoughTokensToBuy)`,
    );
  }
  // pump-amm `buy_quote`: ceil(Q * out / (B - out)).
  const legNet = pool.quote
    .mul(pastCurve)
    .add(pool.base.sub(pastCurve))
    .subn(1)
    .div(pool.base.sub(pastCurve));
  return curveTotal.add(legNet).add(v3Fees(legNet, rates));
}

/**
 * The tokens `buy_exact_quote_in_v3` buys for `amount` quote, fees included;
 * apply slippage to it for `min_tokens_out`. Past the remaining supply the
 * leftover budget buys from the pool-to-be; on a mayhem curve it stops at the
 * remaining supply (send `partialFill` then). Zero on a complete curve.
 *
 * @param params.curveBaseTokenBalance - As in
 *   `getBuyV3QuoteAmountFromTokenAmount`.
 * @throws when a crossing budget meets an empty pool-to-be.
 */
export function getBuyV3TokenAmountFromQuoteAmount({
  global,
  feeConfig,
  mintSupply,
  bondingCurve,
  amount,
  curveBaseTokenBalance,
}: {
  global: Global;
  feeConfig: FeeConfig | null;
  mintSupply: BN;
  bondingCurve: BondingCurve;
  amount: BN;
  curveBaseTokenBalance: BN;
}): BN {
  if (
    amount.isZero() ||
    bondingCurve.complete ||
    bondingCurve.virtualTokenReserves.isZero()
  ) {
    return new BN(0);
  }
  const rates = v3Rates(global, feeConfig, mintSupply, bondingCurve);
  const net = v3ExactQuoteInNet(amount, rates);
  if (net.lten(1)) {
    return new BN(0);
  }
  const tokens = getBuyTokenAmountFromSolAmountQuote({
    inputAmount: net.subn(1),
    virtualTokenReserves: bondingCurve.virtualTokenReserves,
    virtualQuoteReserves: bondingCurve.virtualQuoteReserves,
  });
  const remaining = bondingCurve.realTokenReserves;
  if (tokens.lte(remaining) || bondingCurve.isMayhemMode) {
    return BN.min(tokens, remaining);
  }

  const curveNet = getBuySolAmountFromTokenAmountQuote({
    minAmount: remaining,
    virtualTokenReserves: bondingCurve.virtualTokenReserves,
    virtualQuoteReserves: bondingCurve.virtualQuoteReserves,
  });
  const budgetLeft = amount.sub(curveNet.add(v3Fees(curveNet, rates)));
  if (budgetLeft.lten(0)) {
    return remaining;
  }
  const totalBps = rates.protocolFeeBps.add(rates.creatorFeeBps);
  const afterFees = totalBps.isZero()
    ? budgetLeft
    : budgetLeft.muln(10_000).div(totalBps.addn(10_000));
  if (afterFees.ltn(2)) {
    return remaining;
  }
  const legNet = v3ExactQuoteInNet(budgetLeft, rates);
  const pool = poolToBe(
    global,
    bondingCurve,
    curveBaseTokenBalance,
    remaining,
    curveNet,
  );
  // pump-amm `buy_exact_quote_in`: floor((in - 1) * B / (Q + in - 1)).
  const legTokens = legNet
    .subn(1)
    .mul(pool.base)
    .div(pool.quote.add(legNet.subn(1)));
  return remaining.add(legTokens);
}
