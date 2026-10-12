import { PublicKey } from "@solana/web3.js";
import BN from "bn.js";

import type { PumpQuoteCurve } from "./bondingCurve";
import type { PumpQuoteAccounts } from "./sdk";

/**
 * Platform identifiers for social handle mappings.
 */
export enum Platform {
  Pump = 0,
  X = 1,
  GitHub = 2,
  // Google = 3,
  // Discord = 4,
  // Reddit = 5,
  // TikTok = 6,
  // Youtube = 7,
  // Twitch = 8,
  // LinkedIn = 9,
  // Facebook = 10,
  // Instagram = 11,
  // Snapchat = 12,
  // Telegram = 13,
  // WhatsApp = 14,
  // Threads = 15,
}

export const stringToPlatform = (value: string): Platform => {
  const normalized = value.trim().toUpperCase();
  const entry = Object.entries(Platform).find(
    ([key, val]) => typeof val === "number" && key.toUpperCase() === normalized,
  );
  if (entry) {
    return entry[1] as Platform;
  }
  const validNames = Object.entries(Platform)
    .filter(([, val]) => typeof val === "number")
    .map(([key]) => key.toUpperCase())
    .join(", ");
  throw new Error(
    `Unknown platform "${value}". Expected one of: ${validNames}`,
  );
};

export const platformToString = (platform: Platform): string => {
  const name = Platform[platform];
  if (name !== undefined) {
    return name;
  }
  throw new Error(`Unknown platform value: ${platform}`);
};

export interface Global {
  // unused
  initialized: boolean;
  authority: PublicKey;
  feeRecipient: PublicKey;
  initialVirtualTokenReserves: BN;
  initialVirtualSolReserves: BN;
  initialRealTokenReserves: BN;
  tokenTotalSupply: BN;
  feeBasisPoints: BN;
  withdrawAuthority: PublicKey;
  // Unused
  enableMigrate: boolean;
  poolMigrationFee: BN;
  creatorFeeBasisPoints: BN;
  feeRecipients: PublicKey[];
  setCreatorAuthority: PublicKey;
  adminSetCreatorAuthority: PublicKey;
  createV2Enabled: boolean;
  whitelistPda: PublicKey;
  reservedFeeRecipient: PublicKey;
  mayhemModeEnabled: boolean;
  reservedFeeRecipients: PublicKey[];
  isCashbackEnabled: boolean;
  buybackFeeRecipients: PublicKey[];
  buybackBasisPoints: BN;
  initialVirtualQuoteReserves: BN;
  whitelistedQuoteMints: PublicKey[];
  /**
   * Gate for per-coin creator fees. While `false`, every curve pays the
   * schedule's creator rate whatever its `creatorFeeBps` holds, and
   * `create_v2` / `set_creator_fee_bps` reject a nonzero rate (6077).
   * `false` on a `Global` account written before the field existed.
   */
  creatorFeeConfigurable: boolean;
  /**
   * Inclusive ceiling for a configured `BondingCurve.creatorFeeBps`; the
   * program accepts `1..=max` (6078 outside it). Zero on accounts written
   * before the field existed.
   */
  maxConfigurableCreatorFeeBps: BN;
  /**
   * The only signer `distribute_fee_to_holders` accepts. The zero key on a
   * `Global` account written before the field existed (or never configured).
   */
  holderRewardClaimAuthority: PublicKey;
  /**
   * Gate for `create_v2`'s `is_holder_reward` and for a CTO's holder
   * conversion (6084 `HolderRewardDisabled` while `false`). `false` on a
   * `Global` account written before the field existed.
   */
  isHolderRewardEnabled: boolean;
  /**
   * The deepest curve `create_v2` may create through a pump coin quote: a
   * coin quoted in a pump coin Q stores `Q.depth + 1`, refused above this
   * (6105 `CurveDepthExceeded`). 0 disables pump-coin quotes; 0 on a `Global`
   * account written before the field existed.
   */
  maxCurveDepth: number;
}

export interface BondingCurve {
  virtualTokenReserves: BN;
  virtualQuoteReserves: BN;
  realTokenReserves: BN;
  realQuoteReserves: BN;
  tokenTotalSupply: BN;
  complete: boolean;
  creator: PublicKey;
  isMayhemMode: boolean;
  isCashbackCoin: boolean;
  quoteMint: PublicKey;
  /**
   * The coin's own creator fee rate in basis points. Zero means "not
   * configured": trades pay the pump-fees schedule's creator rate. Nonzero
   * replaces that rate while `Global.creatorFeeConfigurable` is on (protocol
   * and LP rates are untouched). Zero on curves shorter than
   * `BONDING_CURVE_SIZE`, which is every curve written before the field
   * existed.
   */
  creatorFeeBps: BN;
  /**
   * Retired: nothing sets or reads it any more. A configured creator fee is
   * fixed at creation and changes only through a CTO (`admin_cto`), where the
   * CTO authority picks the new rate. Always `false` on curves the current
   * program wrote.
   */
  canEditCreatorFee: boolean;
  /**
   * Whether the coin is a holder-reward coin: its `creator` is the coin's
   * `holderRewardsPda(mint)`, so every creator fee accrues to that PDA's
   * creator vault and is paid out to holders by `distribute_fee_to_holders`.
   * Set at `create_v2` (`is_holder_reward`) or by a CTO; permanent once set.
   * `false` on curves shorter than `BONDING_CURVE_SIZE`.
   */
  isHolderReward: boolean;
  /**
   * Creator (or holder-reward) fees the v3 trades accrued and left on the
   * curve: lamports on a SOL curve, tokens in the curve's quote ATA
   * otherwise. Paid to `creatorVaultPda(creator)` by the permissionless
   * `sweep_creator_fee` (`PumpSdk.sweepCreatorFeeInstruction`), which must
   * run first in the same transaction as every `distribute_creator_fees(_v2)`,
   * `admin_cto` and fee-sharing creation while it is nonzero (6095
   * `CreatorFeesNotSwept`). Zero on curves shorter than `BONDING_CURVE_SIZE`.
   */
  creatorFee: BN;
  /**
   * Protocol fees (net of the buyback slice, which the trade pays out
   * directly) the v3 trades accrued and left on the curve, paid to a
   * `Global` fee recipient by `sweep_protocol_fee`. Zero on curves shorter
   * than `BONDING_CURVE_SIZE`.
   */
  protocolFees: BN;
  /**
   * How many pump coins deep the curve's quote chain is: 0 for SOL, a
   * `Global`-whitelisted or a quote-control quote, `Q.depth + 1` for a coin
   * quoted in pump coin Q. 0 on curves written before the field existed.
   */
  depth: number;
  /**
   * The `virtualQuoteReserves` the curve was created with (0 on curves
   * created before the field existed). A coin quoted in this one seeds from
   * it when this curve's depth is 1 or more.
   */
  initialVirtualQuoteReserves: BN;
  /**
   * The post-completion leg of the buy that completed the curve: tokens it
   * took from the pool-to-be and the net quote it paid in, both added to the
   * migration's deposit. Zero unless a v3 buy crossed the remaining supply.
   */
  postCompleteBaseOut: BN;
  postCompleteQuoteIn: BN;
}

/**
 * One quote mint admitted through the `QuoteControl` PDA and the
 * `virtualQuoteReserves` a curve quoted in it starts from (mints whitelisted
 * on `Global` use `Global.initialVirtualQuoteReserves` instead).
 */
export interface QuoteControlMint {
  mint: PublicKey;
  initialVirtualQuoteReserves: BN;
}

/**
 * The pump `QuoteControl` PDA (`QUOTE_CONTROL_PDA`): the admin-managed list of
 * quote mints `create_v2` accepts in addition to SOL and the `Global`
 * whitelist. The account may not exist yet, which the program treats as an
 * empty list. `reserved` is the 32-byte area the program keeps in front of
 * `mints` for future fixed-size fields.
 */
export interface QuoteControl {
  admin: PublicKey;
  /**
   * The key allowed to change a listed mint's initial virtual quote reserves
   * (carved out of the reserved area: the zero key until set).
   */
  reservesAdmin: PublicKey;
  reserved: number[];
  mints: QuoteControlMint[];
}

/**
 * Where a supported quote mint is admitted from: SOL itself, the
 * `Global.whitelistedQuoteMints` slots, or the `QuoteControl` PDA.
 */
export type QuoteMintSource = "sol" | "global" | "quoteControl" | "pumpCoin";

/**
 * A quote mint `create_v2` accepts right now, as enumerated by
 * `OnlinePumpSdk.fetchSupportedQuoteMints`. SOL is reported as `NATIVE_MINT`.
 * `initialVirtualQuoteReserves` is what a new curve quoted in it starts from
 * (see `initialVirtualQuoteReservesFor`).
 */
export interface SupportedQuoteMint {
  mint: PublicKey;
  source: QuoteMintSource;
  initialVirtualQuoteReserves: BN;
}

/**
 * A `SupportedQuoteMint` plus what instruction builders need for it: the
 * program that owns the mint (every quote-side ATA is derived with it) and the
 * mint's decimals.
 */
export interface ResolvedQuoteMint extends SupportedQuoteMint {
  quoteTokenProgram: PublicKey;
  decimals: number;
  /**
   * Set when `source` is `pumpCoin`: the pump coin's curve state, from which
   * `initialVirtualQuoteReserves` was derived (pass it as `pumpQuote` to the
   * quote functions), the accounts `create_v2` needs for it (pass them as
   * `createV2Instruction`'s `pumpQuote`) and the depth the new coin gets.
   */
  pumpQuote?: {
    curve: PumpQuoteCurve;
    accounts: PumpQuoteAccounts;
    depth: number;
  };
}

export interface GlobalVolumeAccumulator {
  startTime: BN;
  endTime: BN;
  secondsInADay: BN;
  mint: PublicKey;
  totalTokenSupply: BN[];
  solVolumes: BN[];
}

export interface UserVolumeAccumulator {
  user: PublicKey;
  needsClaim: boolean;
  totalUnclaimedTokens: BN;
  totalClaimedTokens: BN;
  currentSolVolume: BN;
  lastUpdateTimestamp: BN;
  hasTotalClaimedTokens: boolean;
  cashbackEarned: BN;
  totalCashbackClaimed: BN;
  stableCashbackEarned: BN;
  totalStableCashbackClaimed: BN;
}

export interface UserVolumeAccumulatorTotalStats {
  totalUnclaimedTokens: BN;
  totalClaimedTokens: BN;
  currentSolVolume: BN;
}

export interface FeeConfig {
  admin: PublicKey;
  /** Schedule for pools that are not canonical pump pools. */
  flatFees: Fees;
  /** Market-cap tiers for SOL-quoted canonical pump pools and curves. */
  feeTiers: FeeTier[];
  /**
   * Market-cap tiers for canonical pump pools quoted in a listed stable
   * (USDC). Empty on accounts that predate the field.
   */
  stableFeeTiers: FeeTier[];
  /**
   * Flat schedule for canonical pump pools quoted in anything else. All-zero
   * means unset: the program then charges `flatFees`.
   */
  exoticFlatFees: Fees;
}

export interface FeeTier {
  marketCapLamportsThreshold: BN;
  fees: Fees;
}

export interface Fees {
  lpFeeBps: BN;
  protocolFeeBps: BN;
  creatorFeeBps: BN;
}

export interface Shareholder {
  address: PublicKey;
  shareBps: number;
}

export interface SharingConfig {
  version: number;
  mint: PublicKey;
  admin: PublicKey;
  adminRevoked: boolean;
  shareholders: Shareholder[];
}

export interface DistributeCreatorFeesEvent {
  timestamp: BN;
  mint: PublicKey;
  sharingConfig: PublicKey;
  admin: PublicKey;
  shareholders: Shareholder[];
  distributed: BN;
  quoteMint: PublicKey;
}

export interface CollectCreatorFeeEventBc {
  timestamp: BN;
  creator: PublicKey;
  creatorFee: BN;
  quoteMint: PublicKey;
}

export interface CollectCoinCreatorFeeEventAmm {
  timestamp: BN;
  coinCreator: PublicKey;
  coinCreatorFee: BN;
  coinCreatorVaultAta: PublicKey;
  coinCreatorTokenAccount: PublicKey;
}
export interface CreatePoolEventAmm {
  timestamp: BN;
  index: number;
  creator: PublicKey;
  baseMint: PublicKey;
  quoteMint: PublicKey;
  baseMintDecimals: number;
  quoteMintDecimals: number;
  baseAmountIn: BN;
  quoteAmountIn: BN;
  poolBaseAmount: BN;
  poolQuoteAmount: BN;
  minimumLiquidity: BN;
  initialLiquidity: BN;
  lpTokenAmountOut: BN;
  poolBump: number;
  pool: PublicKey;
  lpMint: PublicKey;
  userBaseTokenAccount: PublicKey;
  userQuoteTokenAccount: PublicKey;
  coinCreator: PublicKey;
  isMayhemMode: boolean;
  /**
   * The pool's own creator fee rate in basis points, carried over from the
   * curve at migration (zero: the schedule rate). Zero in events emitted
   * before the field existed.
   */
  creatorFeeBps: BN;
  /**
   * Retired flag, carried over from the curve at migration; nothing reads it.
   * `false` in events emitted before the field existed.
   */
  canEditCreatorFee: boolean;
  /**
   * Whether the pool belongs to a holder-reward coin (its `coinCreator` is
   * the coin's holder-rewards PDA). `false` in events emitted before the
   * field existed.
   */
  isHolderReward: boolean;
}

export interface DepositEventAmm {
  timestamp: BN;
  lpTokenAmountOut: BN;
  maxBaseAmountIn: BN;
  maxQuoteAmountIn: BN;
  userBaseTokenReserves: BN;
  userQuoteTokenReserves: BN;
  poolBaseTokenReserves: BN;
  poolQuoteTokenReserves: BN;
  baseAmountIn: BN;
  quoteAmountIn: BN;
  lpMintSupply: BN;
  pool: PublicKey;
  user: PublicKey;
  userBaseTokenAccount: PublicKey;
  userQuoteTokenAccount: PublicKey;
  userPoolTokenAccount: PublicKey;
}

export interface WithdrawEventAmm {
  timestamp: BN;
  lpTokenAmountIn: BN;
  minBaseAmountOut: BN;
  minQuoteAmountOut: BN;
  userBaseTokenReserves: BN;
  userQuoteTokenReserves: BN;
  poolBaseTokenReserves: BN;
  poolQuoteTokenReserves: BN;
  baseAmountOut: BN;
  quoteAmountOut: BN;
  lpMintSupply: BN;
  pool: PublicKey;
  user: PublicKey;
  userBaseTokenAccount: PublicKey;
  userQuoteTokenAccount: PublicKey;
  userPoolTokenAccount: PublicKey;
}

export interface BuyEventAmm {
  timestamp: BN;
  baseAmountOut: BN;
  maxQuoteAmountIn: BN;
  userBaseTokenReserves: BN;
  userQuoteTokenReserves: BN;
  poolBaseTokenReserves: BN;
  poolQuoteTokenReserves: BN;
  quoteAmountIn: BN;
  lpFeeBasisPoints: BN;
  lpFee: BN;
  protocolFeeBasisPoints: BN;
  protocolFee: BN;
  quoteAmountInWithLpFee: BN;
  userQuoteAmountIn: BN;
  pool: PublicKey;
  user: PublicKey;
  userBaseTokenAccount: PublicKey;
  userQuoteTokenAccount: PublicKey;
  protocolFeeRecipient: PublicKey;
  protocolFeeRecipientTokenAccount: PublicKey;
  coinCreator: PublicKey;
  coinCreatorFeeBasisPoints: BN;
  coinCreatorFee: BN;
  trackVolume: boolean;
  totalUnclaimedTokens: BN;
  totalClaimedTokens: BN;
  currentSolVolume: BN;
  lastUpdateTimestamp: BN;
  minBaseAmountOut: BN;
  ixName: string;
  cashbackFeeBasisPoints: BN;
  cashback: BN;
  buybackFeeBasisPoints: BN;
  buybackFee: BN;
  virtualQuoteReserves: BN;
  canBoost: boolean;
  baseSupply: BN;
  /**
   * The creator fee rate / amount when the pool is a holder-reward pool
   * (equal to `coinCreatorFeeBasisPoints` / `coinCreatorFee`, which keep
   * reporting the fee); zero otherwise, and in events emitted before the
   * fields existed.
   */
  holderRewardsBps: BN;
  holderRewards: BN;
  /**
   * The pool's creator bucket (`Pool.creatorFees`) after the trade: creator
   * fees pump-amm v2 trades accrued that no `sweep_creator_fee` has moved to
   * the coin creator vault yet. Zero in events emitted before the field
   * existed.
   */
  creatorFeeUnclaimed: BN;
}

export interface SellEventAmm {
  timestamp: BN;
  baseAmountIn: BN;
  minQuoteAmountOut: BN;
  userBaseTokenReserves: BN;
  userQuoteTokenReserves: BN;
  poolBaseTokenReserves: BN;
  poolQuoteTokenReserves: BN;
  quoteAmountOut: BN;
  lpFeeBasisPoints: BN;
  lpFee: BN;
  protocolFeeBasisPoints: BN;
  protocolFee: BN;
  quoteAmountOutWithoutLpFee: BN;
  userQuoteAmountOut: BN;
  pool: PublicKey;
  user: PublicKey;
  userBaseTokenAccount: PublicKey;
  userQuoteTokenAccount: PublicKey;
  protocolFeeRecipient: PublicKey;
  protocolFeeRecipientTokenAccount: PublicKey;
  coinCreator: PublicKey;
  coinCreatorFeeBasisPoints: BN;
  coinCreatorFee: BN;
  cashbackFeeBasisPoints: BN;
  cashback: BN;
  buybackFeeBasisPoints: BN;
  buybackFee: BN;
  virtualQuoteReserves: BN;
  canBoost: boolean;
  baseSupply: BN;
  /**
   * The creator fee rate / amount when the pool is a holder-reward pool
   * (equal to `coinCreatorFeeBasisPoints` / `coinCreatorFee`, which keep
   * reporting the fee); zero otherwise, and in events emitted before the
   * fields existed.
   */
  holderRewardsBps: BN;
  holderRewards: BN;
  /**
   * The pool's creator bucket (`Pool.creatorFees`) after the trade: creator
   * fees pump-amm v2 trades accrued that no `sweep_creator_fee` has moved to
   * the coin creator vault yet. Zero in events emitted before the field
   * existed.
   */
  creatorFeeUnclaimed: BN;
}

/** pump-amm `AdminCtoPoolEvent`: the pool side of a pump `admin_cto`. */
export interface AdminCtoPoolEventAmm {
  timestamp: BN;
  baseMint: PublicKey;
  pool: PublicKey;
  oldCoinCreator: PublicKey;
  newCoinCreator: PublicKey;
  isHolderReward: boolean;
  isCashbackCoin: boolean;
  oldCreatorFeeBps: BN;
  newCreatorFeeBps: BN;
}

/** pump `AdminCtoEvent`: one community takeover, whatever path it took. */
export interface AdminCtoEvent {
  timestamp: BN;
  /** `Global.adminSetCreatorAuthority`, the signer. */
  authority: PublicKey;
  mint: PublicKey;
  bondingCurve: PublicKey;
  oldCreator: PublicKey;
  /** The wallet, the coin's SharingConfig PDA (fee-shared coin) or its holder-rewards PDA. */
  newCreator: PublicKey;
  isHolderReward: boolean;
  isCashbackCoin: boolean;
  oldCreatorFeeBps: BN;
  newCreatorFeeBps: BN;
  /** Whether the coin's pump-fees SharingConfig was rewritten or terminated. */
  sharingConfigReset: boolean;
  /** Quote units swept from a fee-shared coin's vaults into the holder-rewards creator vault. */
  sweptToHolderVault: BN;
  /** Whether a canonical pump-amm pool existed and was updated through `admin_cto_pool`. */
  poolUpdated: boolean;
}

export interface CreateEventBc {
  name: string;
  symbol: string;
  uri: string;
  mint: PublicKey;
  bondingCurve: PublicKey;
  user: PublicKey;
  creator: PublicKey;
  timestamp: BN;
  virtualTokenReserves: BN;
  virtualSolReserves: BN;
  realTokenReserves: BN;
  tokenTotalSupply: BN;
  tokenProgram: PublicKey;
  isMayhemMode: boolean;
  isCashbackEnabled: boolean;
  quoteMint: PublicKey;
  virtualQuoteReserves: BN;
  /**
   * The creator fee rate the coin was created with (`create_v2`'s
   * `creator_fee_bps`; zero for the schedule rate, and always zero from
   * legacy `create`). Zero in events emitted before the field existed.
   */
  creatorFeeBps: BN;
  /**
   * Whether the coin was created as a holder-reward coin (`create_v2`'s
   * `is_holder_reward`; always `false` from legacy `create`). `false` in
   * events emitted before the field existed.
   */
  isHolderReward: boolean;
  /**
   * The new curve's depth (`BondingCurve.depth`): nonzero only for a coin
   * quoted in a pump coin. 0 in events emitted before the field existed.
   */
  depth: number;
}

export interface TradeEventBc {
  mint: PublicKey;
  solAmount: BN;
  tokenAmount: BN;
  isBuy: boolean;
  user: PublicKey;
  timestamp: BN;
  virtualSolReserves: BN;
  virtualTokenReserves: BN;
  realSolReserves: BN;
  realTokenReserves: BN;
  feeRecipient: PublicKey;
  feeBasisPoints: BN;
  fee: BN;
  creator: PublicKey;
  creatorFeeBasisPoints: BN;
  creatorFee: BN;
  trackVolume: boolean;
  totalUnclaimedTokens: BN;
  totalClaimedTokens: BN;
  currentSolVolume: BN;
  lastUpdateTimestamp: BN;
  ixName: string;
  mayhemMode: boolean;
  cashbackFeeBasisPoints: BN;
  cashback: BN;
  buybackFeeBasisPoints: BN;
  buybackFee: BN;
  shareholders: Shareholder[];
  quoteMint: PublicKey;
  quoteAmount: BN;
  virtualQuoteReserves: BN;
  realQuoteReserves: BN;
  /**
   * The creator fee rate / amount when the coin is a holder-reward coin
   * (equal to `creatorFeeBasisPoints` / `creatorFee`, which keep reporting
   * the fee); zero otherwise, and in events emitted before the fields
   * existed.
   */
  holderRewardsBps: BN;
  holderRewards: BN;
  /**
   * The curve's creator bucket (`BondingCurve.creatorFee`) after the trade:
   * creator fees v3 trades accrued that no `sweep_creator_fee` has moved to
   * the creator vault yet (v1 / v2 trades report it unchanged). Zero in
   * events emitted before the field existed.
   */
  creatorFeeUnclaimed: BN;
}

export interface CompleteEventBc {
  user: PublicKey;
  mint: PublicKey;
  bondingCurve: PublicKey;
  timestamp: BN;
  quoteMint: PublicKey;
}

export interface SetQuoteControlAdminEvent {
  quoteControl: PublicKey;
  authority: PublicKey;
  oldAdmin: PublicKey;
  newAdmin: PublicKey;
  timestamp: BN;
}

export interface AddQuoteControlMintEvent {
  quoteControl: PublicKey;
  authority: PublicKey;
  quoteMint: PublicKey;
  initialVirtualQuoteReserves: BN;
  timestamp: BN;
}

export interface RemoveQuoteControlMintEvent {
  quoteControl: PublicKey;
  authority: PublicKey;
  quoteMint: PublicKey;
  timestamp: BN;
}

/**
 * pump `PostCompleteBuyEvent`, emitted after `CompleteEvent` when a v3 buy
 * crossed the remaining supply: the leg bought from the pool the migration
 * will create, priced on its reserves before and after.
 */
export interface PostCompleteBuyEvent {
  user: PublicKey;
  mint: PublicKey;
  bondingCurve: PublicKey;
  quoteMint: PublicKey;
  timestamp: BN;
  baseOut: BN;
  quoteIn: BN;
  feeBasisPoints: BN;
  fee: BN;
  creatorFeeBasisPoints: BN;
  creatorFee: BN;
  buybackFee: BN;
  poolBaseReservesBefore: BN;
  poolQuoteReservesBefore: BN;
  poolBaseReservesAfter: BN;
  poolQuoteReservesAfter: BN;
}

/**
 * pump `SweepBondingCurveFeeEvent`: one fee bucket of a curve paid out by
 * `sweep_protocol_fee` (`bucket` 0) or `sweep_creator_fee` (`bucket` 1).
 */
export interface SweepBondingCurveFeeEvent {
  timestamp: BN;
  mint: PublicKey;
  bondingCurve: PublicKey;
  /** The zero key on a SOL curve. */
  quoteMint: PublicKey;
  recipient: PublicKey;
  amount: BN;
  bucket: number;
}

/**
 * pump-amm `SweepPoolFeeEvent`: one fee bucket of a canonical pool paid out
 * by `sweep_protocol_fee` (`bucket` 0) or `sweep_creator_fee` (`bucket` 1).
 */
export interface SweepPoolFeeEventAmm {
  timestamp: BN;
  pool: PublicKey;
  baseMint: PublicKey;
  quoteMint: PublicKey;
  recipient: PublicKey;
  payer: PublicKey;
  amount: BN;
  bucket: number;
}

export interface UpdateCreatorFeeConfigEvent {
  timestamp: BN;
  authority: PublicKey;
  creatorFeeConfigurable: boolean;
  maxConfigurableCreatorFeeBps: BN;
}

/** pump `DistributeFeeToHoldersEvent`: one payout of a holder-reward coin. */
export interface DistributeFeeToHoldersEvent {
  timestamp: BN;
  mint: PublicKey;
  /** The zero key for a SOL quote, else the quote mint. */
  quoteMint: PublicKey;
  /** How many `(owner, ATA)` pairs were paid. */
  recipients: BN;
  /** The sum of the amounts paid, in the quote's base units. */
  total: BN;
}

export interface ClaimCashbackEvent {
  user: PublicKey;
  amount: BN;
  timestamp: BN;
  totalClaimed: BN;
  totalCashbackEarned: BN;
}

export interface MinimumDistributableFeeEvent {
  minimumRequired: BN;
  distributableFees: BN;
  canDistribute: boolean;
}

export interface SocialFeePda {
  bump: number;
  version: number;
  userId: string;
  platform: number;
  totalClaimed: BN;
  lastClaimed: BN;
  totalStableClaimed: BN;
}

export interface SocialFeePdaClaimedEvent {
  timestamp: BN;
  userId: string;
  platform: number;
  socialFeePda: PublicKey;
  recipient: PublicKey;
  socialClaimAuthority: PublicKey;
  amountClaimed: BN;
  claimableBefore: BN;
  lifetimeClaimed: BN;
  recipientBalanceBefore: BN;
  recipientBalanceAfter: BN;
  quoteMint: PublicKey;
  lifetimeStableClaimed: BN;
}

export interface SocialFeePdaCreatedEvent {
  timestamp: BN;
  userId: string;
  platform: number;
  socialFeePda: PublicKey;
  createdBy: PublicKey;
}

export interface DonationFeePda {
  bump: number;
  version: number;
  configId: PublicKey;
  baseMint: PublicKey;
  quoteMint: PublicKey;
  creator: PublicKey;
  totalDonated: BN;
  lastCrankTs: BN;
  reserved: number[];
}

export type ConfigStatus =
  { paused: Record<string, never> } | { active: Record<string, never> };

export interface CreateFeeSharingConfigEvent {
  timestamp: BN;
  mint: PublicKey;
  bondingCurve: PublicKey;
  pool: PublicKey | null;
  sharingConfig: PublicKey;
  admin: PublicKey;
  initialShareholders: Shareholder[];
  status: ConfigStatus;
}

export interface UpdateFeeSharesEvent {
  timestamp: BN;
  mint: PublicKey;
  sharingConfig: PublicKey;
  admin: PublicKey;
  newShareholders: Shareholder[];
  version: number;
}

export interface UpdateAdminEvent {
  timestamp: BN;
  oldAdmin: PublicKey;
  newAdmin: PublicKey;
}

export interface SetAuthorityEvent {
  timestamp: BN;
  oldAuthority: PublicKey;
  newAuthority: PublicKey;
}

export interface ResetFeeSharingConfigEvent {
  timestamp: BN;
  mint: PublicKey;
  sharingConfig: PublicKey;
  oldAdmin: PublicKey;
  oldShareholders: Shareholder[];
  newAdmin: PublicKey;
  newShareholders: Shareholder[];
  oldVersion: number;
  newVersion: number;
}

export interface DonationFeePdaCreatedEvent {
  timestamp: BN;
  createdBy: PublicKey;
  donationFeePda: PublicKey;
  configId: PublicKey;
  baseMint: PublicKey;
  quoteMint: PublicKey;
  creator: PublicKey;
}
