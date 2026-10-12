import { Program } from "@coral-xyz/anchor";
import {
  coinCreatorVaultAtaPda,
  coinCreatorVaultAuthorityPda,
  OnlinePumpAmmSdk,
  PUMP_AMM_SDK,
  PumpAmmAdminSdk,
} from "@pump-fun/pump-swap-sdk";
import {
  createAssociatedTokenAccountIdempotentInstruction,
  getAssociatedTokenAddressSync,
  NATIVE_MINT,
  TOKEN_2022_PROGRAM_ID,
  TOKEN_PROGRAM_ID,
  unpackAccount,
  unpackMint,
} from "@solana/spl-token";
import {
  AccountInfo,
  AddressLookupTableAccount,
  ComputeBudgetProgram,
  Connection,
  PublicKey,
  PublicKeyInitData,
  TransactionInstruction,
  TransactionMessage,
  VersionedTransaction,
} from "@solana/web3.js";
import BN from "bn.js";

import {
  isBondingCurveMigrated,
  PumpQuoteCurve,
  pumpQuoteReserves,
} from "./bondingCurve";
import {
  CreatorFeeBpsOutOfRangeError,
  CreatorFeeNotAllowedForCashbackCoinError,
  CreatorFeeNotConfigurableError,
  CreatorFeeNotConfigurableForQuoteError,
  CtoNotAllowedForMayhemCoinError,
  HolderRewardCreatorImmutableError,
  HolderRewardDisabledError,
  QuotePoolNotFoundError,
  UnsupportedQuoteMintError,
} from "./errors";
import { Pump } from "./idl/pump";
import { PumpAmm } from "./idl/pump_amm";
import {
  bondingCurvePda,
  canonicalPumpPoolPdaWithQuote,
  creatorVaultPda,
  feeSharingConfigPda,
  GLOBAL_PDA,
  GLOBAL_VOLUME_ACCUMULATOR_PDA,
  holderRewardsPda,
  isLegacyQuoteMint,
  normalizeQuoteMint,
  PUMP_FEE_CONFIG_PDA,
  QUOTE_CONTROL_PDA,
  quoteAta,
  userVolumeAccumulatorPda,
} from "./pda";
import {
  ADMIN_CTO_COMPUTE_UNIT_LIMIT,
  getPumpAmmProgram,
  getPumpProgram,
  MultiHopHop,
  multiHopRouteEnds,
  MultiHopSide,
  PUMP_AMM_PROGRAM_ID,
  PUMP_PROGRAM_ID,
  PUMP_SDK,
  PUMP_TOKEN_MINT,
  PumpQuoteAccounts,
} from "./sdk";
import {
  BondingCurve,
  FeeConfig,
  Fees,
  Global,
  GlobalVolumeAccumulator,
  MinimumDistributableFeeEvent,
  QuoteControl,
  QuoteMintSource,
  ResolvedQuoteMint,
  SupportedQuoteMint,
  UserVolumeAccumulator,
  UserVolumeAccumulatorTotalStats,
} from "./state";
import { currentDayTokens, totalUnclaimedTokens } from "./tokenIncentives";

export const OFFLINE_PUMP_PROGRAM = getPumpProgram(null as any as Connection);

// Standard Solana RPCs reject `getMultipleAccounts` with more than this many
// keys ("failed to get info for accounts"); some providers accept more.
const GET_MULTIPLE_ACCOUNTS_MAX_KEYS = 100;

/**
 * `connection.getMultipleAccountsInfo` over any number of keys, in slices of
 * `GET_MULTIPLE_ACCOUNTS_MAX_KEYS` fetched concurrently (web3.js does not
 * slice by itself). No RPC call for an empty list.
 */
async function getMultipleAccountsInfoChunked(
  connection: Connection,
  keys: readonly PublicKey[],
): Promise<(AccountInfo<Buffer> | null)[]> {
  const chunks = Array.from(
    { length: Math.ceil(keys.length / GET_MULTIPLE_ACCOUNTS_MAX_KEYS) },
    (_, index) =>
      keys.slice(
        index * GET_MULTIPLE_ACCOUNTS_MAX_KEYS,
        (index + 1) * GET_MULTIPLE_ACCOUNTS_MAX_KEYS,
      ),
  );
  const results = await Promise.all(
    chunks.map((chunk) => connection.getMultipleAccountsInfo(chunk)),
  );
  return results.flat();
}

/** Whether `programId` is a program a quote mint may be owned by. */
function isQuoteTokenProgram(programId: PublicKey): boolean {
  return (
    programId.equals(TOKEN_PROGRAM_ID) ||
    programId.equals(TOKEN_2022_PROGRAM_ID)
  );
}

/**
 * The token program a fetched quote mint belongs to, which every quote-side
 * ATA must be derived with. A mint owned by anything else cannot be a quote.
 */
function quoteTokenProgramOf(
  mint: PublicKey,
  mintAccountInfo: AccountInfo<Buffer>,
): PublicKey {
  const { owner } = mintAccountInfo;
  if (!isQuoteTokenProgram(owner)) {
    throw new Error(
      `Quote mint ${mint.toBase58()} is owned by ${owner.toBase58()}, not by SPL Token or Token-2022`,
    );
  }
  return owner;
}

/**
 * Whether a fetched account is a token account of `tokenProgram`, which is
 * what both fee programs deserialize a vault ATA as (`TokenAccount`). Any
 * other account at an ATA address (anyone can fund a system account there; the
 * address is public) counts as absent, so it is never put in a collect
 * instruction the program would then fail on, and never unpacked.
 */
function isTokenAccount(
  accountInfo: AccountInfo<Buffer> | null,
  tokenProgram: PublicKey,
): accountInfo is AccountInfo<Buffer> {
  return accountInfo !== null && accountInfo.owner.equals(tokenProgram);
}

/** A quote mint with the program that owns it. */
interface QuoteMintProgram {
  mint: PublicKey;
  quoteTokenProgram: PublicKey;
}

/**
 * The quote mints `create_v2` accepts, from the fetched `Global` and
 * `QuoteControl` accounts: SOL first, then the non-zero `Global` whitelist
 * slots, then the quote-control entries `Global` does not already list. A
 * mint in both lists is reported once, as `Global`'s, because that is the
 * seeding `create_v2` applies to it. A missing `QuoteControl` PDA is an empty
 * list, as the program treats it.
 */
function supportedQuoteMints(
  globalAccountInfo: AccountInfo<Buffer> | null,
  quoteControlAccountInfo: AccountInfo<Buffer> | null,
): SupportedQuoteMint[] {
  if (!globalAccountInfo) {
    throw new Error(`Global account not found: ${GLOBAL_PDA.toBase58()}`);
  }
  const global = PUMP_SDK.decodeGlobal(globalAccountInfo);
  // Strict on purpose: this list decides which vaults get swept, so an account
  // at the PDA that is not a well-formed `QuoteControl` is an error, not an
  // empty list (`decodeQuoteControlNullable` would swallow it).
  const quoteControl = quoteControlAccountInfo
    ? PUMP_SDK.decodeQuoteControl(quoteControlAccountInfo)
    : null;

  const supported: SupportedQuoteMint[] = [
    {
      mint: NATIVE_MINT,
      source: "sol",
      initialVirtualQuoteReserves: global.initialVirtualSolReserves,
    },
    ...global.whitelistedQuoteMints
      .filter((mint) => !isLegacyQuoteMint(mint))
      .map((mint) => ({
        mint,
        source: "global" as const,
        initialVirtualQuoteReserves: global.initialVirtualQuoteReserves,
      })),
  ];
  for (const entry of quoteControl?.mints ?? []) {
    if (!supported.some(({ mint }) => mint.equals(entry.mint))) {
      supported.push({
        mint: entry.mint,
        source: "quoteControl",
        initialVirtualQuoteReserves: entry.initialVirtualQuoteReserves,
      });
    }
  }
  return supported;
}

/**
 * Token amount held by a fetched token account, or zero when it is missing or
 * is not a token account of `tokenProgram` (see `isTokenAccount`).
 */
function tokenAccountAmount(
  address: PublicKey,
  accountInfo: AccountInfo<Buffer> | null,
  tokenProgram: PublicKey,
): BN {
  if (!isTokenAccount(accountInfo, tokenProgram)) {
    return new BN(0);
  }
  const { amount } = unpackAccount(address, accountInfo, tokenProgram);
  return new BN(amount.toString());
}

// pump-amm `Pool` fields read raw (the layout only ever grew at the end, so
// the offsets are frozen; pump's pump-quote path reads the same bytes): the
// two vault keys (present from 211 bytes, the initial layout), `coin_creator`
// (from 243), the signed i128 `virtual_quote_reserves` (from 261) and
// `creator_fees` (from 287, the fee buckets). A shorter pool reads a missing
// field as the program does: the zero key or zero.
interface PoolFields {
  baseVault: PublicKey;
  quoteVault: PublicKey;
  coinCreator: PublicKey;
  virtualQuoteReserves: BN;
  creatorFees: BN;
}

function readPoolFields({ data }: AccountInfo<Buffer>): PoolFields | null {
  if (data.length < 211) {
    return null;
  }
  const key = (offset: number) =>
    new PublicKey(data.subarray(offset, offset + 32));
  return {
    baseVault: key(139),
    quoteVault: key(171),
    coinCreator: data.length >= 243 ? key(211) : PublicKey.default,
    virtualQuoteReserves:
      data.length >= 261
        ? new BN(data.subarray(245, 261), "le").fromTwos(128)
        : new BN(0),
    creatorFees:
      data.length >= 287 ? new BN(data.subarray(279, 287), "le") : new BN(0),
  };
}

function poolCreatorFees(poolAccountInfo: AccountInfo<Buffer> | null): BN {
  return (
    (poolAccountInfo && readPoolFields(poolAccountInfo)?.creatorFees) ??
    new BN(0)
  );
}

/**
 * The creator-fee sweeps a CTO, a distribution or a fee-sharing change on
 * `mint` needs first, from the fetched state: pump `sweep_creator_fee` when
 * the curve holds creator fees from v3 trades (paid to the vault of the
 * curve's `creator`), pump-amm `sweep_creator_fee` when the canonical pool
 * holds some from v2 pool trades (paid to the vault of the pool's own
 * `coin_creator`, which pump-amm requires). An empty bucket needs no sweep,
 * so coins without such trades get none. A trade landing between the fetch
 * and the transaction can still leave a bucket nonzero (6095 / pump-amm 6081
 * `CreatorFeesNotSwept`); rebuilding picks it up.
 */
async function creatorFeeSweepInstructions({
  payer,
  mint,
  bondingCurve,
  poolAccountInfo,
  quoteMint,
  quoteTokenProgram,
}: {
  payer: PublicKey | undefined;
  mint: PublicKey;
  bondingCurve: BondingCurve | null;
  poolAccountInfo: AccountInfo<Buffer> | null;
  quoteMint: PublicKey;
  quoteTokenProgram: PublicKey;
}): Promise<TransactionInstruction[]> {
  const pool = poolAccountInfo ? readPoolFields(poolAccountInfo) : null;
  const sweepCurve = bondingCurve !== null && !bondingCurve.creatorFee.isZero();
  const sweepPool = pool !== null && !pool.creatorFees.isZero();
  if (!sweepCurve && !sweepPool) {
    return [];
  }
  if (!payer) {
    throw new Error(
      `payer is required: ${mint.toBase58()} has un-swept creator fees, and the sweep that must come first needs a signer`,
    );
  }
  const sweep = { payer, mint, quoteMint, quoteTokenProgram };
  return [
    ...(sweepCurve
      ? [
          await PUMP_SDK.sweepCreatorFeeInstruction({
            ...sweep,
            creator: bondingCurve.creator,
          }),
        ]
      : []),
    ...(sweepPool
      ? [
          await PUMP_SDK.sweepPoolCreatorFeeInstruction({
            ...sweep,
            coinCreator: pool.coinCreator,
          }),
        ]
      : []),
  ];
}

export class OnlinePumpSdk {
  private readonly connection: Connection;
  private readonly pumpProgram: Program<Pump>;
  private readonly offlinePumpProgram: Program<Pump>;
  private readonly pumpAmmProgram: Program<PumpAmm>;
  private readonly pumpAmmSdk: OnlinePumpAmmSdk;
  private readonly pumpAmmAdminSdk: PumpAmmAdminSdk;

  constructor(connection: Connection) {
    this.connection = connection;

    this.pumpProgram = getPumpProgram(connection);
    this.offlinePumpProgram = OFFLINE_PUMP_PROGRAM;
    this.pumpAmmProgram = getPumpAmmProgram(connection);

    this.pumpAmmSdk = new OnlinePumpAmmSdk(connection);
    this.pumpAmmAdminSdk = new PumpAmmAdminSdk(connection);
  }

  /**
   * The pump `Global` account, decoded by `PumpSdk.decodeGlobal` so the live
   * account still decodes while it is shorter than `GLOBAL_SIZE` (before
   * `extend_account` adds the newest fields).
   */
  async fetchGlobal(): Promise<Global> {
    const accountInfo = await this.connection.getAccountInfo(GLOBAL_PDA);
    if (!accountInfo) {
      throw new Error(`Global account not found: ${GLOBAL_PDA.toBase58()}`);
    }
    return PUMP_SDK.decodeGlobal(accountInfo);
  }

  async fetchFeeConfig(): Promise<FeeConfig> {
    const accountInfo =
      await this.connection.getAccountInfo(PUMP_FEE_CONFIG_PDA);

    if (!accountInfo) {
      throw new Error(
        `Fee config account not found: ${PUMP_FEE_CONFIG_PDA.toBase58()}`,
      );
    }

    return PUMP_SDK.decodeFeeConfig(accountInfo);
  }

  /**
   * The pump `QuoteControl` PDA, or `null` while it is uninitialized (the
   * program treats a missing account as an empty mint list). Only a missing
   * account yields `null`: an account at the PDA that does not decode as a
   * `QuoteControl` throws (Anchor `fetchNullable`), unlike
   * `PumpSdk.decodeQuoteControlNullable`, which maps decode failures to
   * `null`.
   */
  async fetchQuoteControl(): Promise<QuoteControl | null> {
    return await this.pumpProgram.account.quoteControl.fetchNullable(
      QUOTE_CONTROL_PDA,
    );
  }

  /**
   * The program that owns `quoteMint`, which every quote-side ATA and every
   * `quoteTokenProgram` parameter in this SDK must use. WSOL and the zero key
   * resolve to `TOKEN_PROGRAM_ID` without an RPC call; any other mint is
   * fetched and must be owned by SPL Token or Token-2022 (a missing account or
   * another owner throws). That includes the Token-2022 native mint, which
   * resolves to its owner, `TOKEN_2022_PROGRAM_ID`: it is SOL-like for fee
   * selection only, and `create_v2` rejects it as a quote.
   */
  async fetchQuoteTokenProgram(quoteMint: PublicKey): Promise<PublicKey> {
    if (isLegacyQuoteMint(quoteMint)) {
      return TOKEN_PROGRAM_ID;
    }

    const mintAccountInfo = await this.connection.getAccountInfo(quoteMint);
    if (!mintAccountInfo) {
      throw new Error(`Quote mint account not found: ${quoteMint.toBase58()}`);
    }
    return quoteTokenProgramOf(quoteMint, mintAccountInfo);
  }

  /**
   * Every quote mint `create_v2` accepts right now, in one RPC round-trip: SOL
   * (as `NATIVE_MINT`, seeded from `Global.initialVirtualSolReserves`), the
   * non-zero `Global.whitelistedQuoteMints` slots, then the `QuoteControl`
   * entries `Global` does not already list. The PDA is the only source of
   * quote-control mints; while it is uninitialized the list is SOL plus the
   * `Global` whitelist.
   */
  async fetchSupportedQuoteMints(): Promise<SupportedQuoteMint[]> {
    const [globalAccountInfo, quoteControlAccountInfo] =
      await this.connection.getMultipleAccountsInfo([
        GLOBAL_PDA,
        QUOTE_CONTROL_PDA,
      ]);
    return supportedQuoteMints(globalAccountInfo, quoteControlAccountInfo);
  }

  /**
   * `fetchSupportedQuoteMints` narrowed to one mint, plus what a builder needs
   * for it: the owning token program and the mint's decimals. SOL-like inputs
   * (`NATIVE_MINT`, the zero key, `undefined`) resolve to the `sol` entry. One
   * RPC round-trip for a listed mint; a pump coin adds `fetchPumpQuote`'s.
   *
   * A mint in neither list that is itself a pump coin resolves as
   * `pumpCoin`: the seed is derived from its price (`pumpQuoteReserves`,
   * whose refusals are thrown as typed errors) and `pumpQuote` carries what
   * the create and the quote functions need.
   *
   * @throws {UnsupportedQuoteMintError} when the mint is in neither list and
   *   is not a pump coin, `create_v2`'s first admission check. A listed mint can still be rejected
   *   on chain: a `quoteTokenProgram` that is not its owner or a Token-2022
   *   extension outside the xStock set (6063), or `mayhemMode` with a mint
   *   admitted only through `QuoteControl` (6071).
   */
  async resolveQuoteMint(
    quoteMint: PublicKey = NATIVE_MINT,
  ): Promise<ResolvedQuoteMint> {
    const mint = normalizeQuoteMint(quoteMint);
    const [globalAccountInfo, quoteControlAccountInfo, mintAccountInfo] =
      await this.connection.getMultipleAccountsInfo([
        GLOBAL_PDA,
        QUOTE_CONTROL_PDA,
        mint,
      ]);

    const supported = supportedQuoteMints(
      globalAccountInfo,
      quoteControlAccountInfo,
    ).find((entry) => entry.mint.equals(mint));
    // Listed nowhere: a pump coin is admitted through its own curve.
    const pumpQuote = supported ? null : await this.fetchPumpQuote(mint);
    if (!supported && !pumpQuote) {
      throw new UnsupportedQuoteMintError(mint);
    }
    if (!mintAccountInfo) {
      throw new Error(`Quote mint account not found: ${mint.toBase58()}`);
    }
    const quoteTokenProgram = quoteTokenProgramOf(mint, mintAccountInfo);
    const { decimals } = unpackMint(mint, mintAccountInfo, quoteTokenProgram);
    if (supported) {
      return { ...supported, quoteTokenProgram, decimals };
    }

    const { virtualQuoteReserves, depth } = pumpQuoteReserves(
      PUMP_SDK.decodeGlobal(globalAccountInfo!),
      pumpQuote!.curve,
      quoteControlAccountInfo
        ? PUMP_SDK.decodeQuoteControl(quoteControlAccountInfo)
        : null,
    );
    return {
      mint,
      source: "pumpCoin",
      initialVirtualQuoteReserves: virtualQuoteReserves,
      quoteTokenProgram,
      decimals,
      pumpQuote: { ...pumpQuote!, depth },
    };
  }

  /**
   * Pump coin `quoteMint` as a `create_v2` quote: its curve, live mint
   * supply, the `QuoteControl` PDA and, once migrated, its canonical pool's
   * reserves (the inputs of `pumpQuoteReserves`), plus the accounts
   * `createV2Instruction`'s `pumpQuote` takes. `null` when `quoteMint` has
   * no pump bonding curve. One RPC round-trip, three once migrated. Does not
   * check whether a list admits the mint first (`resolveQuoteMint` does).
   *
   * @throws {QuotePoolNotFoundError} when Q migrated but has no pump-amm pool
   *   (6102), or an error when the pool or a vault is not one the program
   *   reads (6103 `InvalidQuotePool`).
   */
  async fetchPumpQuote(
    quoteMint: PublicKey,
  ): Promise<{ curve: PumpQuoteCurve; accounts: PumpQuoteAccounts } | null> {
    const [curveAccountInfo, mintAccountInfo, quoteControlAccountInfo] =
      await this.connection.getMultipleAccountsInfo([
        bondingCurvePda(quoteMint),
        quoteMint,
        QUOTE_CONTROL_PDA,
      ]);
    if (!curveAccountInfo || !curveAccountInfo.owner.equals(PUMP_PROGRAM_ID)) {
      return null;
    }
    if (!mintAccountInfo) {
      throw new Error(`Quote mint account not found: ${quoteMint.toBase58()}`);
    }
    const bondingCurve = PUMP_SDK.decodeBondingCurve(curveAccountInfo);
    const mintSupply = new BN(
      unpackMint(
        quoteMint,
        mintAccountInfo,
        quoteTokenProgramOf(quoteMint, mintAccountInfo),
      ).supply.toString(),
    );
    const quoteControl = quoteControlAccountInfo
      ? PUMP_SDK.decodeQuoteControl(quoteControlAccountInfo)
      : null;
    if (!isBondingCurveMigrated(bondingCurve)) {
      return {
        curve: { mint: quoteMint, bondingCurve, mintSupply, quoteControl },
        accounts: {},
      };
    }

    // A SOL curve stores the zero key but migrates into a WSOL pool.
    const pool = canonicalPumpPoolPdaWithQuote(
      quoteMint,
      normalizeQuoteMint(bondingCurve.quoteMint),
    );
    const poolAccountInfo = await this.connection.getAccountInfo(pool);
    if (
      !poolAccountInfo ||
      !poolAccountInfo.owner.equals(PUMP_AMM_PROGRAM_ID)
    ) {
      throw new QuotePoolNotFoundError(quoteMint, pool);
    }
    const fields = readPoolFields(poolAccountInfo);
    if (!fields) {
      throw new Error(
        `Pool ${pool.toBase58()} is too short to be a pump-amm pool (InvalidQuotePool)`,
      );
    }
    const { baseVault, quoteVault, virtualQuoteReserves } = fields;
    const vaultInfos = await this.connection.getMultipleAccountsInfo([
      baseVault,
      quoteVault,
    ]);
    // The program reads only initialized, unfrozen token accounts.
    const [baseReserves, quoteReserves] = [baseVault, quoteVault].map(
      (vault, index) => {
        const info = vaultInfos[index];
        const account =
          info && isQuoteTokenProgram(info.owner)
            ? unpackAccount(vault, info, info.owner)
            : null;
        if (!account || !account.isInitialized || account.isFrozen) {
          throw new Error(
            `Pool vault ${vault.toBase58()} is missing, uninitialized or frozen (InvalidQuotePool)`,
          );
        }
        return new BN(account.amount.toString());
      },
    );
    return {
      curve: {
        mint: quoteMint,
        bondingCurve,
        mintSupply,
        quoteControl,
        pool: { baseReserves, quoteReserves, virtualQuoteReserves },
      },
      accounts: { pool: { pool, baseVault, quoteVault } },
    };
  }

  /**
   * @deprecated use PumpSdk.decodeBondingCurveNullable instead.
   */
  async fetchBondingCurve(mint: PublicKeyInitData): Promise<BondingCurve> {
    const bondingCurve = bondingCurvePda(mint);
    const accountInfo = await this.connection.getAccountInfo(bondingCurve);
    if (!accountInfo) {
      throw new Error(
        `Bonding curve account not found: ${bondingCurve.toBase58()}`,
      );
    }
    // Through the padding decoder: a 115-byte curve does not decode under the
    // vendored IDL otherwise.
    return PUMP_SDK.decodeBondingCurve(accountInfo);
  }

  /**
   * The state `buyV2Instructions` needs, plus the curve's normalized
   * `quoteMint` (`NATIVE_MINT` for SOL curves) and `quoteTokenProgram` (the
   * mint's owner) to forward to it.
   *
   * @param quoteMint - Optional hint: the curve's quote mint when the caller
   *   already knows it (from an earlier fetch, `resolveQuoteMint`, or an
   *   indexer). A curve stores its quote mint, so for a non-SOL curve the
   *   token program is only known after decoding the curve: without the hint
   *   that is a second RPC round-trip; with a correct hint the mint account
   *   joins the first batch. A hint that does not match the curve is ignored
   *   (the second round-trip happens). SOL curves never need one.
   */
  async fetchBuyState(
    mint: PublicKey,
    user: PublicKey,
    tokenProgram: PublicKey = TOKEN_PROGRAM_ID,
    quoteMint?: PublicKey,
  ) {
    const quoteMintHint = this.quoteMintHint(quoteMint);
    // The curve's base ATA under both token programs: the balance must come
    // from the coin's real program even when `tokenProgram` is left at its
    // SPL Token default for a Token-2022 coin.
    const curveBaseAtas = [TOKEN_PROGRAM_ID, TOKEN_2022_PROGRAM_ID].map(
      (program) => ({
        program,
        address: getAssociatedTokenAddressSync(
          mint,
          bondingCurvePda(mint),
          true,
          program,
        ),
      }),
    );
    const accountInfos = await this.connection.getMultipleAccountsInfo([
      bondingCurvePda(mint),
      getAssociatedTokenAddressSync(mint, user, true, tokenProgram),
      ...(quoteMintHint ? [quoteMintHint] : []),
      ...curveBaseAtas.map(({ address }) => address),
    ]);
    const [bondingCurveAccountInfo, associatedUserAccountInfo] = accountInfos;
    const quoteMintHintAccountInfo = quoteMintHint ? accountInfos[2] : null;
    const curveBaseAtaAccountInfos = accountInfos.slice(-2);

    if (!bondingCurveAccountInfo) {
      throw new Error(
        `Bonding curve account not found for mint: ${mint.toBase58()}`,
      );
    }

    const bondingCurve = PUMP_SDK.decodeBondingCurve(bondingCurveAccountInfo);
    const quote = await this.curveQuote(
      bondingCurve,
      quoteMintHint,
      quoteMintHintAccountInfo,
    );
    return {
      bondingCurveAccountInfo,
      bondingCurve,
      associatedUserAccountInfo,
      // The curve's base ATA balance, which prices a v3 buy's
      // post-completion leg (`getBuyV3QuoteAmountFromTokenAmount`).
      curveBaseTokenBalance: curveBaseAtas.reduce(
        (balance, { program, address }, index) =>
          balance.add(
            tokenAccountAmount(
              address,
              curveBaseAtaAccountInfos[index],
              program,
            ),
          ),
        new BN(0),
      ),
      ...quote,
    };
  }

  /**
   * The state `sellV2Instructions` needs, plus the curve's normalized
   * `quoteMint` and `quoteTokenProgram`. `quoteMint` is the same optional
   * hint as on `fetchBuyState`.
   */
  async fetchSellState(
    mint: PublicKey,
    user: PublicKey,
    tokenProgram: PublicKey = TOKEN_PROGRAM_ID,
    quoteMint?: PublicKey,
  ) {
    const quoteMintHint = this.quoteMintHint(quoteMint);
    const [
      bondingCurveAccountInfo,
      associatedUserAccountInfo,
      quoteMintHintAccountInfo,
    ] = await this.connection.getMultipleAccountsInfo([
      bondingCurvePda(mint),
      getAssociatedTokenAddressSync(mint, user, true, tokenProgram),
      ...(quoteMintHint ? [quoteMintHint] : []),
    ]);

    if (!bondingCurveAccountInfo) {
      throw new Error(
        `Bonding curve account not found for mint: ${mint.toBase58()}`,
      );
    }

    if (!associatedUserAccountInfo) {
      throw new Error(
        `Associated token account not found for mint: ${mint.toBase58()} and user: ${user.toBase58()}`,
      );
    }

    const bondingCurve = PUMP_SDK.decodeBondingCurve(bondingCurveAccountInfo);
    const quote = await this.curveQuote(
      bondingCurve,
      quoteMintHint,
      quoteMintHintAccountInfo,
    );
    return { bondingCurveAccountInfo, bondingCurve, ...quote };
  }

  // A quote mint worth fetching alongside the curve: SOL needs no lookup.
  private quoteMintHint(quoteMint: PublicKey | undefined): PublicKey | null {
    return quoteMint && !isLegacyQuoteMint(quoteMint) ? quoteMint : null;
  }

  /**
   * The quote mint a decoded curve trades in (normalized) and the program
   * that owns it. SOL curves need no RPC; another curve uses the hinted mint
   * account when the hint is the curve's own quote, else one more fetch.
   */
  private async curveQuote(
    bondingCurve: BondingCurve,
    quoteMintHint: PublicKey | null,
    quoteMintHintAccountInfo: AccountInfo<Buffer> | null | undefined,
  ): Promise<{ quoteMint: PublicKey; quoteTokenProgram: PublicKey }> {
    const quoteMint = normalizeQuoteMint(bondingCurve.quoteMint);
    if (quoteMint.equals(NATIVE_MINT)) {
      return { quoteMint, quoteTokenProgram: TOKEN_PROGRAM_ID };
    }
    if (quoteMintHint?.equals(quoteMint) && quoteMintHintAccountInfo) {
      return {
        quoteMint,
        quoteTokenProgram: quoteTokenProgramOf(
          quoteMint,
          quoteMintHintAccountInfo,
        ),
      };
    }
    return {
      quoteMint,
      quoteTokenProgram: await this.fetchQuoteTokenProgram(quoteMint),
    };
  }

  async fetchGlobalVolumeAccumulator(): Promise<GlobalVolumeAccumulator> {
    return await this.pumpProgram.account.globalVolumeAccumulator.fetch(
      GLOBAL_VOLUME_ACCUMULATOR_PDA,
    );
  }

  async fetchUserVolumeAccumulator(
    user: PublicKey,
  ): Promise<UserVolumeAccumulator | null> {
    return await this.pumpProgram.account.userVolumeAccumulator.fetchNullable(
      userVolumeAccumulatorPda(user),
    );
  }

  async fetchUserVolumeAccumulatorTotalStats(
    user: PublicKey,
  ): Promise<UserVolumeAccumulatorTotalStats> {
    const userVolumeAccumulator = (await this.fetchUserVolumeAccumulator(
      user,
    )) ?? {
      totalUnclaimedTokens: new BN(0),
      totalClaimedTokens: new BN(0),
      currentSolVolume: new BN(0),
    };

    const userVolumeAccumulatorAmm =
      (await this.pumpAmmSdk.fetchUserVolumeAccumulator(user)) ?? {
        totalUnclaimedTokens: new BN(0),
        totalClaimedTokens: new BN(0),
        currentSolVolume: new BN(0),
      };

    return {
      totalUnclaimedTokens: userVolumeAccumulator.totalUnclaimedTokens.add(
        userVolumeAccumulatorAmm.totalUnclaimedTokens,
      ),
      totalClaimedTokens: userVolumeAccumulator.totalClaimedTokens.add(
        userVolumeAccumulatorAmm.totalClaimedTokens,
      ),
      currentSolVolume: userVolumeAccumulator.currentSolVolume.add(
        userVolumeAccumulatorAmm.currentSolVolume,
      ),
    };
  }

  async collectCoinCreatorFeeInstructions(
    coinCreator: PublicKey,
    feePayer?: PublicKey,
  ): Promise<TransactionInstruction[]> {
    const quoteMint = NATIVE_MINT;
    const quoteTokenProgram = TOKEN_PROGRAM_ID;

    const coinCreatorVaultAuthority = coinCreatorVaultAuthorityPda(coinCreator);
    const coinCreatorVaultAta = coinCreatorVaultAtaPda(
      coinCreatorVaultAuthority,
      quoteMint,
      quoteTokenProgram,
    );

    const coinCreatorTokenAccount = getAssociatedTokenAddressSync(
      quoteMint,
      coinCreator,
      true,
      quoteTokenProgram,
    );
    const [coinCreatorVaultAtaAccountInfo, coinCreatorTokenAccountInfo] =
      await this.connection.getMultipleAccountsInfo([
        coinCreatorVaultAta,
        coinCreatorTokenAccount,
      ]);

    return [
      await this.offlinePumpProgram.methods
        .collectCreatorFee()
        .accountsPartial({
          creator: coinCreator,
        })
        .instruction(),
      ...(await PUMP_AMM_SDK.collectCoinCreatorFee(
        {
          coinCreator,
          quoteMint,
          quoteTokenProgram,
          coinCreatorVaultAuthority,
          coinCreatorVaultAta,
          coinCreatorTokenAccount,
          coinCreatorVaultAtaAccountInfo,
          coinCreatorTokenAccountInfo,
        },
        feePayer,
      )),
    ];
  }

  /**
   * Collects a creator's fees in one quote from the pump creator vault and
   * the pump-amm coin creator vault. `quoteTokenProgram` must be the program
   * that owns `quoteMint` (`fetchQuoteTokenProgram`). Assumes the creator's
   * quote ATA exists for a non-SOL quote: neither program creates it (see
   * `collectCoinCreatorFeeAllQuotesInstructions`, which does).
   */
  async collectCoinCreatorFeeV2Instructions(
    coinCreator: PublicKey,
    quoteMint: PublicKey,
    quoteTokenProgram: PublicKey,
    feePayer?: PublicKey,
  ): Promise<TransactionInstruction[]> {
    const coinCreatorVaultAuthority = coinCreatorVaultAuthorityPda(coinCreator);
    const coinCreatorVaultAta = coinCreatorVaultAtaPda(
      coinCreatorVaultAuthority,
      quoteMint,
      quoteTokenProgram,
    );

    const coinCreatorTokenAccount = getAssociatedTokenAddressSync(
      quoteMint,
      coinCreator,
      true,
      quoteTokenProgram,
    );
    const [coinCreatorVaultAtaAccountInfo, coinCreatorTokenAccountInfo] =
      await this.connection.getMultipleAccountsInfo([
        coinCreatorVaultAta,
        coinCreatorTokenAccount,
      ]);

    const pumpAmmInstructions = coinCreatorVaultAtaAccountInfo
      ? await PUMP_AMM_SDK.collectCoinCreatorFee(
          {
            coinCreator,
            quoteMint,
            quoteTokenProgram,
            coinCreatorVaultAuthority,
            coinCreatorVaultAta,
            coinCreatorTokenAccount,
            coinCreatorVaultAtaAccountInfo,
            coinCreatorTokenAccountInfo,
          },
          feePayer,
        )
      : [];

    return [
      await this.offlinePumpProgram.methods
        .collectCreatorFeeV2()
        .accountsPartial({
          creator: coinCreator,
          quoteMint,
          quoteTokenProgram,
          creatorVault: creatorVaultPda(coinCreator),
        })
        .instruction(),
      ...pumpAmmInstructions,
    ];
  }

  /**
   * Collects a creator's fees in every quote mint currently listed on `Global`
   * or in the `QuoteControl` PDA (`fetchSupportedQuoteMints`), plus
   * `extraQuoteMints`, from both the pump creator vault and the pump-amm coin
   * creator vault, into the creator's wallet and quote ATAs. For SOL: the
   * lamport vault (`collect_creator_fee`) and, when the AMM WSOL vault ATA
   * exists, the AMM leg (which wraps and unwraps by itself). For every other
   * quote, in this order: an idempotent create of the creator's quote ATA when
   * it is missing (neither program creates it), the pump
   * `collect_creator_fee_v2` leg only when the pump vault's quote ATA exists,
   * and the AMM leg only when its vault ATA exists; a quote with neither vault
   * ATA contributes nothing. "Exists" means a token account of the quote's
   * program: any other account at a vault ATA address is treated as absent
   * (the programs could not deserialize it), and one at the creator's ATA
   * address is created over. Three RPC round-trips: the supported mints, their
   * owners, then every vault and destination ATA (in batches of 100 keys).
   *
   * De-listing a mint from `QuoteControl` stops new creates only: curves
   * already quoted in it keep trading and accruing fees, and this method does
   * not know about them. Neither does it know about pump coins quoting the
   * creator's coins (never listed anywhere). Pass such mints (from an
   * indexer, or the creator's own coins' `bondingCurve.quoteMint`) as
   * `extraQuoteMints`. A listed or
   * extra mint whose account is missing or is not a token mint is skipped
   * (no ATA can exist for it, so nothing is lost).
   *
   * Each quote's instructions are contiguous, so the result can be split per
   * quote when it does not fit one transaction (up to four instructions for
   * SOL, three per token quote).
   *
   * @param feePayer - Signs and pays ATA rent; defaults to the creator.
   * @param extraQuoteMints - Quote mints to sweep in addition to the listed
   *   ones, e.g. de-listed mints the creator's coins are quoted in. SOL-like
   *   keys and duplicates are ignored.
   */
  async collectCoinCreatorFeeAllQuotesInstructions(
    coinCreator: PublicKey,
    feePayer?: PublicKey,
    extraQuoteMints: readonly PublicKey[] = [],
  ): Promise<TransactionInstruction[]> {
    const payer = feePayer ?? coinCreator;
    const supported = await this.fetchSupportedQuoteMints();
    const mints = extraQuoteMints
      .map((mint) => normalizeQuoteMint(mint))
      .reduce<PublicKey[]>(
        (all, mint) =>
          all.some((known) => known.equals(mint)) ? all : [...all, mint],
        supported.map(({ mint }) => mint),
      );
    const quotes = await this.fetchQuoteMintPrograms(mints);
    const coinCreatorVaultAuthority = coinCreatorVaultAuthorityPda(coinCreator);
    const creatorVault = creatorVaultPda(coinCreator);

    // Per quote: pump vault ATA (unused for SOL), AMM vault ATA, destination.
    const vaultAccounts = quotes.map(({ mint, quoteTokenProgram }) => ({
      pumpVaultAta: quoteAta(creatorVault, mint, quoteTokenProgram),
      ammVaultAta: coinCreatorVaultAtaPda(
        coinCreatorVaultAuthority,
        mint,
        quoteTokenProgram,
      ),
      creatorAta: getAssociatedTokenAddressSync(
        mint,
        coinCreator,
        true,
        quoteTokenProgram,
      ),
    }));
    const accountInfos = await getMultipleAccountsInfoChunked(
      this.connection,
      vaultAccounts.flatMap(({ pumpVaultAta, ammVaultAta, creatorAta }) => [
        pumpVaultAta,
        ammVaultAta,
        creatorAta,
      ]),
    );

    const instructions: TransactionInstruction[] = [];
    for (const [index, { mint, quoteTokenProgram }] of quotes.entries()) {
      const { ammVaultAta, creatorAta } = vaultAccounts[index];
      const [
        pumpVaultAtaAccountInfo,
        ammVaultAtaAccountInfo,
        creatorAtaAccountInfo,
      ] = accountInfos.slice(index * 3, index * 3 + 3);
      const isSol = mint.equals(NATIVE_MINT);
      const collectPump =
        isSol || isTokenAccount(pumpVaultAtaAccountInfo, quoteTokenProgram);
      const collectAmm = isTokenAccount(
        ammVaultAtaAccountInfo,
        quoteTokenProgram,
      );
      if (!collectPump && !collectAmm) {
        continue;
      }

      // The AMM SDK wraps/unwraps WSOL itself; for a token quote both programs
      // expect the creator's ATA to exist already.
      if (!isSol && !isTokenAccount(creatorAtaAccountInfo, quoteTokenProgram)) {
        instructions.push(
          createAssociatedTokenAccountIdempotentInstruction(
            payer,
            creatorAta,
            coinCreator,
            mint,
            quoteTokenProgram,
          ),
        );
      }
      if (collectPump) {
        instructions.push(
          isSol
            ? await this.offlinePumpProgram.methods
                .collectCreatorFee()
                .accountsPartial({ creator: coinCreator })
                .instruction()
            : await this.offlinePumpProgram.methods
                .collectCreatorFeeV2()
                .accountsPartial({
                  creator: coinCreator,
                  quoteMint: mint,
                  quoteTokenProgram,
                  creatorVault,
                })
                .instruction(),
        );
      }
      if (collectAmm) {
        instructions.push(
          ...(await PUMP_AMM_SDK.collectCoinCreatorFee(
            {
              coinCreator,
              quoteMint: mint,
              quoteTokenProgram,
              coinCreatorVaultAuthority,
              coinCreatorVaultAta: ammVaultAta,
              coinCreatorTokenAccount: creatorAta,
              coinCreatorVaultAtaAccountInfo: ammVaultAtaAccountInfo,
              coinCreatorTokenAccountInfo: creatorAtaAccountInfo,
            },
            feePayer,
          )),
        );
      }
    }

    return instructions;
  }

  /**
   * What a creator has waiting in each quote mint currently listed on `Global`
   * or in the `QuoteControl` PDA (`fetchSupportedQuoteMints`): the pump
   * creator vault (lamports above rent for SOL, the vault ATA's token amount
   * otherwise) and the pump-amm coin creator vault ATA. An account at a vault
   * ATA address that is not a token account of the quote's program counts as
   * zero. Up to four RPC round-trips (the vault batch in slices of 100 keys).
   *
   * Like `collectCoinCreatorFeeAllQuotesInstructions`, this does not see fees
   * in a mint that has since been de-listed, or in a pump coin quoting the
   * creator's coins: pass those as `extraQuoteMints` (reported with source
   * `extra`; SOL-like keys, duplicates and listed mints are ignored). A mint whose
   * account is missing or is not a token mint is left out.
   */
  async getCreatorVaultQuoteBalances(
    creator: PublicKey,
    extraQuoteMints: readonly PublicKey[] = [],
  ): Promise<CreatorVaultQuoteBalance[]> {
    const listed = await this.fetchSupportedQuoteMintPrograms();
    const extras = await this.fetchQuoteMintPrograms(
      extraQuoteMints
        .map((mint) => normalizeQuoteMint(mint))
        .filter(
          (mint, index, all) =>
            !mint.equals(NATIVE_MINT) &&
            all.findIndex((other) => other.equals(mint)) === index &&
            !listed.some((entry) => entry.mint.equals(mint)),
        ),
    );
    const quotes = [
      ...listed,
      ...extras.map((extra) => ({ ...extra, source: "extra" as const })),
    ];
    const coinCreatorVaultAuthority = coinCreatorVaultAuthorityPda(creator);
    const creatorVault = creatorVaultPda(creator);

    const vaultAccounts = quotes.map(({ mint, quoteTokenProgram }) => ({
      pumpVaultAta: quoteAta(creatorVault, mint, quoteTokenProgram),
      ammVaultAta: coinCreatorVaultAtaPda(
        coinCreatorVaultAuthority,
        mint,
        quoteTokenProgram,
      ),
    }));
    const [creatorVaultAccountInfo, ...accountInfos] =
      await getMultipleAccountsInfoChunked(this.connection, [
        creatorVault,
        ...vaultAccounts.flatMap(({ pumpVaultAta, ammVaultAta }) => [
          pumpVaultAta,
          ammVaultAta,
        ]),
      ]);
    const solVaultBalance = await this.creatorVaultLamportsAboveRent(
      creatorVaultAccountInfo,
    );

    return quotes.map(({ mint, source, quoteTokenProgram }, index) => {
      const { pumpVaultAta, ammVaultAta } = vaultAccounts[index];
      const [pumpVaultAtaAccountInfo, ammVaultAtaAccountInfo] =
        accountInfos.slice(index * 2, index * 2 + 2);
      const pumpVault = mint.equals(NATIVE_MINT)
        ? solVaultBalance
        : tokenAccountAmount(
            pumpVaultAta,
            pumpVaultAtaAccountInfo,
            quoteTokenProgram,
          );
      const ammVault = tokenAccountAmount(
        ammVaultAta,
        ammVaultAtaAccountInfo,
        quoteTokenProgram,
      );
      return {
        mint,
        source,
        quoteTokenProgram,
        pumpVault,
        ammVault,
        total: pumpVault.add(ammVault),
      };
    });
  }

  // Every supported quote mint with the program that owns it, dropping the
  // entries `fetchQuoteMintPrograms` cannot resolve.
  private async fetchSupportedQuoteMintPrograms(): Promise<
    (SupportedQuoteMint & QuoteMintProgram)[]
  > {
    const supported = await this.fetchSupportedQuoteMints();
    const quotes = await this.fetchQuoteMintPrograms(
      supported.map(({ mint }) => mint),
    );
    return quotes.map(({ mint, quoteTokenProgram }) => ({
      // Present by construction: `fetchQuoteMintPrograms` only drops entries.
      ...supported.find((entry) => entry.mint.equals(mint))!,
      quoteTokenProgram,
    }));
  }

  // `mints` (normalized; SOL as `NATIVE_MINT`) with the program that owns each,
  // in order: SOL without a lookup, the others from one chunked fetch of their
  // mint accounts. A mint whose account is missing or is owned by neither token
  // program is dropped rather than thrown on: `add_quote_control_mint` does not
  // check the mint exists, and no ATA can exist for such a mint, so a sweep or
  // balance over the remaining mints is complete.
  private async fetchQuoteMintPrograms(
    mints: readonly PublicKey[],
  ): Promise<QuoteMintProgram[]> {
    const tokenMints = mints.filter((mint) => !mint.equals(NATIVE_MINT));
    const mintAccountInfos = await getMultipleAccountsInfoChunked(
      this.connection,
      tokenMints,
    );
    const programs = new Map(
      tokenMints.flatMap((mint, index) => {
        const owner = mintAccountInfos[index]?.owner;
        return owner && isQuoteTokenProgram(owner)
          ? [[mint.toBase58(), owner] as const]
          : [];
      }),
    );
    return mints.flatMap((mint) => {
      if (mint.equals(NATIVE_MINT)) {
        return [{ mint, quoteTokenProgram: TOKEN_PROGRAM_ID }];
      }
      const quoteTokenProgram = programs.get(mint.toBase58());
      return quoteTokenProgram ? [{ mint, quoteTokenProgram }] : [];
    });
  }

  // `getCreatorVaultBalance` over an already fetched vault account.
  private async creatorVaultLamportsAboveRent(
    accountInfo: AccountInfo<Buffer> | null,
  ): Promise<BN> {
    if (accountInfo === null) {
      return new BN(0);
    }

    const rentExemptionLamports =
      await this.connection.getMinimumBalanceForRentExemption(
        accountInfo.data.length,
      );

    if (accountInfo.lamports < rentExemptionLamports) {
      return new BN(0);
    }

    return new BN(accountInfo.lamports - rentExemptionLamports);
  }

  /**
   * `PumpSdk.adminCtoInstruction` for `mint`, with the signer defaulting to
   * `Global.adminSetCreatorAuthority` and every other account resolved from
   * chain: `Global` and the curve in one round-trip, plus the quote mint's
   * owner program for a token quote, and the canonical pool. Returned as
   * `[setComputeUnitLimit(ADMIN_CTO_COMPUTE_UNIT_LIMIT), ...sweeps,
   * admin_cto]`, the sweeps present only when a creator bucket is nonzero
   * (see below).
   *
   * Rejects up front, with typed errors, what the program would reject
   * (`admin_cto.rs`): a mayhem coin (`CtoNotAllowedForMayhemCoinError`, 6088),
   * changing a holder-reward coin's creator (`HolderRewardCreatorImmutableError`,
   * 6083; only `isHolderReward: true` again is allowed), converting while
   * `Global.isHolderRewardEnabled` is off (`HolderRewardDisabledError`, 6084),
   * a missing `newCreator` on the new-creator path or a present one on the
   * holder path (6089 / 6090), and for a `creatorFeeBps`: a SOL or
   * `Global`-whitelisted quote (`CreatorFeeNotConfigurableForQuoteError`,
   * 6091), a coin that stays cashback
   * (`CreatorFeeNotAllowedForCashbackCoinError`, 6080), the gate off
   * (`CreatorFeeNotConfigurableError`, 6077) and a rate outside
   * `1..=Global.maxConfigurableCreatorFeeBps` (`CreatorFeeBpsOutOfRangeError`,
   * 6078). The program alone judges the rest (a `newCreator` equal to a PDA,
   * a frozen shared vault, ...).
   *
   * Creator fees left on the curve by v3 trades, or in the canonical pool by
   * pump-amm v2 trades, block a CTO (6095 / pump-amm 6081
   * `CreatorFeesNotSwept`): when either bucket is nonzero the matching
   * `sweep_creator_fee` goes in front of `admin_cto`, paid by the CTO
   * authority, so they reach the outgoing creator first. That takes one more
   * round-trip, for the pool.
   */
  async adminCtoInstructions(
    mint: PublicKey,
    {
      isHolderReward,
      creatorFeeBps,
      newCreator,
      adminSetCreatorAuthority,
    }: {
      isHolderReward?: boolean;
      creatorFeeBps?: BN;
      newCreator?: PublicKey;
      adminSetCreatorAuthority?: PublicKey;
    },
  ): Promise<TransactionInstruction[]> {
    const { global, bondingCurve, quoteMint, quoteTokenProgram } =
      await this.fetchCurveWithQuote(mint);

    if (bondingCurve.isMayhemMode) {
      throw new CtoNotAllowedForMayhemCoinError(mint);
    }
    const toHolder = isHolderReward === true;
    if (bondingCurve.isHolderReward && !toHolder) {
      throw new HolderRewardCreatorImmutableError(mint);
    }
    if (toHolder) {
      if (!bondingCurve.isHolderReward && !global.isHolderRewardEnabled) {
        throw new HolderRewardDisabledError();
      }
      if (newCreator) {
        throw new Error(
          "newCreator must be omitted when converting to holder rewards",
        );
      }
    } else if (!newCreator) {
      throw new Error(
        "newCreator is required unless converting to holder rewards",
      );
    }
    if (creatorFeeBps) {
      const quoteIsSolOrWhitelisted =
        isLegacyQuoteMint(bondingCurve.quoteMint) ||
        global.whitelistedQuoteMints.some((whitelisted) =>
          whitelisted.equals(bondingCurve.quoteMint),
        );
      if (quoteIsSolOrWhitelisted) {
        throw new CreatorFeeNotConfigurableForQuoteError(quoteMint);
      }
      // The holder path clears cashback; the new-creator path keeps it.
      if (bondingCurve.isCashbackCoin && !toHolder) {
        throw new CreatorFeeNotAllowedForCashbackCoinError(mint);
      }
      if (!global.creatorFeeConfigurable) {
        throw new CreatorFeeNotConfigurableError();
      }
      if (
        creatorFeeBps.ltn(1) ||
        creatorFeeBps.gt(global.maxConfigurableCreatorFeeBps)
      ) {
        throw new CreatorFeeBpsOutOfRangeError(
          creatorFeeBps,
          global.maxConfigurableCreatorFeeBps,
        );
      }
    }

    const authority =
      adminSetCreatorAuthority ?? global.adminSetCreatorAuthority;
    const poolAccountInfo = await this.connection.getAccountInfo(
      canonicalPumpPoolPdaWithQuote(mint, quoteMint),
    );

    return [
      ComputeBudgetProgram.setComputeUnitLimit({
        units: ADMIN_CTO_COMPUTE_UNIT_LIMIT,
      }),
      ...(await creatorFeeSweepInstructions({
        payer: authority,
        mint,
        bondingCurve,
        poolAccountInfo,
        quoteMint,
        quoteTokenProgram,
      })),
      await PUMP_SDK.adminCtoInstruction({
        adminSetCreatorAuthority: authority,
        mint,
        currentCreator: bondingCurve.creator,
        quoteMint,
        quoteTokenProgram,
        isHolderReward,
        creatorFeeBps,
        newCreator,
      }),
    ];
  }

  /**
   * `PumpSdk.updateHolderRewardConfigInstruction` with `authority` defaulting
   * to the current `Global.authority`, the only key the program accepts.
   */
  async adminUpdateHolderRewardConfigInstruction({
    isHolderRewardEnabled,
    holderRewardClaimAuthority,
    authority,
  }: {
    isHolderRewardEnabled: boolean;
    holderRewardClaimAuthority: PublicKey;
    authority?: PublicKey;
  }): Promise<TransactionInstruction> {
    return await PUMP_SDK.updateHolderRewardConfigInstruction({
      authority: authority ?? (await this.fetchGlobal()).authority,
      isHolderRewardEnabled,
      holderRewardClaimAuthority,
    });
  }

  /**
   * `PumpSdk.distributeFeeToHoldersInstruction` for `mint`, with the signer
   * defaulting to `Global.holderRewardClaimAuthority`, the quote read from
   * the curve, and the PDA's quote ATA passed as `holderRewardsTokenAccount`
   * when it exists (on a SOL quote it is a parked WSOL account the program
   * sweeps first; on a token quote it is the payout source and this throws
   * when it is missing, since there is nothing to pay from). Throws when the
   * coin is not a holder-reward coin.
   */
  async distributeFeeToHoldersInstructions(
    mint: PublicKey,
    recipients: readonly { owner: PublicKey; amount: BN }[],
    holderRewardClaimAuthority?: PublicKey,
  ): Promise<TransactionInstruction[]> {
    const { global, bondingCurve, quoteMint, quoteTokenProgram } =
      await this.fetchCurveWithQuote(mint);
    if (!bondingCurve.isHolderReward) {
      throw new Error(
        `Mint ${mint.toBase58()} is not a holder-reward coin; nothing to distribute`,
      );
    }
    const holderRewardsAta = quoteAta(
      holderRewardsPda(mint),
      quoteMint,
      quoteTokenProgram,
    );
    const holderRewardsAtaAccountInfo =
      await this.connection.getAccountInfo(holderRewardsAta);
    if (!holderRewardsAtaAccountInfo && !quoteMint.equals(NATIVE_MINT)) {
      throw new Error(
        `Holder-rewards token account ${holderRewardsAta.toBase58()} does not exist; collect the coin's creator fees onto the PDA first`,
      );
    }

    return [
      await PUMP_SDK.distributeFeeToHoldersInstruction({
        holderRewardClaimAuthority:
          holderRewardClaimAuthority ?? global.holderRewardClaimAuthority,
        mint,
        quoteMint,
        quoteTokenProgram,
        recipients,
        holderRewardsTokenAccount: holderRewardsAtaAccountInfo
          ? holderRewardsAta
          : undefined,
      }),
    ];
  }

  /**
   * `Global` and `mint`'s curve in one round-trip, with the curve's quote
   * normalized (`NATIVE_MINT` for SOL curves) and the program that owns it
   * (a second round-trip for a token quote, none for SOL).
   */
  private async fetchCurveWithQuote(mint: PublicKey): Promise<{
    global: Global;
    bondingCurve: BondingCurve;
    quoteMint: PublicKey;
    quoteTokenProgram: PublicKey;
  }> {
    const [globalAccountInfo, bondingCurveAccountInfo] =
      await this.connection.getMultipleAccountsInfo([
        GLOBAL_PDA,
        bondingCurvePda(mint),
      ]);
    if (!globalAccountInfo) {
      throw new Error(`Global account not found: ${GLOBAL_PDA.toBase58()}`);
    }
    if (!bondingCurveAccountInfo) {
      throw new Error(
        `Bonding curve account not found for mint: ${mint.toBase58()}`,
      );
    }
    const global = PUMP_SDK.decodeGlobal(globalAccountInfo);
    const bondingCurve = PUMP_SDK.decodeBondingCurve(bondingCurveAccountInfo);
    const quoteMint = normalizeQuoteMint(bondingCurve.quoteMint);
    return {
      global,
      bondingCurve,
      quoteMint,
      quoteTokenProgram: await this.fetchQuoteTokenProgram(quoteMint),
    };
  }

  /**
   * `PumpSdk.setQuoteControlAdminInstruction` with `authority` defaulting to
   * the current `Global.authority`, the only key the program accepts.
   */
  async adminSetQuoteControlAdminInstruction({
    newAdmin,
    authority,
  }: {
    newAdmin: PublicKey;
    authority?: PublicKey;
  }): Promise<TransactionInstruction> {
    return await PUMP_SDK.setQuoteControlAdminInstruction({
      authority: authority ?? (await this.fetchGlobal()).authority,
      newAdmin,
    });
  }

  /**
   * `PumpSdk.addQuoteControlMintInstruction` with `authority` defaulting to
   * the current `Global.authority` (pass `QuoteControl.admin` to sign as the
   * delegated admin instead).
   */
  async adminAddQuoteControlMintInstruction({
    quoteMint,
    initialVirtualQuoteReserves,
    authority,
  }: {
    quoteMint: PublicKey;
    initialVirtualQuoteReserves: BN;
    authority?: PublicKey;
  }): Promise<TransactionInstruction> {
    return await PUMP_SDK.addQuoteControlMintInstruction({
      authority: authority ?? (await this.fetchGlobal()).authority,
      quoteMint,
      initialVirtualQuoteReserves,
    });
  }

  /**
   * `PumpSdk.removeQuoteControlMintInstruction` with `authority` defaulting
   * to the current `Global.authority`.
   */
  async adminRemoveQuoteControlMintInstruction({
    quoteMint,
    authority,
  }: {
    quoteMint: PublicKey;
    authority?: PublicKey;
  }): Promise<TransactionInstruction> {
    return await PUMP_SDK.removeQuoteControlMintInstruction({
      authority: authority ?? (await this.fetchGlobal()).authority,
      quoteMint,
    });
  }

  /**
   * `PumpSdk.updateCreatorFeeConfigInstruction` with `authority` defaulting
   * to the current `Global.authority`, the only key the program accepts.
   */
  async adminUpdateCreatorFeeConfigInstruction({
    creatorFeeConfigurable,
    maxConfigurableCreatorFeeBps,
    authority,
  }: {
    creatorFeeConfigurable: boolean;
    maxConfigurableCreatorFeeBps: BN;
    authority?: PublicKey;
  }): Promise<TransactionInstruction> {
    return await PUMP_SDK.updateCreatorFeeConfigInstruction({
      authority: authority ?? (await this.fetchGlobal()).authority,
      creatorFeeConfigurable,
      maxConfigurableCreatorFeeBps,
    });
  }

  /**
   * `PumpSdk.setExoticFlatFeesInstruction` with `admin` defaulting to the
   * current `FeeConfig.admin`.
   */
  async adminSetExoticFlatFeesInstruction({
    exoticFlatFees,
    admin,
  }: {
    exoticFlatFees: Fees;
    admin?: PublicKey;
  }): Promise<TransactionInstruction> {
    return await PUMP_SDK.setExoticFlatFeesInstruction({
      admin: admin ?? (await this.fetchFeeConfig()).admin,
      exoticFlatFees,
    });
  }

  /**
   * `PumpSdk.setMaxCurveDepthInstruction` with `authority` defaulting to the
   * current `Global.authority`, the only key the program accepts.
   */
  async adminSetMaxCurveDepthInstruction({
    maxCurveDepth,
    authority,
  }: {
    maxCurveDepth: number;
    authority?: PublicKey;
  }): Promise<TransactionInstruction> {
    return await PUMP_SDK.setMaxCurveDepthInstruction({
      authority: authority ?? (await this.fetchGlobal()).authority,
      maxCurveDepth,
    });
  }

  /**
   * The hops of a `multi_hop_swap` route along `path`, each venue picked
   * from chain: a coin's bonding curve while it trades and is quoted in the
   * previous mint (a token, not SOL), else its canonical pump-amm pool.
   *
   * @param path - Mints in trade order. A buy starts at the user's currency
   *   and climbs a quote chain (`[USDC, X, Y]`: X quoted in USDC, Y in X); a
   *   sell is the reverse (`[Y, X, USDC]`). SOL may be WSOL or the zero key.
   * @throws when a pair has neither a tradable curve nor a pool.
   */
  async resolveMultiHopRoute(
    path: readonly PublicKey[],
    side: MultiHopSide,
  ): Promise<MultiHopHop[]> {
    if (path.length < 2) {
      throw new Error("A route needs at least two mints");
    }
    // SOL as curves store it (the zero key) is WSOL here.
    const mints = path.map((mint) => normalizeQuoteMint(mint));
    const pairs = mints.slice(0, -1).map((mint, index) => {
      const next = mints[index + 1];
      return side === "buy"
        ? { baseMint: next, quoteMint: mint }
        : { baseMint: mint, quoteMint: next };
    });
    const infos = await getMultipleAccountsInfoChunked(this.connection, [
      ...mints,
      ...pairs.map(({ baseMint }) => bondingCurvePda(baseMint)),
      ...pairs.map(({ baseMint, quoteMint }) =>
        canonicalPumpPoolPdaWithQuote(baseMint, quoteMint),
      ),
    ]);
    const programOf = (mint: PublicKey): PublicKey => {
      const info = infos[mints.findIndex((known) => known.equals(mint))];
      if (!info) {
        throw new Error(`Mint account not found: ${mint.toBase58()}`);
      }
      return quoteTokenProgramOf(mint, info);
    };
    return pairs.map(({ baseMint, quoteMint }, index) => {
      const curveInfo = infos[mints.length + index];
      const poolInfo = infos[mints.length + pairs.length + index];
      const curve =
        curveInfo && curveInfo.owner.equals(PUMP_PROGRAM_ID)
          ? PUMP_SDK.decodeBondingCurve(curveInfo)
          : null;
      const curveTradable =
        curve !== null &&
        !curve.complete &&
        !isLegacyQuoteMint(quoteMint) &&
        curve.quoteMint.equals(quoteMint);
      if (!curveTradable && !poolInfo) {
        throw new Error(
          `No tradable curve or canonical pool for ${baseMint.toBase58()} / ${quoteMint.toBase58()}`,
        );
      }
      return {
        venue: curveTradable ? ("curve" as const) : ("pool" as const),
        baseMint,
        quoteMint,
        baseTokenProgram: programOf(baseMint),
        quoteTokenProgram: programOf(quoteMint),
      };
    });
  }

  /**
   * What a `multi_hop_swap` of `amountIn` would pay out, by simulating
   * `PumpSdk.multiHopSwapInstructions` (with a 1,400,000 CU limit, the SOL
   * output left wrapped so it can be read) for `user`, who must hold the
   * input. Use it for `minAmountOut` less slippage. Throws with the program
   * logs when the simulation fails, and when the route does not fit a
   * transaction without `addressLookupTables`.
   */
  async simulateMultiHopSwap({
    user,
    hops,
    side,
    amountIn,
    buybackFeeRecipient,
    addressLookupTables = [],
  }: {
    user: PublicKey;
    hops: readonly MultiHopHop[];
    side: MultiHopSide;
    amountIn: BN;
    buybackFeeRecipient?: PublicKey;
    /** Needed for routes past three hops, as for the real transaction. */
    addressLookupTables?: AddressLookupTableAccount[];
  }): Promise<BN> {
    const { output } = multiHopRouteEnds(hops, side);
    const outAta = quoteAta(user, output.mint, output.tokenProgram);
    const instructions = await PUMP_SDK.multiHopSwapInstructions({
      user,
      hops,
      side,
      amountIn,
      minAmountOut: new BN(1),
      buybackFeeRecipient,
    });
    if (output.mint.equals(NATIVE_MINT)) {
      // Keep the output WSOL account open so its balance can be read.
      instructions.pop();
    }
    const preInfo = await this.connection.getAccountInfo(outAta);
    const before = tokenAccountAmount(outAta, preInfo, output.tokenProgram);
    const transaction = new VersionedTransaction(
      new TransactionMessage({
        payerKey: user,
        // Replaced by the node (`replaceRecentBlockhash`).
        recentBlockhash: PublicKey.default.toBase58(),
        instructions: [
          ComputeBudgetProgram.setComputeUnitLimit({ units: 1_400_000 }),
          ...instructions,
        ],
      }).compileToV0Message(addressLookupTables),
    );
    try {
      transaction.serialize();
    } catch (error) {
      throw new Error(
        `multi_hop_swap route of ${hops.length} hops does not fit a transaction; pass addressLookupTables (${String(error)})`,
      );
    }
    const { value } = await this.connection.simulateTransaction(transaction, {
      sigVerify: false,
      replaceRecentBlockhash: true,
      accounts: { encoding: "base64", addresses: [outAta.toBase58()] },
    });
    const after = value.accounts?.[0];
    if (value.err || !after) {
      throw new Error(
        `multi_hop_swap simulation failed: ${JSON.stringify(value.err)}\n${(value.logs ?? []).join("\n")}`,
      );
    }
    const afterInfo: AccountInfo<Buffer> = {
      ...after,
      owner: new PublicKey(after.owner),
      data: Buffer.from(after.data[0], "base64"),
    };
    return tokenAccountAmount(outAta, afterInfo, output.tokenProgram).sub(
      before,
    );
  }

  async getCreatorVaultBalance(creator: PublicKey): Promise<BN> {
    const creatorVault = creatorVaultPda(creator);
    const accountInfo = await this.connection.getAccountInfo(creatorVault);
    return await this.creatorVaultLamportsAboveRent(accountInfo);
  }

  async getCreatorVaultBalanceBothPrograms(creator: PublicKey): Promise<BN> {
    const balance = await this.getCreatorVaultBalance(creator);
    const ammBalance =
      await this.pumpAmmSdk.getCoinCreatorVaultBalance(creator);
    return balance.add(ammBalance);
  }

  async adminUpdateTokenIncentives(
    startTime: BN,
    endTime: BN,
    dayNumber: BN,
    tokenSupplyPerDay: BN,
    secondsInADay: BN = new BN(86_400),
    mint: PublicKey = PUMP_TOKEN_MINT,
    tokenProgram: PublicKey = TOKEN_2022_PROGRAM_ID,
  ): Promise<TransactionInstruction> {
    const { authority } = await this.fetchGlobal();

    return await this.offlinePumpProgram.methods
      .adminUpdateTokenIncentives(
        startTime,
        endTime,
        secondsInADay,
        dayNumber,
        tokenSupplyPerDay,
      )
      .accountsPartial({
        authority,
        mint,
        tokenProgram,
      })
      .instruction();
  }

  async adminUpdateTokenIncentivesBothPrograms(
    startTime: BN,
    endTime: BN,
    dayNumber: BN,
    tokenSupplyPerDay: BN,
    secondsInADay: BN = new BN(86_400),
    mint: PublicKey = PUMP_TOKEN_MINT,
    tokenProgram: PublicKey = TOKEN_2022_PROGRAM_ID,
  ): Promise<TransactionInstruction[]> {
    return [
      await this.adminUpdateTokenIncentives(
        startTime,
        endTime,
        dayNumber,
        tokenSupplyPerDay,
        secondsInADay,
        mint,
        tokenProgram,
      ),
      await this.pumpAmmAdminSdk.adminUpdateTokenIncentives(
        startTime,
        endTime,
        dayNumber,
        tokenSupplyPerDay,
        secondsInADay,
        mint,
        tokenProgram,
      ),
    ];
  }

  async claimTokenIncentives(
    user: PublicKey,
    payer: PublicKey,
  ): Promise<TransactionInstruction[]> {
    const { mint } = await this.fetchGlobalVolumeAccumulator();

    if (mint.equals(PublicKey.default)) {
      return [];
    }

    const [mintAccountInfo, userAccumulatorAccountInfo] =
      await this.connection.getMultipleAccountsInfo([
        mint,
        userVolumeAccumulatorPda(user),
      ]);

    if (!mintAccountInfo) {
      return [];
    }

    if (!userAccumulatorAccountInfo) {
      return [];
    }

    return [
      await this.offlinePumpProgram.methods
        .claimTokenIncentives()
        .accountsPartial({
          user,
          payer,
          mint,
          tokenProgram: mintAccountInfo.owner,
        })
        .instruction(),
    ];
  }

  async claimTokenIncentivesBothPrograms(
    user: PublicKey,
    payer: PublicKey,
  ): Promise<TransactionInstruction[]> {
    return [
      ...(await this.claimTokenIncentives(user, payer)),
      ...(await this.pumpAmmSdk.claimTokenIncentives(user, payer)),
    ];
  }

  async getTotalUnclaimedTokens(user: PublicKey): Promise<BN> {
    const [
      globalVolumeAccumulatorAccountInfo,
      userVolumeAccumulatorAccountInfo,
    ] = await this.connection.getMultipleAccountsInfo([
      GLOBAL_VOLUME_ACCUMULATOR_PDA,
      userVolumeAccumulatorPda(user),
    ]);

    if (
      !globalVolumeAccumulatorAccountInfo ||
      !userVolumeAccumulatorAccountInfo
    ) {
      return new BN(0);
    }

    const globalVolumeAccumulator = PUMP_SDK.decodeGlobalVolumeAccumulator(
      globalVolumeAccumulatorAccountInfo,
    );
    const userVolumeAccumulator = PUMP_SDK.decodeUserVolumeAccumulator(
      userVolumeAccumulatorAccountInfo,
    );

    return totalUnclaimedTokens(globalVolumeAccumulator, userVolumeAccumulator);
  }

  async getTotalUnclaimedTokensBothPrograms(user: PublicKey): Promise<BN> {
    return (await this.getTotalUnclaimedTokens(user)).add(
      await this.pumpAmmSdk.getTotalUnclaimedTokens(user),
    );
  }

  async getCurrentDayTokens(user: PublicKey): Promise<BN> {
    const [
      globalVolumeAccumulatorAccountInfo,
      userVolumeAccumulatorAccountInfo,
    ] = await this.connection.getMultipleAccountsInfo([
      GLOBAL_VOLUME_ACCUMULATOR_PDA,
      userVolumeAccumulatorPda(user),
    ]);

    if (
      !globalVolumeAccumulatorAccountInfo ||
      !userVolumeAccumulatorAccountInfo
    ) {
      return new BN(0);
    }

    const globalVolumeAccumulator = PUMP_SDK.decodeGlobalVolumeAccumulator(
      globalVolumeAccumulatorAccountInfo,
    );
    const userVolumeAccumulator = PUMP_SDK.decodeUserVolumeAccumulator(
      userVolumeAccumulatorAccountInfo,
    );

    return currentDayTokens(globalVolumeAccumulator, userVolumeAccumulator);
  }

  async getCurrentDayTokensBothPrograms(user: PublicKey): Promise<BN> {
    return (await this.getCurrentDayTokens(user)).add(
      await this.pumpAmmSdk.getCurrentDayTokens(user),
    );
  }

  async syncUserVolumeAccumulatorBothPrograms(
    user: PublicKey,
  ): Promise<TransactionInstruction[]> {
    return [
      await PUMP_SDK.syncUserVolumeAccumulator(user),
      await PUMP_AMM_SDK.syncUserVolumeAccumulator(user),
    ];
  }

  /**
   * Gets the minimum distributable fee for a token's fee sharing configuration.
   *
   * This method handles both graduated (AMM) and non-graduated (bonding curve) tokens.
   * For graduated tokens, it automatically consolidates fees from the AMM vault before
   * calculating the minimum distributable fee.
   *
   * On a SOL coin, creator fees v3 trades (curve) or pump-amm v2 trades (pool)
   * left un-swept are added to `distributableFees`, and `canDistribute`
   * reflects them: `buildDistributeCreatorFeesInstructions` sweeps them into
   * the vault first.
   *
   * @param mint - The mint address of the token
   * @param simulationSigner - Optional signer address for transaction simulation.
   *                           Must have a non-zero SOL balance. Defaults to a known funded address.
   * @param options - Quote-mint-specific parameters. Without them the coin is
   *   treated as SOL-quoted, exactly as before these options existed.
   * @param options.quoteMint - The coin's quote mint (`bondingCurve.quoteMint`
   *   can be passed as is). Selects the canonical pool, so `isGraduated` is
   *   right for a non-SOL coin, and the consolidation instruction
   *   (`transferCreatorFeesToPumpV2`). Note that the on-chain
   *   `get_minimum_distributable_fee` view reads the lamport creator vault
   *   only, so for a non-SOL quote `minimumRequired`, `distributableFees` and
   *   `canDistribute` still describe SOL fees, not the quote-token fees (the
   *   consolidation moves tokens the view does not look at); the result's
   *   `feesQuoteMint` says which mint the figures are in. Use
   *   `getCreatorVaultQuoteBalances` for token-quote amounts.
   * @param options.quoteTokenProgram - The program that owns `quoteMint`;
   *   fetched from the mint when omitted for a non-SOL quote (one extra
   *   round-trip).
   * @param options.payer - Signer for the V2 consolidation instruction, which
   *   may initialize the pump vault ATA; defaults to `simulationSigner`.
   * @returns The minimum distributable fee information including whether distribution is possible
   */
  async getMinimumDistributableFee(
    mint: PublicKey,
    simulationSigner: PublicKey = new PublicKey(
      "UqN2p5bAzBqYdHXcgB6WLtuVrdvmy9JSAtgqZb3CMKw",
    ),
    options: {
      quoteMint?: PublicKey;
      quoteTokenProgram?: PublicKey;
      payer?: PublicKey;
    } = {},
  ): Promise<MinimumDistributableFeeResult> {
    const state = await this.fetchDistributionState(mint, options);
    const payer = options.payer ?? simulationSigner;
    const isGraduated = state.poolAccountInfo !== null;

    const instructions: TransactionInstruction[] = [];
    if (isGraduated && state.ammVaultAtaInfo) {
      instructions.push(
        await this.consolidationInstruction(mint, payer, state),
      );
    }
    instructions.push(
      await PUMP_SDK.getMinimumDistributableFee({
        mint,
        sharingConfig: state.sharingConfig,
        sharingConfigAddress: state.sharingConfigPubkey,
      }),
    );

    const { blockhash } = await this.connection.getLatestBlockhash();

    const tx = new VersionedTransaction(
      new TransactionMessage({
        payerKey: simulationSigner,
        recentBlockhash: blockhash,
        instructions,
      }).compileToV0Message(),
    );

    const result = await this.connection.simulateTransaction(tx);

    let minimumDistributableFee: MinimumDistributableFeeEvent = {
      minimumRequired: new BN(0),
      distributableFees: new BN(0),
      canDistribute: false,
    };

    if (!result.value.err) {
      const [data, encoding] = result.value.returnData?.data ?? [];
      if (data) {
        const buffer = Buffer.from(data, encoding as BufferEncoding);
        minimumDistributableFee =
          PUMP_SDK.decodeMinimumDistributableFee(buffer);
      }
    }

    // Un-swept SOL buckets reach the vault with the sweeps
    // `buildDistributeCreatorFeesInstructions` puts first. The view's
    // `distributable_fees` is the vault's lamports above its rent floor and
    // `minimum_required` is its threshold plus that floor, so both adjust
    // exactly.
    const unswept = state.isNativeQuote
      ? (state.bondingCurve?.creatorFee ?? new BN(0)).add(
          poolCreatorFees(state.poolAccountInfo),
        )
      : new BN(0);
    if (!result.value.err && !unswept.isZero()) {
      const vaultRent = new BN(
        await this.connection.getMinimumBalanceForRentExemption(0),
      );
      const distributableFees =
        minimumDistributableFee.distributableFees.add(unswept);
      minimumDistributableFee = {
        ...minimumDistributableFee,
        distributableFees,
        canDistribute: distributableFees.gte(
          BN.max(
            minimumDistributableFee.minimumRequired.sub(vaultRent),
            new BN(0),
          ),
        ),
      };
    }

    return {
      ...minimumDistributableFee,
      isGraduated,
      // The only view the program has; a quote-aware one is a program change.
      feesQuoteMint: NATIVE_MINT,
    };
  }

  /**
   * Gets the instructions to distribute creator fees for a token's fee sharing configuration.
   *
   * This method handles both graduated (AMM) and non-graduated (bonding curve) tokens.
   * For graduated tokens, it automatically includes an instruction to consolidate fees
   * from the AMM vault before distributing.
   *
   * Creator fees left on the curve (v3 trades) or in the pool (pump-amm v2
   * trades) are swept first: the first `sweepCount` instructions. A large
   * sharing config can push the whole list past one transaction; then send
   * those sweeps in a transaction of their own first (a trade landing in
   * between can leave the curve bucket nonzero again, 6095
   * `CreatorFeesNotSwept`; rebuild then).
   *
   * @param mint - The mint address of the token
   * @param options - Optional quote-mint-specific parameters
   * @param options.quoteTokenProgram - The program that owns `quoteMint`.
   *   Fetched from the mint when omitted for a non-SOL quote (one extra
   *   round-trip before the account batch, which derives every ATA from it);
   *   `TOKEN_PROGRAM_ID` for SOL.
   * @param options.payer - Transaction signer. Required when `quoteMint` is not
   *   `NATIVE_MINT`: pays rent for the vault/shareholder ATAs the V2
   *   consolidation and distribution instructions may initialize. Also
   *   required, whatever the quote, when a sweep is needed (it signs and pays
   *   the sweeps).
   * @param options.quoteMint - The coin's quote mint
   * @returns The instructions to distribute creator fees and whether the token is graduated
   */
  async buildDistributeCreatorFeesInstructions(
    mint: PublicKey,
    options: {
      quoteMint?: PublicKey;
      quoteTokenProgram?: PublicKey;
      payer?: PublicKey;
    } = {},
  ): Promise<DistributeCreatorFeeResult> {
    const { payer } = options;
    if (!normalizeQuoteMint(options.quoteMint).equals(NATIVE_MINT) && !payer) {
      throw new Error(
        "payer is required when quoteMint is not NATIVE_MINT (V2 instructions may initialize ATAs)",
      );
    }
    const state = await this.fetchDistributionState(mint, options);
    const {
      quoteMint,
      isNativeQuote,
      quoteTokenProgram,
      sharingConfig,
      sharingConfigPubkey,
      poolAccountInfo,
    } = state;

    // Creator fees still on the curve (v3) or in the pool (pump-amm v2) are
    // swept into the vaults first: distribution refuses an un-swept curve
    // bucket, and the pool sweep creates the AMM vault ATA when missing.
    const sweeps = await creatorFeeSweepInstructions({
      payer,
      mint,
      bondingCurve: state.bondingCurve,
      poolAccountInfo,
      quoteMint,
      quoteTokenProgram,
    });
    const instructions = [...sweeps];

    const isGraduated = poolAccountInfo !== null;
    if (
      isGraduated &&
      (state.ammVaultAtaInfo || !poolCreatorFees(poolAccountInfo).isZero())
    ) {
      instructions.push(
        await this.consolidationInstruction(mint, payer!, state),
      );
    }

    instructions.push(
      isNativeQuote
        ? await PUMP_SDK.distributeCreatorFees({
            mint,
            sharingConfig,
            sharingConfigAddress: sharingConfigPubkey,
          })
        : await PUMP_SDK.distributeCreatorFeesV2({
            mint,
            sharingConfig,
            sharingConfigAddress: sharingConfigPubkey,
            quoteMint,
            payer: payer!,
            shouldInitializeAta: true,
            quoteTokenProgram,
          }),
    );

    return {
      instructions,
      isGraduated,
      sweepCount: sweeps.length,
    };
  }

  // What both distribution helpers read, in one batch after the quote program
  // is known: the sharing config (required), the canonical pool (graduation),
  // the AMM coin creator vault ATA and the curve.
  private async fetchDistributionState(
    mint: PublicKey,
    options: { quoteMint?: PublicKey; quoteTokenProgram?: PublicKey },
  ) {
    const quoteMint = normalizeQuoteMint(options.quoteMint);
    const isNativeQuote = quoteMint.equals(NATIVE_MINT);
    const quoteTokenProgram =
      options.quoteTokenProgram ??
      (isNativeQuote
        ? TOKEN_PROGRAM_ID
        : await this.fetchQuoteTokenProgram(quoteMint));
    const sharingConfigPubkey = feeSharingConfigPda(mint);
    const ammVaultAta = coinCreatorVaultAtaPda(
      coinCreatorVaultAuthorityPda(sharingConfigPubkey),
      quoteMint,
      quoteTokenProgram,
    );

    const [
      sharingConfigAccountInfo,
      poolAccountInfo,
      ammVaultAtaInfo,
      bondingCurveAccountInfo,
    ] = await this.connection.getMultipleAccountsInfo([
      sharingConfigPubkey,
      canonicalPumpPoolPdaWithQuote(mint, quoteMint),
      ammVaultAta,
      bondingCurvePda(mint),
    ]);

    if (!sharingConfigAccountInfo) {
      throw new Error(`Sharing config not found for mint: ${mint.toBase58()}`);
    }

    return {
      quoteMint,
      isNativeQuote,
      quoteTokenProgram,
      sharingConfigPubkey,
      sharingConfig: PUMP_SDK.decodeSharingConfig(sharingConfigAccountInfo),
      poolAccountInfo,
      ammVaultAtaInfo,
      bondingCurve: bondingCurveAccountInfo
        ? PUMP_SDK.decodeBondingCurve(bondingCurveAccountInfo)
        : null,
    };
  }

  // Moves the AMM coin creator vault's fees to the pump creator vault so a
  // distribution pays them too.
  private async consolidationInstruction(
    mint: PublicKey,
    payer: PublicKey,
    {
      quoteMint,
      isNativeQuote,
      quoteTokenProgram,
      sharingConfigPubkey,
    }: {
      quoteMint: PublicKey;
      isNativeQuote: boolean;
      quoteTokenProgram: PublicKey;
      sharingConfigPubkey: PublicKey;
    },
  ): Promise<TransactionInstruction> {
    return isNativeQuote
      ? await this.pumpAmmProgram.methods
          .transferCreatorFeesToPump()
          .accountsPartial({
            wsolMint: NATIVE_MINT,
            tokenProgram: TOKEN_PROGRAM_ID,
            coinCreator: sharingConfigPubkey,
          })
          .instruction()
      : await PUMP_SDK.transferCreatorFeesToPumpV2({
          payer,
          mint,
          quoteMint,
          quoteTokenProgram,
        });
  }
}

export interface MinimumDistributableFeeResult extends MinimumDistributableFeeEvent {
  isGraduated: boolean;
  /**
   * The mint `minimumRequired` / `distributableFees` / `canDistribute` are
   * denominated in. Always `NATIVE_MINT` today: the on-chain view reads the
   * lamport creator vault only. Compare it with the coin's quote mint before
   * gating a token-quoted coin's distribution on `canDistribute`.
   */
  feesQuoteMint: PublicKey;
}

export interface DistributeCreatorFeeResult {
  instructions: TransactionInstruction[];
  isGraduated: boolean;
  /**
   * How many leading `instructions` are creator-fee sweeps (0 to 2), to send
   * in a transaction of their own when the whole list does not fit one.
   */
  sweepCount: number;
}

/**
 * A creator's uncollected fees in one supported quote mint, as returned by
 * `OnlinePumpSdk.getCreatorVaultQuoteBalances`. Amounts are in the mint's
 * base units (lamports for SOL, reported as `NATIVE_MINT`).
 */
export interface CreatorVaultQuoteBalance {
  mint: PublicKey;
  /** Where the mint was listed, or `extra` for one passed by the caller. */
  source: QuoteMintSource | "extra";
  quoteTokenProgram: PublicKey;
  /**
   * Pump creator vault: lamports above rent for SOL, the vault ATA's amount
   * otherwise.
   */
  pumpVault: BN;
  /** Pump-amm coin creator vault ATA amount. */
  ammVault: BN;
  total: BN;
}
