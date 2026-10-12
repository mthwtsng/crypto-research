import { PublicKey } from "@solana/web3.js";
import BN from "bn.js";

/**
 * Custom error types for the Pump SDK
 */

export class NoShareholdersError extends Error {
  constructor() {
    super("No shareholders provided");
    this.name = "NoShareholdersError";
  }
}

export class TooManyShareholdersError extends Error {
  constructor(
    public count: number,
    public max: number,
  ) {
    super(`Too many shareholders. Maximum allowed is ${max}, got ${count}`);
    this.name = "TooManyShareholdersError";
  }
}

export class ZeroShareError extends Error {
  constructor(public address: string) {
    super(`Zero or negative share not allowed for address ${address}`);
    this.name = "ZeroShareError";
  }
}

export class ShareCalculationOverflowError extends Error {
  constructor() {
    super("Share calculation overflow - total shares exceed maximum value");
    this.name = "ShareCalculationOverflowError";
  }
}

export class InvalidShareTotalError extends Error {
  constructor(public total: number) {
    super(
      `Invalid share total. Must equal 10,000 basis points (100%). Got ${total}`,
    );
    this.name = "InvalidShareTotalError";
  }
}

export class DuplicateShareholderError extends Error {
  constructor() {
    super("Duplicate shareholder addresses not allowed");
    this.name = "DuplicateShareholderError";
  }
}

export class PoolRequiredForGraduatedError extends Error {
  constructor() {
    super(
      "Pool parameter is required for graduated coins (bondingCurve.complete = true)",
    );
    this.name = "PoolRequiredForGraduatedError";
  }
}

export class UnsupportedQuoteMintError extends Error {
  constructor(public quoteMint: PublicKey) {
    super(
      `Unsupported quote mint ${quoteMint.toBase58()}: not SOL, not whitelisted on Global and not listed in QuoteControl`,
    );
    this.name = "UnsupportedQuoteMintError";
  }
}

/** Mirrors pump error 6077: `Global.creatorFeeConfigurable` is off. */
export class CreatorFeeNotConfigurableError extends Error {
  constructor() {
    super(
      "Configurable creator fees are disabled (Global.creatorFeeConfigurable is false)",
    );
    this.name = "CreatorFeeNotConfigurableError";
  }
}

/**
 * Mirrors pump error 6078: a configured creator fee must be in
 * `1..=Global.maxConfigurableCreatorFeeBps`.
 */
export class CreatorFeeBpsOutOfRangeError extends Error {
  constructor(
    public creatorFeeBps: BN,
    public max: BN,
  ) {
    super(
      `Creator fee of ${creatorFeeBps.toString()} bps is outside 1..=${max.toString()} (Global.maxConfigurableCreatorFeeBps)`,
    );
    this.name = "CreatorFeeBpsOutOfRangeError";
  }
}

/**
 * Mirrors pump error 6080: a cashback coin cannot configure a creator fee.
 * Only reachable through `admin_cto` now: `create_v2` rejects every cashback
 * coin first (`CashbackDeprecatedError`).
 */
export class CreatorFeeNotAllowedForCashbackCoinError extends Error {
  constructor(public mint: PublicKey) {
    super(
      `Creator fee cannot be configured for cashback coin ${mint.toBase58()}`,
    );
    this.name = "CreatorFeeNotAllowedForCashbackCoinError";
  }
}

/**
 * Mirrors pump error 6082: `create_v2` no longer creates cashback coins
 * (`is_cashback_enabled` must be false). Existing cashback coins keep working
 * and their accrued cashback stays claimable.
 */
export class CashbackDeprecatedError extends Error {
  constructor(public mint: PublicKey) {
    super(
      `Cashback coins can no longer be created (mint ${mint.toBase58()}): is_cashback_enabled is deprecated`,
    );
    this.name = "CashbackDeprecatedError";
  }
}

/** Mirrors pump error 6084: `Global.isHolderRewardEnabled` is off. */
export class HolderRewardDisabledError extends Error {
  constructor() {
    super(
      "Holder-reward coins are disabled (Global.isHolderRewardEnabled is false)",
    );
    this.name = "HolderRewardDisabledError";
  }
}

/**
 * Mirrors pump error 6083: a holder-reward coin's creator is the
 * holder-rewards PDA forever; a CTO may only adjust its configurable rate
 * (`isHolderReward: true` again), never hand it to a wallet.
 */
export class HolderRewardCreatorImmutableError extends Error {
  constructor(public mint: PublicKey) {
    super(
      `The creator of holder-reward coin ${mint.toBase58()} cannot be changed`,
    );
    this.name = "HolderRewardCreatorImmutableError";
  }
}

/** Mirrors pump error 6088: a mayhem-mode coin cannot be taken over. */
export class CtoNotAllowedForMayhemCoinError extends Error {
  constructor(public mint: PublicKey) {
    super(`CTO is not allowed on mayhem-mode coin ${mint.toBase58()}`);
    this.name = "CtoNotAllowedForMayhemCoinError";
  }
}

/**
 * Mirrors pump error 6094: the v3 trades refuse cashback coins (they never
 * credit the buyer's volume accumulator); trade those with the v2
 * instructions.
 */
export class CashbackCoinNotSupportedError extends Error {
  constructor(public mint: PublicKey) {
    super(
      `v3 trades do not support cashback coin ${mint.toBase58()}; use the v2 instructions`,
    );
    this.name = "CashbackCoinNotSupportedError";
  }
}

/**
 * Mirrors pump error 6091: a creator fee rate can only be configured on a
 * quote admitted through `QuoteControl`; SOL and `Global`-whitelisted quotes
 * (USDC) always pay the pump-fees schedule rate.
 */
export class CreatorFeeNotConfigurableForQuoteError extends Error {
  constructor(public quoteMint: PublicKey) {
    super(
      `Creator fee is not configurable on quote mint ${quoteMint.toBase58()} (SOL or whitelisted); the fee schedule applies`,
    );
    this.name = "CreatorFeeNotConfigurableForQuoteError";
  }
}

/**
 * Mirrors pump error 6105: a coin quoted in pump coin Q would sit at depth
 * `Q.depth + 1`, above `Global.maxCurveDepth` (0 disables pump-coin quotes).
 */
export class CurveDepthExceededError extends Error {
  constructor(
    public depth: number,
    public maxCurveDepth: number,
  ) {
    super(`Curve depth ${depth} exceeds Global.maxCurveDepth ${maxCurveDepth}`);
    this.name = "CurveDepthExceededError";
  }
}

/**
 * Mirrors pump error 6100: pump coin Q cannot quote a new coin (its curve is
 * mayhem mode, or it is a depth-0 coin whose own quote no list admits).
 */
export class QuoteBondingCurveNotEligibleError extends Error {
  constructor(public quoteMint: PublicKey) {
    super(
      `Pump coin ${quoteMint.toBase58()} is not eligible as a quote: mayhem mode, or its own quote is not listed`,
    );
    this.name = "QuoteBondingCurveNotEligibleError";
  }
}

/**
 * Mirrors pump error 6107: pump coin Q's curve is complete but not migrated
 * yet, so it has no price; retry once `migrate_v2` creates its pool.
 */
export class QuoteCurveAwaitingMigrationError extends Error {
  constructor(public quoteMint: PublicKey) {
    super(
      `Pump coin ${quoteMint.toBase58()} has completed its curve but is not migrated yet`,
    );
    this.name = "QuoteCurveAwaitingMigrationError";
  }
}

/**
 * Mirrors pump error 6104: the reserves derived from pump coin Q are zero, or
 * the new curve's graduation raise would exceed Q's mint supply.
 */
export class QuoteReservesOutOfRangeError extends Error {
  constructor(
    public quoteMint: PublicKey,
    public derived: BN,
  ) {
    super(
      `Reserves ${derived.toString()} derived from pump coin ${quoteMint.toBase58()} are out of range`,
    );
    this.name = "QuoteReservesOutOfRangeError";
  }
}

/**
 * Mirrors pump error 6102: pump coin Q's curve has migrated but its canonical
 * pump-amm pool does not exist (a coin graduated before pump-amm), so Q has
 * no price the program can read.
 */
export class QuotePoolNotFoundError extends Error {
  constructor(
    public quoteMint: PublicKey,
    public pool: PublicKey,
  ) {
    super(
      `Pump coin ${quoteMint.toBase58()} migrated but has no pump-amm pool at ${pool.toBase58()}`,
    );
    this.name = "QuotePoolNotFoundError";
  }
}
