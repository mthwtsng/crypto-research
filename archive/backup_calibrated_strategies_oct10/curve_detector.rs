//! Real-Time Bonding Curve State Tracker & Strategy Signal Detector.
//!
//! Subscribes directly to on-chain Solana Pump.fun bonding curve transactions
//! via Yellowstone gRPC (e.g. Solami, Triton, Helius).
//!
//! Evaluates the Canonical Starting 5 strategies with receipt-backed quote inputs:
//! - Integer bonding-curve quotes use authentic reserves and fee policy.
//! - Protocol and creator fees are rounded up separately.
//! - Delayed paper buys freeze an immutable 10% output guard by default.
//! - Provisional receive-clock delay defaults to 70 ms; it is not a calibrated
//!   validator landing measurement.
//! - Completed curves retain inventory until an authenticated migration route
//!   and pool fill are available.
//! - Creator attribution from Pump create discriminator (account index 7).
//! - Canonical 2-buyer confirmation within 3 slots for S3.
//! - Dedicated wall-clock timeout evaluation.
//! - Tailored Dynamic Exits & Calibrated Circuit Breakers.

use super::ghost_execution::{QuoteError, QuoteState};
use super::migration_amm::AmmSnapshot;
use serde::{Deserialize, Serialize};
use std::{
    collections::{HashMap, HashSet, VecDeque},
    fs::{create_dir_all, File, OpenOptions},
    io::Write,
    path::Path,
};

pub const PUMP_PROGRAM_ID: &str = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P";

// Discriminators (8-byte SHA256 prefixes)
pub const PUMP_CREATE_DISCRIMINATOR: [u8; 8] = [24, 30, 200, 40, 5, 28, 7, 119];
pub const PUMP_BUY_DISCRIMINATOR: [u8; 8] = [102, 6, 61, 18, 1, 218, 235, 234];
pub const PUMP_BUY_EXACT_SOL_IN_DISCRIMINATOR: [u8; 8] = [56, 252, 116, 8, 158, 223, 205, 95];
pub const PUMP_SELL_DISCRIMINATOR: [u8; 8] = [51, 230, 133, 164, 1, 127, 131, 173];

// Pump.fun Canonical Bonding Curve Integer Constants
pub const V_SOL_INIT: u64 = 30_000_000_000; // 30 SOL in lamports
pub const V_TOKEN_INIT: u64 = 1_073_000_000_000_000; // 1,073,000,000 tokens (6 decimals)
pub const R_TOKEN_INIT: u64 = 793_100_000_000_000; // 793,100,000 tokens available for trade
pub const TOTAL_TOKEN_SUPPLY: u64 = 1_000_000_000_000_000; // 1,000,000,000 tokens
pub const FEE_BPS: u64 = 100; // 1.00% trading fee
pub const STANDARD_NETWORK_FEE_LAMPORTS: u64 = 1_505_000; // 0.001505 SOL priority + network fee
pub const FAILED_GUARD_FEE_LAMPORTS: u64 = 505_000; // 0.000505 SOL failed tx fee
pub const DEFAULT_GHOST_LANDING_DELAY_MS: u64 = 70;
pub const DEFAULT_MIN_OUTPUT_RETAINED_BPS: u64 = 9_000; // 10.0% max adverse slippage (90.0% output retained)

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct PumpTradeEvent {
    pub mint: String,
    pub user: String,
    pub is_buy: bool,
    pub is_create: bool,
    pub sol_amount: f64,
    pub token_amount: u64,
    pub slot: u64,
    pub timestamp: u64,
    pub signature: String,
    pub onchain_rsol: Option<u64>,
    pub onchain_vsol: Option<u64>,
    pub onchain_vtokens: Option<u64>,
    pub onchain_rtokens: Option<u64>,
    pub protocol_fee_bps: Option<u16>,
    pub creator_fee_bps: Option<u16>,
    pub fee_policy_known: bool,
    pub supported_sol_quote: bool,
    pub creator: Option<String>,
    pub signer_post_sol_lamports: Option<u64>,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum StrategyKind {
    DevDumpAbsorption,      // Strat 1: broad_recovery
    SurvivalShelfBreakout,  // Strat 2: fresh_expansion
    DislocationFloor,       // Strat 3: quiet_absorption
    UpperAthBreakout,       // Strat 4: upper_ath_breakout
    PreGraduationCarryover, // Strat 5: late_continuation
}

impl StrategyKind {
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::DevDumpAbsorption => "DevDumpAbsorption (Strat 1)",
            Self::SurvivalShelfBreakout => "SurvivalShelfBreakout (Strat 2)",
            Self::DislocationFloor => "DislocationFloor (Strat 3)",
            Self::UpperAthBreakout => "UpperAthBreakout (Strat 4)",
            Self::PreGraduationCarryover => "PreGraduationCarryover (Strat 5)",
        }
    }

    pub fn code(&self) -> &'static str {
        match self {
            Self::DevDumpAbsorption => "S1",
            Self::SurvivalShelfBreakout => "S2",
            Self::DislocationFloor => "S3",
            Self::UpperAthBreakout => "S4",
            Self::PreGraduationCarryover => "S5",
        }
    }

    pub fn all() -> [StrategyKind; 5] {
        [
            Self::DevDumpAbsorption,
            Self::SurvivalShelfBreakout,
            Self::DislocationFloor,
            Self::UpperAthBreakout,
            Self::PreGraduationCarryover,
        ]
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct StrategySignal {
    pub strategy: StrategyKind,
    pub mint: String,
    pub reserve_sol: f64,
    pub buyer_breadth: usize,
    pub developer_held_pct: f64,
    pub timestamp: u64,
    pub slot: u64,
    pub signal_trough_spot: Option<f64>,
    pub details: String,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct CurveState {
    pub mint: String,
    pub creator: Option<String>,
    pub creator_tokens_max: u64,
    pub creator_tokens_held: u64,

    // Exact Integer Constant Product Curve State
    pub v_sol: u64,
    pub v_tokens: u64,
    pub r_sol: u64,
    pub r_tokens: u64,
    pub prev_r_sol: f64,
    pub peak_r_sol: u64,
    pub protocol_fee_bps: Option<u16>,
    pub creator_fee_bps: Option<u16>,
    pub fee_policy_known: bool,
    pub supported_sol_quote: bool,
    pub reserves_authoritative: bool,
    pub reserves_from_paper_fill: bool,

    // Canonical Spot Price Tracking
    pub peak_spot: f64,
    pub trough_spot: Option<f64>,
    pub trough_slot: Option<u64>,
    pub trough_outside_buyers: HashSet<String>,
    pub trough_outside_buy_lamports: u64,

    // Creator Token Liquidation Accounting (S1)
    pub creator_bought_tokens: u64,
    pub creator_sold_tokens: u64,

    // Qualified Historical Outside Buyers (>= 0.05 SOL) (S2, S4)
    pub qualified_outside_buyers: HashSet<String>,
    pub last_outside_buys: VecDeque<bool>,
    pub trailing_30s_spot: VecDeque<(u64, f64)>,

    // S3 Two-buyer Confirmation Tracking
    pub s3_dip_slot: Option<u64>,
    pub s3_dip_buyers: HashSet<String>,
    pub s3_dip_buy_groups: usize,
    pub prior_spot: Option<f64>,

    // S5 Outside Net Flow (5 slots)
    pub slot_outside_net_flow: HashMap<u64, i64>,
    pub last_slot: u64,

    pub unique_non_dev_buyers: HashSet<String>,
    pub trades_count: u64,
    pub created_at_ts: u64,
    pub last_trade_ts: u64,
    pub recent_trades: VecDeque<(u64, bool, f64)>, // (ts, is_buy, sol)

    pub signal_fired: HashSet<StrategyKind>,

    // Anti-Bundle and Botted Coin Guards
    pub created_at_slot: u64,
    pub block_0_buys_count: usize,
    pub block_0_tokens_bought: u64,
    pub early_slots_buys_count: usize,
    pub early_slots_tokens_bought: u64,
    pub holder_balances: HashMap<String, u64>,
    pub dust_wallets_count: usize,
    pub total_buyers_evaluated: usize,
    pub is_botted_cabal: bool,
    pub fresh_wallets_audited: bool,
    pub fresh_wallets_ratio: Option<f64>,
    pub audit_in_flight: bool,
    pub anti_bundle_reason: Option<String>,
    pub is_whitelisted: bool,
    pub whitelisted_by: Option<String>,
}

impl CurveState {
    pub fn new(mint: String, creator: Option<String>, created_at: u64) -> Self {
        Self {
            mint,
            creator,
            creator_tokens_max: 0,
            creator_tokens_held: 0,
            v_sol: V_SOL_INIT,
            v_tokens: V_TOKEN_INIT,
            r_sol: 0,
            r_tokens: R_TOKEN_INIT,
            prev_r_sol: 0.0,
            peak_r_sol: 0,
            protocol_fee_bps: None,
            creator_fee_bps: None,
            fee_policy_known: false,
            supported_sol_quote: false,
            reserves_authoritative: false,
            reserves_from_paper_fill: false,
            peak_spot: 0.0,
            trough_spot: None,
            trough_slot: None,
            trough_outside_buyers: HashSet::new(),
            trough_outside_buy_lamports: 0,
            creator_bought_tokens: 0,
            creator_sold_tokens: 0,
            qualified_outside_buyers: HashSet::new(),
            last_outside_buys: VecDeque::with_capacity(4),
            trailing_30s_spot: VecDeque::new(),
            s3_dip_slot: None,
            s3_dip_buyers: HashSet::new(),
            s3_dip_buy_groups: 0,
            prior_spot: None,
            slot_outside_net_flow: HashMap::new(),
            last_slot: 0,
            unique_non_dev_buyers: HashSet::new(),
            trades_count: 0,
            created_at_ts: created_at,
            last_trade_ts: created_at,
            recent_trades: VecDeque::with_capacity(30),
            signal_fired: HashSet::new(),
            created_at_slot: 0,
            block_0_buys_count: 0,
            block_0_tokens_bought: 0,
            early_slots_buys_count: 0,
            early_slots_tokens_bought: 0,
            holder_balances: HashMap::new(),
            dust_wallets_count: 0,
            total_buyers_evaluated: 0,
            is_botted_cabal: false,
            fresh_wallets_audited: false,
            fresh_wallets_ratio: None,
            audit_in_flight: false,
            anti_bundle_reason: None,
            is_whitelisted: false,
            whitelisted_by: None,
        }
    }

    /// Whitelist a coin when a tracked wallet or KOL buys it, clearing all shield vetoes.
    pub fn mark_whitelisted(&mut self, label_and_wallet: String) {
        self.is_whitelisted = true;
        self.whitelisted_by = Some(label_and_wallet);
        self.is_botted_cabal = false;
        self.anti_bundle_reason = None;
    }

    pub fn spot_price(&self) -> f64 {
        if self.v_tokens == 0 {
            0.0
        } else {
            (self.v_sol as f64) / (self.v_tokens as f64)
        }
    }

    pub fn real_sol_reserve(&self) -> f64 {
        self.r_sol as f64 / 1e9
    }

    pub fn market_cap_sol(&self) -> f64 {
        self.spot_price() * 1_000_000.0
    }

    pub fn market_cap_usd(&self, sol_usd: f64) -> f64 {
        self.market_cap_sol() * sol_usd
    }

    /// Return quote inputs only when the current reserve snapshot and fee/quote
    /// policy came from a supported on-chain receipt (or from a paper fill
    /// applied to such a receipt).
    pub fn quote_state(&self) -> Option<QuoteState> {
        if !(self.reserves_authoritative || self.reserves_from_paper_fill)
            || !self.fee_policy_known
            || !self.supported_sol_quote
        {
            return None;
        }
        let fee_bps = self.protocol_fee_bps?;
        let creator_fee_bps = self.creator_fee_bps?;
        if (fee_bps as u32) + (creator_fee_bps as u32) > 10_000 {
            return None;
        }
        Some(QuoteState {
            vsol_raw: self.v_sol,
            vtokens_raw: self.v_tokens,
            rsol_raw: self.r_sol,
            rtokens_raw: self.r_tokens,
            fee_bps,
            creator_fee_bps,
        })
    }

    pub fn is_complete(&self) -> bool {
        (self.reserves_authoritative || self.reserves_from_paper_fill) && self.r_tokens == 0
    }

    fn apply_paper_quote_state(&mut self, state: QuoteState) {
        self.v_sol = state.vsol_raw;
        self.v_tokens = state.vtokens_raw;
        self.r_sol = state.rsol_raw;
        self.r_tokens = state.rtokens_raw;
        self.peak_r_sol = self.peak_r_sol.max(self.r_sol);
        self.reserves_authoritative = false;
        self.reserves_from_paper_fill = true;
    }

    /// Check Developer Gate: returns true if creator holds <= 15% of bag
    pub fn check_developer_gate(&self) -> bool {
        if self.creator_tokens_max == 0 {
            return true;
        }
        let ratio = self.creator_tokens_held as f64 / self.creator_tokens_max as f64;
        ratio <= 0.15
    }

    pub fn developer_held_pct(&self) -> f64 {
        if self.creator_tokens_max == 0 {
            0.0
        } else {
            (self.creator_tokens_held as f64 / self.creator_tokens_max as f64) * 100.0
        }
    }

    /// Execute on-chain trade on the constant-product curve
    pub fn apply_onchain_trade(&mut self, trade: &PumpTradeEvent) {
        self.trades_count += 1;
        self.last_trade_ts = trade.timestamp;
        self.last_slot = trade.slot;

        if let Some(c) = &trade.creator {
            self.creator = Some(c.clone());
        } else if trade.is_create {
            self.creator = Some(trade.user.clone());
        }

        let is_creator = self.creator.as_ref().map_or(false, |c| c == &trade.user);
        if is_creator {
            if trade.is_buy {
                self.creator_bought_tokens = self
                    .creator_bought_tokens
                    .saturating_add(trade.token_amount);
                self.creator_tokens_held =
                    self.creator_tokens_held.saturating_add(trade.token_amount);
                self.creator_tokens_max = self.creator_tokens_max.max(self.creator_tokens_held);
            } else {
                self.creator_sold_tokens =
                    self.creator_sold_tokens.saturating_add(trade.token_amount);
                self.creator_tokens_held =
                    self.creator_tokens_held.saturating_sub(trade.token_amount);
            }
        } else {
            if trade.is_buy {
                self.unique_non_dev_buyers.insert(trade.user.clone());
                if trade.sol_amount >= 0.05 {
                    self.qualified_outside_buyers.insert(trade.user.clone());
                }
            }
            // Canonical S2: Track last 2 eventful outside transactions (buys vs sells)
            self.last_outside_buys.push_back(trade.is_buy);
            if self.last_outside_buys.len() > 2 {
                self.last_outside_buys.pop_front();
            }

            // Canonical S5: Track outside net flow per slot (in lamports)
            let sol_lamports = (trade.sol_amount * 1e9).round() as i64;
            let flow_delta = if trade.is_buy {
                sol_lamports
            } else {
                -sol_lamports
            };
            *self.slot_outside_net_flow.entry(trade.slot).or_insert(0) += flow_delta;
        }

        // Anti-Bundle Tracker 1: Track Block-0 Genesis Bundle buys & Early-Slot Snipers
        if self.created_at_slot == 0 {
            self.created_at_slot = trade.slot;
        }
        if trade.slot <= self.created_at_slot + 1 && trade.is_buy {
            self.block_0_buys_count += 1;
            self.block_0_tokens_bought = self
                .block_0_tokens_bought
                .saturating_add(trade.token_amount);
        }
        if trade.slot <= self.created_at_slot + 10 && trade.is_buy {
            self.early_slots_buys_count += 1;
            self.early_slots_tokens_bought = self
                .early_slots_tokens_bought
                .saturating_add(trade.token_amount);
        }

        // Anti-Bundle Tracker 2: Track exact holder token balances (excluding bonding curve)
        let balance = self.holder_balances.entry(trade.user.clone()).or_insert(0);
        if trade.is_buy {
            *balance = balance.saturating_add(trade.token_amount);
        } else {
            *balance = balance.saturating_sub(trade.token_amount);
        }

        // Anti-Bundle Tracker 3: Track disposable dust / burner wallets (< 0.50 SOL post-trade balance)
        if trade.is_buy {
            if let Some(post_bal) = trade.signer_post_sol_lamports {
                self.total_buyers_evaluated += 1;
                if post_bal < 500_000_000 {
                    self.dust_wallets_count += 1;
                }
            }
        }

        self.prev_r_sol = self.real_sol_reserve();

        // Only authenticated receipt snapshots can establish quote state.
        if let (Some(r_sol), Some(v_sol), Some(v_tokens), Some(r_tokens)) = (
            trade.onchain_rsol,
            trade.onchain_vsol,
            trade.onchain_vtokens,
            trade.onchain_rtokens,
        ) {
            self.r_sol = r_sol;
            self.v_sol = v_sol;
            self.v_tokens = v_tokens;
            self.r_tokens = r_tokens;
            self.protocol_fee_bps = trade.protocol_fee_bps;
            self.creator_fee_bps = trade.creator_fee_bps;
            self.fee_policy_known = trade.fee_policy_known;
            self.supported_sol_quote = trade.supported_sol_quote;
            self.reserves_authoritative = true;
            self.reserves_from_paper_fill = false;
        } else {
            self.reserves_authoritative = false;
            self.reserves_from_paper_fill = false;
            self.fee_policy_known = false;
        }

        self.peak_r_sol = self.peak_r_sol.max(self.r_sol);

        // Spot price history & Canonical Strategy State Updates
        let current_spot = self.spot_price();
        if current_spot > 0.0 {
            // S1 Trough / Peak spot tracking: exactly as in signals.py
            if current_spot >= self.peak_spot {
                self.peak_spot = current_spot;
                self.trough_spot = Some(current_spot);
                self.trough_slot = Some(trade.slot);
                self.trough_outside_buyers.clear();
                self.trough_outside_buy_lamports = 0;
            } else if self.trough_spot.map_or(true, |low| current_spot < low) {
                self.trough_spot = Some(current_spot);
                self.trough_slot = Some(trade.slot);
                self.trough_outside_buyers.clear();
                self.trough_outside_buy_lamports = 0;
            } else if let Some(t_slot) = self.trough_slot {
                if trade.slot <= t_slot + 3 && trade.is_buy && !is_creator {
                    self.trough_outside_buyers.insert(trade.user.clone());
                    self.trough_outside_buy_lamports = self
                        .trough_outside_buy_lamports
                        .saturating_add((trade.sol_amount * 1e9).round() as u64);
                }
            }

            // S3 Dip Detection: >= 15% drop from prior spot and outside sell >= 1.5 SOL
            if let Some(prior) = self.prior_spot {
                let r_sol = self.real_sol_reserve();
                if r_sol >= 8.0
                    && r_sol <= 18.0
                    && current_spot <= prior * 0.85
                    && !trade.is_buy
                    && !is_creator
                    && trade.sol_amount >= 1.5
                {
                    self.s3_dip_slot = Some(trade.slot);
                    self.s3_dip_buyers.clear();
                    self.s3_dip_buy_groups = 0;
                }
            }

            // S3 Two-buyer confirmation within 2 slots of dip
            if let Some(dip_s) = self.s3_dip_slot {
                if trade.slot <= dip_s + 2 {
                    if trade.is_buy && !is_creator && trade.sol_amount >= 0.05 {
                        self.s3_dip_buyers.insert(trade.user.clone());
                        self.s3_dip_buy_groups += 1;
                    }
                } else {
                    self.s3_dip_slot = None;
                    self.s3_dip_buyers.clear();
                    self.s3_dip_buy_groups = 0;
                }
            }

            // S2 Trailing 30s spot tracking
            self.trailing_30s_spot
                .push_back((trade.timestamp, current_spot));
            let cutoff_30s = trade.timestamp.saturating_sub(30);
            while let Some(&(ts, _)) = self.trailing_30s_spot.front() {
                if ts < cutoff_30s {
                    self.trailing_30s_spot.pop_front();
                } else {
                    break;
                }
            }

            self.prior_spot = Some(current_spot);
        }

        // Record recent trade history
        self.recent_trades
            .push_back((trade.timestamp, trade.is_buy, trade.sol_amount));
        while self.recent_trades.len() > 30 {
            self.recent_trades.pop_front();
        }
        let cutoff = trade.timestamp.saturating_sub(30);
        while let Some(&(ts, _, _)) = self.recent_trades.front() {
            if ts < cutoff {
                self.recent_trades.pop_front();
            } else {
                break;
            }
        }
    }

    /// Evaluates multi-layered Anti-Bundle & Bot protection
    pub fn check_anti_bundle_safety(&self, age_secs: u64) -> Result<(), &'static str> {
        // Whitelisted coins (bought by tracked smart money wallets or KOLs) bypass all anti-bundle & cabal checks!
        if self.is_whitelisted {
            return Ok(());
        }

        // 0. Botted Fresh Wallets Cabal: >= 10% burner wallets (< 24h or < 12 txs)
        if self.is_botted_cabal {
            return Err("Botted Fresh Wallets Cabal (>=10% Burners)");
        }

        // Newly spawned microcaps gate: Check block-0 bundle and early sniper swarm volume
        // ONLY for coins that were created <= 10 seconds ago AND are under $10k market cap.
        // Established coins (age > 10s or MCAP >= $10k) bypass early launch volume checks
        // because legitimate high-momentum coins often have heavy initial volume.
        let is_early_spawn = age_secs <= 10 && self.market_cap_usd(145.0) < 10_000.0;
        if is_early_spawn {
            // 1. Block-0 Jito Bundle: > 20% supply bought in block 0
            if self.block_0_tokens_bought > 200_000_000_000_000 {
                return Err("Block-0 Jito Bundle (>20% Supply Bought)");
            }

            // 2. Early-Slot Sniper Swarm: > 20% supply bought in first 10 slots (4s)
            if self.early_slots_tokens_bought > 200_000_000_000_000 {
                return Err("Early-Slot Sniper Swarm (>20% Supply Bought)");
            }
        }

        // 3. Top Holder Concentration: Any single non-curve wallet holding > 7.5% of supply
        let max_held = self.holder_balances.values().copied().max().unwrap_or(0);
        if max_held > 75_000_000_000_000 {
            return Err("Single Whale Holds > 7.5% Supply");
        }

        // 4. Cabal Concentration across Top Holders:
        let mut balances: Vec<u64> = self.holder_balances.values().copied().collect();
        balances.sort_unstable_by(|a, b| b.cmp(a));

        let top_3_sum: u64 = balances.iter().take(3).sum();
        if top_3_sum > 180_000_000_000_000 {
            return Err("Top-3 Cabal Holds > 18% Supply");
        }

        let top_5_sum: u64 = balances.iter().take(5).sum();
        if top_5_sum > 250_000_000_000_000 {
            return Err("Top-5 Cabal Holds > 25% Supply");
        }

        let top_10_sum: u64 = balances.iter().take(10).sum();
        if top_10_sum > 350_000_000_000_000 {
            return Err("Top-10 Cabal Holds > 35% Supply");
        }

        // Current top-holder SOL screening is performed by the RPC holder
        // screen. Historical low-balance buy counts are not its denominator.

        Ok(())
    }

    /// Evaluates Starting 5 triggers against current curve state
    pub fn evaluate_triggers(&mut self, trade: &PumpTradeEvent) -> Option<StrategySignal> {
        let age_secs = trade.timestamp.saturating_sub(self.created_at_ts);

        // Anti-Bundle Gate: Reject any token flagged as a Jito bundle, cabal-concentrated, or botted burner coin
        if let Err(reason) = self.check_anti_bundle_safety(age_secs) {
            self.anti_bundle_reason = Some(reason.to_owned());
            return None;
        }

        self.evaluate_entry_triggers(trade)
    }

    /// Observer only: report source-predicate candidates before admission screens.
    /// Cloning keeps signal_fired and every live runner state unchanged. These are
    /// source predicates, not a claim of canonical registry or deployed-build parity.
    pub fn audit_entry_candidates(&self, trade: &PumpTradeEvent) -> Vec<StrategySignal> {
        let mut audit = self.clone();
        let mut signals = Vec::new();
        while let Some(signal) = audit.evaluate_entry_triggers(trade) {
            signals.push(signal);
        }
        signals
    }

    fn evaluate_entry_triggers(&mut self, trade: &PumpTradeEvent) -> Option<StrategySignal> {
        let r_sol = self.real_sol_reserve();
        let s = self.spot_price();
        let age_secs = trade.timestamp.saturating_sub(self.created_at_ts);
        let is_creator = self.creator.as_ref().map_or(false, |c| c == &trade.user);

        // TRIGGER 1: Strat 1 - Post-Dev Dump Absorption (Canonical 1–5 SOL)
        // Observed creator allocation and sale; creator inventory zero or sold >= 95%;
        // real reserves 1–5 SOL; 25–60% drawdown from prior peak; within 3 slots of post-peak trough;
        // at least 2 distinct outside buyers after trough with total >= 0.30 SOL.
        if !self.signal_fired.contains(&StrategyKind::DevDumpAbsorption) {
            let dev_liquidated = self.creator_bought_tokens > 0
                && self.creator_sold_tokens > 0
                && (self.creator_tokens_held == 0
                    || self.creator_sold_tokens >= (self.creator_bought_tokens * 95 / 100));

            if dev_liquidated && r_sol >= 1.0 && r_sol <= 5.0 && self.peak_spot > 0.0 {
                let dd = 1.0 - (s / self.peak_spot);
                if dd >= 0.25 && dd <= 0.60 {
                    if let Some(t_slot) = self.trough_slot {
                        if trade.slot <= t_slot + 3
                            && self.trough_outside_buyers.len() >= 2
                            && self.trough_outside_buy_lamports >= 300_000_000
                            && trade.is_buy
                            && !is_creator
                        {
                            self.signal_fired.insert(StrategyKind::DevDumpAbsorption);
                            return Some(StrategySignal {
                                strategy: StrategyKind::DevDumpAbsorption,
                                mint: self.mint.clone(),
                                reserve_sol: r_sol,
                                buyer_breadth: self.unique_non_dev_buyers.len(),
                                developer_held_pct: self.developer_held_pct(),
                                timestamp: trade.timestamp,
                                slot: trade.slot,
                                signal_trough_spot: self.trough_spot,
                                details: format!("Canonical S1 Dev absorption: dev liquidated, r={:.2} SOL, dd={:.1}%, trough slot={}, trough buyers={}.", r_sol, dd * 100.0, t_slot, self.trough_outside_buyers.len()),
                            });
                        }
                    }
                }
            }
        }

        // TRIGGER 2: Strat 2 - Survival Shelf Breakout (Canonical 10.8–14 SOL)
        // Cross 10.8 SOL from below, no higher than 14 SOL; age >= 30s;
        // >= 25 historical outside buyers buying >= 0.05 SOL;
        // largest observed holder <= 20% circulating inventory;
        // last 2 eventful transactions outside-buy-only;
        // new price above trailing 30s high.
        if !self
            .signal_fired
            .contains(&StrategyKind::SurvivalShelfBreakout)
        {
            let crossed_10_8 = self.prev_r_sol < 10.8 && r_sol >= 10.8 && r_sol <= 14.0;
            if crossed_10_8 && age_secs >= 30 && self.qualified_outside_buyers.len() >= 25 {
                let circulating: u64 = self.holder_balances.values().copied().sum();
                let max_held = self.holder_balances.values().copied().max().unwrap_or(0);
                let topshare = if circulating > 0 {
                    max_held as f64 / circulating as f64
                } else {
                    1.0
                };

                let last_2_outside_buys =
                    self.last_outside_buys.len() == 2 && self.last_outside_buys.iter().all(|&b| b);

                let cutoff_30s = trade.timestamp.saturating_sub(30);
                let localhigh = self
                    .trailing_30s_spot
                    .iter()
                    .filter(|(ts, _)| *ts >= cutoff_30s && *ts < trade.timestamp)
                    .map(|(_, p)| *p)
                    .fold(0.0f64, f64::max);

                if topshare <= 0.20 && last_2_outside_buys && s > localhigh {
                    self.signal_fired
                        .insert(StrategyKind::SurvivalShelfBreakout);
                    return Some(StrategySignal {
                        strategy: StrategyKind::SurvivalShelfBreakout,
                        mint: self.mint.clone(),
                        reserve_sol: r_sol,
                        buyer_breadth: self.unique_non_dev_buyers.len(),
                        developer_held_pct: self.developer_held_pct(),
                        timestamp: trade.timestamp,
                        slot: trade.slot,
                        signal_trough_spot: None,
                        details: format!("Canonical S2 Survival shelf: cross 10.8 SOL (r={:.2}), qualified buyers={}, topshare={:.1}%, s > localhigh.", r_sol, self.qualified_outside_buyers.len(), topshare * 100.0),
                    });
                }
            }
        }

        // TRIGGER 3: Strat 3 - Two-Buyer Bounce / Deadman Dip (Canonical 8–18 SOL)
        // Original 8–18 SOL dip: >= 15% drop and >= 1.5 SOL outside sell.
        // Then two separate completed buying transactions with distinct noncreator buyers each >= 0.05 SOL within 2 slots;
        // entry remains 8–18 SOL.
        if !self.signal_fired.contains(&StrategyKind::DislocationFloor) {
            if let Some(dip_s) = self.s3_dip_slot {
                if trade.slot <= dip_s + 2
                    && self.s3_dip_buy_groups >= 2
                    && self.s3_dip_buyers.len() >= 2
                    && self.qualified_outside_buyers.len() >= 35
                    && r_sol >= 8.0
                    && r_sol <= 18.0
                    && trade.is_buy
                    && !is_creator
                {
                    self.signal_fired.insert(StrategyKind::DislocationFloor);
                    return Some(StrategySignal {
                        strategy: StrategyKind::DislocationFloor,
                        mint: self.mint.clone(),
                        reserve_sol: r_sol,
                        buyer_breadth: self.unique_non_dev_buyers.len(),
                        developer_held_pct: self.developer_held_pct(),
                        timestamp: trade.timestamp,
                        slot: trade.slot,
                        signal_trough_spot: None,
                        details: format!("Canonical S3 Two-buyer bounce confirmed at r={:.2} SOL by 2 distinct buyers within 2 slots of dip (qualified buyers={}).", r_sol, self.qualified_outside_buyers.len()),
                    });
                }
            }
        }

        // TRIGGER 4: Strat 4 - Upper ATH Breakout (Canonical 16–22 SOL)
        // Reserves 16–22 SOL, new all-time high, >= 35 historical qualified outside buyers,
        // and an outside buy >= 1 SOL in the signal transaction.
        if !self.signal_fired.contains(&StrategyKind::UpperAthBreakout) {
            if r_sol >= 16.0
                && r_sol <= 22.0
                && s >= self.peak_spot
                && self.qualified_outside_buyers.len() >= 35
            {
                if trade.is_buy && !is_creator && trade.sol_amount >= 0.95 {
                    self.signal_fired.insert(StrategyKind::UpperAthBreakout);
                    return Some(StrategySignal {
                        strategy: StrategyKind::UpperAthBreakout,
                        mint: self.mint.clone(),
                        reserve_sol: r_sol,
                        buyer_breadth: self.unique_non_dev_buyers.len(),
                        developer_held_pct: self.developer_held_pct(),
                        timestamp: trade.timestamp,
                        slot: trade.slot,
                        signal_trough_spot: None,
                        details: format!("Canonical S4 Upper ATH breakout at r={:.2} SOL, new ATH spot={:.6}, qualified buyers={}, signal buy={:.2} SOL.", r_sol, s, self.qualified_outside_buyers.len(), trade.sol_amount),
                    });
                }
            }
        }

        // TRIGGER 5: Strat 5 - Carryover (Canonical cross 72 SOL from below)
        // Cross 72 SOL from below, >= 100 observed holders, positive outside net flow over current and 4 preceding slots.
        if !self
            .signal_fired
            .contains(&StrategyKind::PreGraduationCarryover)
        {
            let crossed_72 = self.prev_r_sol < 72.0 && r_sol >= 72.0;
            if crossed_72 {
                let holdercount = self.holder_balances.values().filter(|&&b| b > 0).count();
                if holdercount >= 100 && self.unique_non_dev_buyers.len() >= 50 {
                    let min_slot = trade.slot.saturating_sub(4);
                    let five_slot_net_flow: i64 = self
                        .slot_outside_net_flow
                        .iter()
                        .filter(|(&slot, _)| slot >= min_slot && slot <= trade.slot)
                        .map(|(_, &flow)| flow)
                        .sum();
                    if five_slot_net_flow > 0 {
                        self.signal_fired
                            .insert(StrategyKind::PreGraduationCarryover);
                        return Some(StrategySignal {
                            strategy: StrategyKind::PreGraduationCarryover,
                            mint: self.mint.clone(),
                            reserve_sol: r_sol,
                            buyer_breadth: self.unique_non_dev_buyers.len(),
                            developer_held_pct: self.developer_held_pct(),
                            timestamp: trade.timestamp,
                            slot: trade.slot,
                            signal_trough_spot: None,
                            details: format!("Canonical S5 Carryover: cross 72 SOL from below (r={:.2}), holders={}, 5-slot outside net flow = +{:.3} SOL.", r_sol, holdercount, five_slot_net_flow as f64 / 1e9),
                        });
                    }
                }
            }
        }

        None
    }
}

// ==============================================================================
// REALISTIC EXECUTION & POSITION TRACKER
// ==============================================================================

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub enum PositionState {
    PendingLanding {
        signal_slot: u64,
        signal_reserve: f64,
        ticket_sol: f64,
        trades_seen: u32,
    },
    Open,
    AwaitingMigration,
    Closed,
}

#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub enum PendingOrderStatus {
    Pending,
    AwaitingData,
    Filled,
    GuardFailed,
    RejectedCurveComplete,
    AwaitingMigration,
}

#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub enum ExecutionSide {
    Buy,
    Sell,
}

#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct QuoteStateAudit {
    pub vsol_raw: u64,
    pub vtokens_raw: u64,
    pub rsol_raw: u64,
    pub rtokens_raw: u64,
    pub protocol_fee_bps: u16,
    pub creator_fee_bps: u16,
}

impl From<QuoteState> for QuoteStateAudit {
    fn from(value: QuoteState) -> Self {
        Self {
            vsol_raw: value.vsol_raw,
            vtokens_raw: value.vtokens_raw,
            rsol_raw: value.rsol_raw,
            rtokens_raw: value.rtokens_raw,
            protocol_fee_bps: value.fee_bps,
            creator_fee_bps: value.creator_fee_bps,
        }
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct PendingBuyAudit {
    pub submitted_at_ms: u64,
    pub ready_at_ms: u64,
    pub ticket_raw: u64,
    pub expected_tokens_raw: Option<u64>,
    /// Frozen at the signal-time quote; landing may not relax this guard.
    pub min_tokens_raw: Option<u64>,
    pub signal_quote_state: Option<QuoteStateAudit>,
    pub status: PendingOrderStatus,
    pub last_error: Option<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct PendingExitAudit {
    pub triggered_at_ms: u64,
    pub ready_at_ms: u64,
    pub trigger_reserve_sol: f64,
    pub tokens_raw: u64,
    pub expected_output_raw: Option<u64>,
    /// Frozen at the trigger-time quote; landing may not relax this guard.
    pub min_output_raw: Option<u64>,
    pub trigger_quote_state: Option<QuoteStateAudit>,
    pub full_exit: bool,
    pub reason: String,
    pub status: PendingOrderStatus,
    pub last_error: Option<String>,
    #[serde(default)]
    pub venue: Option<String>,
    #[serde(default)]
    pub trigger_amm_state: Option<AmmSnapshot>,
}

/// Serializable last-attempt audit for the shadow execution path. `filled_at_ms`
/// is the local receive-clock boundary at which the attempt was evaluated; it
/// is not a validator execution timestamp.
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ExecutionAudit {
    pub side: String,
    pub status: String,
    pub triggered_at_ms: u64,
    pub ready_at_ms: u64,
    pub filled_at_ms: u64,
    pub tokens_raw: u64,
    pub quoted_tokens_raw: Option<u64>,
    pub expected_output_raw: Option<u64>,
    pub min_output_raw: Option<u64>,
    pub curve_sol_raw: u64,
    pub protocol_fee_raw: u64,
    pub creator_fee_raw: u64,
    pub gross_cost_raw: Option<u64>,
    pub net_sol_raw: Option<u64>,
    pub network_fee_raw: u64,
    pub state_before: Option<QuoteStateAudit>,
    pub state_after: Option<QuoteStateAudit>,
    pub detail: Option<String>,
    #[serde(default)]
    pub amm_state_before: Option<AmmSnapshot>,
    #[serde(default)]
    pub amm_state_after: Option<AmmSnapshot>,
    #[serde(default)]
    pub lp_fee_raw: u64,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct PaperPosition {
    pub strategy: StrategyKind,
    pub mint: String,
    pub entry_time: u64,
    pub entry_time_ms: u64,
    pub landing_delay_ms: u64,
    pub buy_delay_ms: u64,
    pub sell_delay_ms: u64,
    pub state: PositionState,

    // Causal Token & Cash Accounting
    pub entry_cost_sol: f64, // Ticket (0.50 SOL) + priority fee (0.001505 SOL)
    pub tokens_held: u64,    // Exact token balance received from bonding curve
    pub original_tokens: u64,
    pub network_fees_raw: u64,
    pub signal_reserve_sol: f64, // Reserve when signal was detected
    pub entry_reserve_sol: f64,  // Curve real reserve when buy actually landed
    pub fill_reserve_sol: f64,   // Post-buy reserve (after buy price impact)
    pub buy_slippage_pct: f64,   // Slippage between signal reserve and pre-fill reserve
    pub buy_impact_pct: f64,     // Upward price impact from our buy
    pub current_reserve_sol: f64,
    pub peak_executable_roi: f64,

    // Dynamic Exit & Proceed Tracking
    pub ratchet_active: bool,
    pub tranche1_sold: bool,
    pub tranche1_intent_fired: bool,
    pub tranche1_proceeds: f64,
    pub proceeds_sol: f64,

    pub pending_buy: Option<PendingBuyAudit>,
    pub pending_exit: Option<PendingExitAudit>,
    pub last_fill: Option<ExecutionAudit>,

    pub exit_trigger_reserve_sol: Option<f64>,
    pub exit_reserve_sol: Option<f64>,
    pub exit_slippage_pct: Option<f64>,
    pub sell_impact_pct: Option<f64>,
    pub post_exit_reserve_sol: Option<f64>,
    pub post_exit_change_pct: Option<f64>,
    pub post_exit_note: Option<String>,

    pub is_closed: bool,
    pub exit_reason: Option<String>,
    pub exit_time: Option<u64>,
    pub exit_time_ms: Option<u64>,
    pub entry_slot: Option<u64>,
    pub signal_trough_spot: Option<f64>,
    pub migration_detected_at_ms: Option<u64>,
    pub post_migration_spot_sol: Option<f64>,
    /// Authenticated pool snapshots; legacy spot alone never supports a fill.
    #[serde(default)]
    pub migration_amm: Option<AmmSnapshot>,
    #[serde(default)]
    pub amm_opened_at_ms: Option<u64>,
    #[serde(default)]
    pub amm_own_base_added: u64,
    #[serde(default)]
    pub amm_own_quote_removed: u64,
    #[serde(default)]
    pub amm_own_virtual_delta: i128,
    pub is_whitelisted: bool,
    pub whitelisted_by: Option<String>,
}

impl PaperPosition {
    pub fn new_pending(
        strategy: StrategyKind,
        mint: String,
        signal_slot: u64,
        signal_reserve: f64,
        ticket_sol: f64,
        now_ts: u64,
    ) -> Self {
        Self::new_pending_at_ms(
            strategy,
            mint,
            signal_slot,
            signal_reserve,
            ticket_sol,
            now_ts.saturating_mul(1_000),
            DEFAULT_GHOST_LANDING_DELAY_MS,
        )
    }

    pub fn new_pending_at_ms(
        strategy: StrategyKind,
        mint: String,
        signal_slot: u64,
        signal_reserve: f64,
        ticket_sol: f64,
        now_ms: u64,
        delay_ms: u64,
    ) -> Self {
        Self::new_pending_at_ms_with_delays(
            strategy,
            mint,
            signal_slot,
            signal_reserve,
            ticket_sol,
            now_ms,
            delay_ms,
            delay_ms,
        )
    }

    pub fn new_pending_at_ms_with_delays(
        strategy: StrategyKind,
        mint: String,
        signal_slot: u64,
        signal_reserve: f64,
        ticket_sol: f64,
        now_ms: u64,
        buy_delay_ms: u64,
        sell_delay_ms: u64,
    ) -> Self {
        let ticket_raw = sol_to_raw(ticket_sol).unwrap_or(0);
        Self {
            strategy,
            mint,
            entry_time: now_ms / 1_000,
            entry_time_ms: now_ms,
            landing_delay_ms: buy_delay_ms,
            buy_delay_ms,
            sell_delay_ms,
            state: PositionState::PendingLanding {
                signal_slot,
                signal_reserve,
                ticket_sol,
                trades_seen: 0,
            },
            entry_cost_sol: 0.0,
            tokens_held: 0,
            original_tokens: 0,
            network_fees_raw: 0,
            signal_reserve_sol: signal_reserve,
            entry_reserve_sol: signal_reserve,
            fill_reserve_sol: signal_reserve,
            buy_slippage_pct: 0.0,
            buy_impact_pct: 0.0,
            current_reserve_sol: signal_reserve,
            peak_executable_roi: 0.0,
            ratchet_active: false,
            tranche1_sold: false,
            tranche1_intent_fired: false,
            tranche1_proceeds: 0.0,
            proceeds_sol: 0.0,
            migration_detected_at_ms: None,
            post_migration_spot_sol: None,
            migration_amm: None,
            amm_opened_at_ms: None,
            amm_own_base_added: 0,
            amm_own_quote_removed: 0,
            amm_own_virtual_delta: 0,
            pending_buy: Some(PendingBuyAudit {
                submitted_at_ms: now_ms,
                ready_at_ms: now_ms.saturating_add(buy_delay_ms),
                ticket_raw,
                expected_tokens_raw: None,
                min_tokens_raw: None,
                signal_quote_state: None,
                status: PendingOrderStatus::Pending,
                last_error: None,
            }),
            pending_exit: None,
            last_fill: None,
            exit_trigger_reserve_sol: None,
            exit_reserve_sol: None,
            exit_slippage_pct: None,
            sell_impact_pct: None,
            post_exit_reserve_sol: None,
            post_exit_change_pct: None,
            post_exit_note: None,
            is_closed: false,
            exit_reason: None,
            exit_time: None,
            exit_time_ms: None,
            entry_slot: Some(signal_slot),
            signal_trough_spot: None,
            is_whitelisted: false,
            whitelisted_by: None,
        }
    }

    /// Freeze the expected token output and minimum acceptable output against
    /// the signal-time state. The caller should invoke this immediately after
    /// queuing the signal, before another source transaction is applied.
    pub fn freeze_buy_guard(&mut self, curve: &CurveState) -> Option<u64> {
        let state = curve.quote_state()?;
        let pending = self.pending_buy.as_mut()?;
        if pending.status != PendingOrderStatus::Pending {
            return pending.min_tokens_raw;
        }
        let quote = match state.quote_buy(pending.ticket_raw) {
            Ok(quote) => quote,
            Err(error) => {
                pending.last_error = Some(error.to_string());
                pending.status = PendingOrderStatus::AwaitingData;
                return None;
            }
        };
        let min_tokens = min_output_guard(quote.tokens_raw);
        pending.expected_tokens_raw = Some(quote.tokens_raw);
        pending.min_tokens_raw = Some(min_tokens);
        pending.signal_quote_state = Some(state.into());
        pending.last_error = None;
        Some(min_tokens)
    }

    /// Compatibility wrapper for second-based callers. The 70 ms delay is a
    /// provisional receive-clock assumption, not a measured chain landing.
    pub fn try_land(
        &mut self,
        curve: &mut CurveState,
        current_slot: u64,
        now_ts: u64,
    ) -> Option<bool> {
        let _ = current_slot;
        self.try_land_at_ms(curve, now_ts.saturating_mul(1_000))
    }

    /// Attempt a due pending buy against the latest complete source state.
    /// Missing fee/reserve coverage waits without inventing a fill or fee.
    pub fn try_land_at_ms(&mut self, curve: &mut CurveState, now_ms: u64) -> Option<bool> {
        let pending = self.pending_buy.as_ref()?.clone();
        if !matches!(
            pending.status,
            PendingOrderStatus::Pending | PendingOrderStatus::AwaitingData
        ) || now_ms < pending.ready_at_ms
        {
            return None;
        }
        if !matches!(self.state, PositionState::PendingLanding { .. }) {
            return None;
        }

        let before = curve.quote_state();
        if curve.is_complete() {
            let pending = self.pending_buy.as_mut().expect("pending buy checked");
            pending.status = PendingOrderStatus::RejectedCurveComplete;
            pending.last_error = Some("curve completed before an unsubmitted paper buy".into());
            self.is_closed = true;
            self.state = PositionState::Closed;
            self.entry_cost_sol = 0.0;
            self.proceeds_sol = 0.0;
            self.exit_reason = Some("Curve completed before paper buy submission".into());
            self.exit_time = Some(now_ms / 1_000);
            self.exit_time_ms = Some(now_ms);
            self.last_fill = Some(ExecutionAudit {
                amm_state_before: None, amm_state_after: None, lp_fee_raw: 0,
                side: "buy".into(),
                status: "rejected_curve_complete_unsubmitted".into(),
                triggered_at_ms: pending.submitted_at_ms,
                ready_at_ms: pending.ready_at_ms,
                filled_at_ms: now_ms,
                tokens_raw: 0,
                quoted_tokens_raw: pending.expected_tokens_raw,
                expected_output_raw: pending.expected_tokens_raw,
                min_output_raw: pending.min_tokens_raw,
                curve_sol_raw: 0,
                protocol_fee_raw: 0,
                creator_fee_raw: 0,
                gross_cost_raw: None,
                net_sol_raw: None,
                network_fee_raw: 0,
                state_before: before.map(Into::into),
                state_after: before.map(Into::into),
                detail: pending.last_error.clone(),
            });
            return Some(false);
        }

        let Some(min_tokens_raw) = pending.min_tokens_raw else {
            let pending = self.pending_buy.as_mut().expect("pending buy checked");
            pending.status = PendingOrderStatus::AwaitingData;
            pending
                .last_error
                .get_or_insert_with(|| "signal-time min-output quote unavailable".into());
            return None;
        };
        let Some(before) = before else {
            let pending = self.pending_buy.as_mut().expect("pending buy checked");
            pending.status = PendingOrderStatus::AwaitingData;
            pending.last_error = Some("current receipt reserves or fee policy unavailable".into());
            return None;
        };
        let quote = match before.quote_buy(pending.ticket_raw) {
            Ok(quote) => quote,
            Err(QuoteError::CurveComplete) => {
                let pending = self.pending_buy.as_mut().expect("pending buy checked");
                pending.status = PendingOrderStatus::RejectedCurveComplete;
                pending.last_error = Some(QuoteError::CurveComplete.to_string());
                self.is_closed = true;
                self.state = PositionState::Closed;
                self.entry_cost_sol = 0.0;
                self.proceeds_sol = 0.0;
                self.exit_reason = Some("Curve completed before paper buy submission".into());
                self.exit_time = Some(now_ms / 1_000);
                self.exit_time_ms = Some(now_ms);
                self.last_fill = Some(ExecutionAudit {
                amm_state_before: None, amm_state_after: None, lp_fee_raw: 0,
                    side: "buy".into(),
                    status: "rejected_curve_complete_unsubmitted".into(),
                    triggered_at_ms: pending.submitted_at_ms,
                    ready_at_ms: pending.ready_at_ms,
                    filled_at_ms: now_ms,
                    tokens_raw: 0,
                    quoted_tokens_raw: pending.expected_tokens_raw,
                    expected_output_raw: pending.expected_tokens_raw,
                    min_output_raw: pending.min_tokens_raw,
                    curve_sol_raw: 0,
                    protocol_fee_raw: 0,
                    creator_fee_raw: 0,
                    gross_cost_raw: None,
                    net_sol_raw: None,
                    network_fee_raw: 0,
                    state_before: Some(before.into()),
                    state_after: Some(before.into()),
                    detail: Some(QuoteError::CurveComplete.to_string()),
                });
                return Some(false);
            }
            Err(error) => {
                let pending = self.pending_buy.as_mut().expect("pending buy checked");
                pending.status = PendingOrderStatus::AwaitingData;
                pending.last_error = Some(error.to_string());
                return None;
            }
        };
        if quote.tokens_raw < min_tokens_raw {
            let fee = FAILED_GUARD_FEE_LAMPORTS;
            let after = Some(before);
            let pending_mut = self.pending_buy.as_mut().expect("pending buy checked");
            pending_mut.status = PendingOrderStatus::GuardFailed;
            pending_mut.last_error =
                Some("immutable token min-output guard rejected landing quote".into());
            self.is_closed = true;
            self.state = PositionState::Closed;
            self.entry_cost_sol = raw_to_sol(fee as i128);
            self.network_fees_raw = fee;
            self.proceeds_sol = 0.0;
            self.buy_slippage_pct = match (pending.expected_tokens_raw, quote.tokens_raw) {
                (Some(expected), _) if expected > 0 => {
                    (1.0 - quote.tokens_raw as f64 / expected as f64) * 100.0
                }
                _ => 0.0,
            };
            self.exit_reason = Some("Buy min-output guard failed".into());
            self.exit_time = Some(now_ms / 1_000);
            self.exit_time_ms = Some(now_ms);
            self.last_fill = Some(ExecutionAudit {
                amm_state_before: None, amm_state_after: None, lp_fee_raw: 0,
                side: "buy".into(),
                status: "guard_failed".into(),
                triggered_at_ms: pending.submitted_at_ms,
                ready_at_ms: pending.ready_at_ms,
                filled_at_ms: now_ms,
                tokens_raw: 0,
                quoted_tokens_raw: Some(quote.tokens_raw),
                expected_output_raw: pending.expected_tokens_raw,
                min_output_raw: Some(min_tokens_raw),
                curve_sol_raw: 0,
                protocol_fee_raw: 0,
                creator_fee_raw: 0,
                gross_cost_raw: None,
                net_sol_raw: None,
                network_fee_raw: fee,
                state_before: Some(before.into()),
                state_after: after.map(Into::into),
                detail: pending_mut.last_error.clone(),
            });
            return Some(false);
        }

        let after = match before.moved(quote.curve_sol_raw, quote.tokens_raw, true) {
            Ok(after) => after,
            Err(error) => {
                let pending = self.pending_buy.as_mut().expect("pending buy checked");
                pending.status = PendingOrderStatus::AwaitingData;
                pending.last_error = Some(error.to_string());
                return None;
            }
        };
        let pre_reserve = raw_to_sol(before.rsol_raw as i128);
        curve.apply_paper_quote_state(after);
        let post_reserve = curve.real_sol_reserve();
        let network_fee = STANDARD_NETWORK_FEE_LAMPORTS;
        self.tokens_held = quote.tokens_raw;
        self.original_tokens = quote.tokens_raw;
        self.network_fees_raw = network_fee;
        self.entry_cost_sol = raw_to_sol(quote.total_cost_raw as i128 + network_fee as i128);
        self.buy_slippage_pct = match pending.expected_tokens_raw {
            Some(expected) if expected > 0 => {
                (1.0 - quote.tokens_raw as f64 / expected as f64) * 100.0
            }
            _ => 0.0,
        };
        self.buy_impact_pct = if pre_reserve > 0.0 {
            (post_reserve / pre_reserve - 1.0) * 100.0
        } else {
            0.0
        };
        self.entry_reserve_sol = post_reserve;
        self.fill_reserve_sol = post_reserve;
        self.current_reserve_sol = post_reserve;
        self.entry_time_ms = now_ms;
        self.entry_time = now_ms / 1_000;
        self.state = if after.rtokens_raw == 0 {
            PositionState::AwaitingMigration
        } else {
            PositionState::Open
        };
        self.pending_buy
            .as_mut()
            .expect("pending buy checked")
            .status = PendingOrderStatus::Filled;
        self.last_fill = Some(ExecutionAudit {
                amm_state_before: None, amm_state_after: None, lp_fee_raw: 0,
            side: "buy".into(),
            status: "filled".into(),
            triggered_at_ms: pending.submitted_at_ms,
            ready_at_ms: pending.ready_at_ms,
            filled_at_ms: now_ms,
            tokens_raw: quote.tokens_raw,
            quoted_tokens_raw: Some(quote.tokens_raw),
            expected_output_raw: pending.expected_tokens_raw,
            min_output_raw: Some(min_tokens_raw),
            curve_sol_raw: quote.curve_sol_raw,
            protocol_fee_raw: quote.protocol_fee_raw,
            creator_fee_raw: quote.creator_fee_raw,
            gross_cost_raw: Some(quote.total_cost_raw),
            net_sol_raw: None,
            network_fee_raw: network_fee,
            state_before: Some(before.into()),
            state_after: Some(after.into()),
            detail: None,
        });
        Some(true)
    }

    /// Executable liquidation value for the remaining tokens. Unsupported fee,
    /// quote, reserve or completion states return `None`, never a zero mark.
    pub fn executable_proceeds_sol(&self, curve: &CurveState) -> Option<f64> {
        let now_ms = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default().as_millis() as u64;
        self.executable_proceeds_sol_at_ms(curve, now_ms)
    }

    pub fn executable_proceeds_sol_at_ms(&self, curve: &CurveState, now_ms: u64) -> Option<f64> {
        if self.tokens_held == 0 { return Some(0.0); }
        if self.state == PositionState::AwaitingMigration || curve.is_complete() {
            let snapshot = self.fresh_amm_snapshot(now_ms)?;
            let quote = snapshot.quote_sell(self.tokens_held).ok()?;
            return Some(raw_to_sol(quote.net_sol_raw as i128 - STANDARD_NETWORK_FEE_LAMPORTS as i128));
        }
        let quote = curve.quote_state()?.quote_sell(self.tokens_held).ok()?;
        Some(raw_to_sol(quote.net_sol_raw as i128 - STANDARD_NETWORK_FEE_LAMPORTS as i128))
    }

    fn fresh_amm_snapshot(&self, now_ms: u64) -> Option<&AmmSnapshot> {
        let snapshot = self.migration_amm.as_ref()?;
        if snapshot.mint != self.mint || snapshot.observed_at_ms > now_ms
            || now_ms.saturating_sub(snapshot.observed_at_ms) > 2_000 { return None; }
        Some(snapshot)
    }

    /// Apply authenticated observed reserves plus this paper position's own
    /// accumulated reserve changes. This is diagnostic paper execution, not
    /// a reconstructed counterfactual replay of every external AMM transaction.
    pub fn attach_amm_snapshot(&mut self, mut snapshot: AmmSnapshot) -> Result<(), String> {
        if snapshot.mint != self.mint { return Err("pool mint does not match inventory".into()); }
        if let Some(previous) = &self.migration_amm {
            if previous.pool != snapshot.pool || snapshot.context_slot < previous.context_slot
                || snapshot.observed_at_ms < previous.observed_at_ms {
                return Err("pool identity changed or snapshot regressed".into());
            }
        }
        snapshot.base_reserve_raw = snapshot.base_reserve_raw.checked_add(self.amm_own_base_added)
            .ok_or("paper base inventory overflow")?;
        snapshot.quote_reserve_raw = snapshot.quote_reserve_raw.checked_sub(self.amm_own_quote_removed)
            .ok_or("paper pool quote liquidity exhausted")?;
        snapshot.virtual_quote_reserve_raw = snapshot.virtual_quote_reserve_raw.checked_add(self.amm_own_virtual_delta)
            .ok_or("paper virtual reserve overflow")?;
        let opened = *self.amm_opened_at_ms.get_or_insert(snapshot.observed_at_ms);
        snapshot.opened_at_ms = opened;
        // Legacy spot marks could contain arbitrary-wallet ratios. Never retain
        // their fabricated peaks when upgrading a saved legacy position.
        if self.post_migration_spot_sol.take().is_some() {
            self.peak_executable_roi = 0.0;
        }
        if self.pending_exit.as_ref().is_some_and(|pending|
            pending.venue.is_none() && pending.trigger_quote_state.is_none()) {
            // A legacy spot-only intent is not an authenticated curve/AMM order.
            // Discard the request, preserve every token, and evaluate afresh.
            self.pending_exit=None;
            self.tranche1_intent_fired=false;
        }
        self.migration_detected_at_ms.get_or_insert(snapshot.observed_at_ms);
        self.await_migration();
        self.migration_amm = Some(snapshot);
        if let Some(pending) = self.pending_exit.as_mut() {
            if pending.venue.as_deref() != Some("pumpswap") {
                pending.venue = Some("pumpswap".into());
                pending.status = PendingOrderStatus::AwaitingData;
                pending.ready_at_ms = pending.ready_at_ms.max(opened.saturating_add(self.sell_delay_ms));
                pending.expected_output_raw = None; // Never settle the old spot estimate.
                pending.min_output_raw = Some(0);
                pending.last_error = Some("curve exit carried through migration; await fresh pool quote".into());
            }
        }
        Ok(())
    }

    /// Compatibility wrapper for second-based callers. Exit fills remain
    /// delayed and are completed only by `land_pending_exit_at_ms`.
    pub fn update(&mut self, curve: &mut CurveState, now_ts: u64) -> Option<f64> {
        self.update_at_ms(curve, now_ts.saturating_mul(1_000))
    }

    /// Evaluate the existing exit triggers after a complete source update or
    /// independent timer tick. Triggered exits are queued with a frozen guard.
    pub fn update_at_ms(&mut self, curve: &mut CurveState, now_ms: u64) -> Option<f64> {
        if self.is_closed {
            return None;
        }
        if curve.is_complete() || self.state == PositionState::AwaitingMigration {
            if self.migration_detected_at_ms.is_none() {
                self.migration_detected_at_ms = Some(now_ms);
            }
            self.await_migration();
        }
        if self.state != PositionState::Open && self.state != PositionState::AwaitingMigration {
            return None;
        }
        if self.pending_exit.is_some() {
            return None;
        }

        let migrated = self.state == PositionState::AwaitingMigration;
        let Some(current_liquid_proceeds) = self.executable_proceeds_sol_at_ms(curve, now_ms) else {
            return None;
        };
        self.current_reserve_sol = curve.real_sol_reserve();
        let elapsed_secs = now_ms.saturating_sub(self.entry_time_ms) / 1_000;

        // Net executable ROI includes accrued tranche proceeds and the current
        // remaining-token quote, including each leg's network fee.
        let current_equity = current_liquid_proceeds + self.tranche1_proceeds;
        if self.entry_cost_sol <= 0.0 {
            return None;
        }
        let roi = (current_equity - self.entry_cost_sol) / self.entry_cost_sol;

        if roi > self.peak_executable_roi {
            self.peak_executable_roi = roi;
        }

        match self.strategy {
            // S1: Dev Dump Absorption (Canonical Control Exit)
            // Immediate net <= -10% or spot below signal trough
            // 40% original tokens at +25%
            // Remaining 15 percentage-point giveback from peak ROI
            // No extra breakeven rule and no rigid timeout
            StrategyKind::DevDumpAbsorption => {
                let current_spot = if migrated {
                    let snapshot = self.fresh_amm_snapshot(now_ms)?;
                    ((snapshot.quote_reserve_raw as i128 + snapshot.virtual_quote_reserve_raw) as f64 / 1e9)
                        / (snapshot.base_reserve_raw as f64 / 10f64.powi(snapshot.base_decimals as i32))
                } else { curve.spot_price() };
                let below_trough = self
                    .signal_trough_spot
                    .map_or(false, |trough| current_spot < trough);
                if !self.tranche1_sold && !self.tranche1_intent_fired && roi >= 0.25 {
                    if self.queue_partial_exit(curve, now_ms, 4_000, "S1 +25% tranche") {
                        return None;
                    }
                }
                if self.tranche1_sold {
                    if roi <= self.peak_executable_roi - 0.15 {
                        self.queue_full_exit(
                            curve,
                            now_ms,
                            format!(
                                "Trailing Stop (Peak: +{:.1}%, Exit: {:+.1}%)",
                                self.peak_executable_roi * 100.0,
                                roi * 100.0
                            ),
                        );
                        return None;
                    }
                } else if roi <= -0.10 || below_trough {
                    self.queue_full_exit(
                        curve,
                        now_ms,
                        format!(
                            "S1 Floor Invalidation / Stop Loss (ROI: {:+.1}%, below_trough: {})",
                            roi * 100.0,
                            below_trough
                        ),
                    );
                    return None;
                }
            }

            // S2: Survival Shelf Breakout (Canonical Control Exit)
            // Curve reserves <= 9.8 SOL invalidation
            // Reaching +10% arms net breakeven
            // 40% original tokens at +30%
            // Remaining 15 percentage-point trail
            StrategyKind::SurvivalShelfBreakout => {
                if !migrated && self.current_reserve_sol <= 9.8 {
                    self.queue_full_exit(
                        curve,
                        now_ms,
                        "Curve reserves <= 9.8 SOL invalidation".to_string(),
                    );
                    return None;
                }
                if roi >= 0.10 {
                    self.ratchet_active = true;
                }
                if self.ratchet_active && !self.tranche1_sold && roi <= 0.00 {
                    self.queue_full_exit(
                        curve,
                        now_ms,
                        "Breakeven Ratchet (armed at +10%)".to_string(),
                    );
                    return None;
                }
                if !self.tranche1_sold && !self.tranche1_intent_fired && roi >= 0.30 {
                    if self.queue_partial_exit(curve, now_ms, 4_000, "S2 +30% tranche") {
                        return None;
                    }
                }
                if self.tranche1_sold {
                    if roi <= self.peak_executable_roi - 0.15 {
                        self.queue_full_exit(
                            curve,
                            now_ms,
                            format!(
                                "Trailing Stop (Peak: +{:.1}%, Exit: {:+.1}%)",
                                self.peak_executable_roi * 100.0,
                                roi * 100.0
                            ),
                        );
                        return None;
                    }
                }
            }

            // S3: Two-Buyer Bounce / Deadman Dip (Canonical Control Exit)
            // 8s grace before relative 12% loss stop from fee-inclusive average fill
            // Dynamic trailing ratchet: arm at +20% with 10 percentage-point trail
            // 60s primary timeout
            StrategyKind::DislocationFloor => {
                if self.peak_executable_roi >= 0.20 {
                    self.ratchet_active = true;
                }
                if self.ratchet_active && roi <= self.peak_executable_roi - 0.10 {
                    self.queue_full_exit(
                        curve,
                        now_ms,
                        format!(
                            "S3 Trailing Exit (Peak: +{:.1}%, Exit: {:+.1}%)",
                            self.peak_executable_roi * 100.0,
                            roi * 100.0
                        ),
                    );
                    return None;
                }
                if elapsed_secs >= 18 && roi <= -0.18 {
                    self.queue_full_exit(
                        curve,
                        now_ms,
                        format!(
                            "S3 Relative -18% Stop Loss 18s grace (ROI: {:+.1}%)",
                            roi * 100.0
                        ),
                    );
                    return None;
                }
                if elapsed_secs >= 60 {
                    self.queue_full_exit(curve, now_ms, "S3 60s Primary Timeout".to_string());
                    return None;
                }
            }

            // S4: Upper ATH Breakout (Canonical Control Exit)
            // Calibrated rejection stop: require at least 12 slots (~5s) and net <= -14% (to absorb initial -6.2% entry friction)
            // Immediate catastrophic stop if net <= -22%
            // 50% at +20%
            // 6% relative wealth-factor trail on remainder
            // No declared long-runner deadline
            StrategyKind::UpperAthBreakout => {
                if !self.tranche1_sold && !self.tranche1_intent_fired && roi >= 0.20 {
                    if self.queue_partial_exit(curve, now_ms, 5_000, "S4 +20% tranche") {
                        return None;
                    }
                }
                if self.tranche1_sold {
                    if (1.0 + roi) <= (1.0 + self.peak_executable_roi) * 0.94 {
                        self.queue_full_exit(
                            curve,
                            now_ms,
                            format!(
                                "Trailing Stop (Peak: +{:.1}%, Exit: {:+.1}%)",
                                self.peak_executable_roi * 100.0,
                                roi * 100.0
                            ),
                        );
                        return None;
                    }
                } else if roi <= -0.22 {
                    self.queue_full_exit(
                        curve,
                        now_ms,
                        format!("Severe Dump Stop (ROI: {:+.1}%)", roi * 100.0),
                    );
                    return None;
                } else if let Some(e_slot) = self.entry_slot {
                    let current_slot = self.fresh_amm_snapshot(now_ms).map_or(curve.last_slot, |pool| pool.context_slot);
                    if current_slot >= e_slot + 12 && roi <= -0.14 && self.peak_executable_roi < 0.10 {
                        self.queue_full_exit(
                            curve,
                            now_ms,
                            format!("Rejection Stop (>=12 slots, ROI: {:+.1}%)", roi * 100.0),
                        );
                        return None;
                    }
                }
            }

            // S5: Pre-Graduation AMM Carryover (Canonical Control Exit)
            // Curve reserves <= 60 SOL invalidation
            // 30s after AMM opening timeout in primary lower endpoint
            StrategyKind::PreGraduationCarryover => {
                if migrated {
                    if !self.tranche1_sold && !self.tranche1_intent_fired {
                        self.queue_partial_exit(curve, now_ms, 5_000, "S5 half at authenticated AMM opening");
                        return None;
                    }
                    if self.tranche1_sold && (1.0 + roi) <= (1.0 + self.peak_executable_roi) * 0.92 {
                        self.queue_full_exit(curve, now_ms, "S5 AMM 8% relative trailing exit".into());
                        return None;
                    }
                    if self.amm_opened_at_ms.is_some_and(|opened| now_ms.saturating_sub(opened) >= 30_000) {
                        self.queue_full_exit(curve, now_ms, "S5 30s after authenticated AMM opening timeout".into());
                    }
                    return None;
                }
                if self.current_reserve_sol <= 60.0 {
                    self.queue_full_exit(
                        curve,
                        now_ms,
                        "Reserve Invalidation (<= 60 SOL)".to_string(),
                    );
                    return None;
                }
            }
        }

        None
    }

    fn queue_partial_exit(
        &mut self,
        curve: &CurveState,
        now_ms: u64,
        fraction_bps: u64,
        reason: &str,
    ) -> bool {
        let tokens_raw = ((self.original_tokens as u128) * (fraction_bps as u128) / 10_000) as u64;
        if tokens_raw == 0 || tokens_raw > self.tokens_held {
            return false;
        }
        let queued = self.queue_exit(
            curve,
            now_ms,
            self.sell_delay_ms,
            tokens_raw,
            false,
            reason.to_owned(),
        );
        if queued {
            self.tranche1_intent_fired = true;
        }
        queued
    }

    fn queue_full_exit(&mut self, curve: &CurveState, now_ms: u64, reason: String) -> bool {
        if self.tokens_held == 0 {
            return false;
        }
        self.queue_exit(
            curve,
            now_ms,
            self.sell_delay_ms,
            self.tokens_held,
            true,
            reason,
        )
    }

    fn queue_amm_exit(&mut self, now_ms: u64, tokens_raw: u64, full_exit: bool, reason: String) -> bool {
        if self.pending_exit.is_some() || tokens_raw == 0 || tokens_raw > self.tokens_held { return false; }
        let Some(snapshot) = self.fresh_amm_snapshot(now_ms).cloned() else { return false; };
        let Ok(quote) = snapshot.quote_sell(tokens_raw) else { return false; };
        self.pending_exit = Some(PendingExitAudit {
            venue: Some("pumpswap".into()), trigger_amm_state: Some(snapshot),
            triggered_at_ms: now_ms, ready_at_ms: now_ms.saturating_add(self.sell_delay_ms),
            trigger_reserve_sol: self.current_reserve_sol, tokens_raw,
            expected_output_raw: Some(quote.net_sol_raw), min_output_raw: Some(0),
            trigger_quote_state: None, full_exit, reason,
            status: PendingOrderStatus::Pending, last_error: None,
        });
        true
    }

    fn queue_exit(
        &mut self,
        curve: &CurveState,
        now_ms: u64,
        delay_ms: u64,
        tokens_raw: u64,
        full_exit: bool,
        reason: String,
    ) -> bool {
        if self.state == PositionState::AwaitingMigration || curve.is_complete() {
            return self.queue_amm_exit(now_ms, tokens_raw, full_exit, reason);
        }
        if self.pending_exit.is_some() { return false; }
        let Some(state) = curve.quote_state() else {
            return false;
        };
        let Ok(quote) = state.quote_sell(tokens_raw) else {
            return false;
        };
        // Exits accept the available landing quote. The trigger quote is audit
        // evidence, not a price floor that can block escape during a dump.
        // Entry orders retain their frozen slippage guards.
        let min_output_raw = 0;
        let trigger_reserve_sol = curve.real_sol_reserve();
        self.exit_trigger_reserve_sol = Some(trigger_reserve_sol);
        self.pending_exit = Some(PendingExitAudit {
            venue: None, trigger_amm_state: None,
            triggered_at_ms: now_ms,
            ready_at_ms: now_ms.saturating_add(delay_ms),
            trigger_reserve_sol,
            tokens_raw,
            expected_output_raw: Some(quote.net_sol_raw),
            min_output_raw: Some(min_output_raw),
            trigger_quote_state: Some(state.into()),
            full_exit,
            reason,
            status: PendingOrderStatus::Pending,
            last_error: None,
        });
        true
    }

    fn await_migration(&mut self) {
        if self.tokens_held == 0 || self.is_closed { return; }
        self.state = PositionState::AwaitingMigration;
        if let Some(pending) = self.pending_exit.as_mut() {
            if pending.venue.as_deref() != Some("pumpswap") && matches!(pending.status,
                PendingOrderStatus::Pending | PendingOrderStatus::AwaitingData) {
                pending.status = PendingOrderStatus::AwaitingMigration;
                pending.last_error = Some("curve complete; awaiting authenticated pool coverage".into());
            }
        }
    }

    fn land_amm_exit_at_ms(&mut self, now_ms: u64) -> Option<f64> {
        let pending = self.pending_exit.as_ref()?.clone();
        if now_ms < pending.ready_at_ms { return None; }
        let Some(before) = self.fresh_amm_snapshot(now_ms).cloned().filter(|p|p.observed_at_ms >= pending.ready_at_ms) else {
            let waiting_for_pool=self.migration_amm.is_none();
            let p = self.pending_exit.as_mut()?;
            p.status = if waiting_for_pool {PendingOrderStatus::AwaitingMigration} else {PendingOrderStatus::AwaitingData};
            p.last_error = Some("need authenticated pool snapshot observed after ready time".into());
            return None;
        };
        if pending.tokens_raw > self.tokens_held { return None; }
        let quote = match before.quote_sell(pending.tokens_raw) {
            Ok(quote) => quote,
            Err(error) => { let p = self.pending_exit.as_mut()?; p.status = PendingOrderStatus::AwaitingData; p.last_error = Some(error); return None; }
        };
        let after = match quote.state_after(&before) { Ok(s) => s, Err(_) => return None };
        let quote_removed = before.quote_reserve_raw.checked_sub(after.quote_reserve_raw)?;
        let own_base = self.amm_own_base_added.checked_add(pending.tokens_raw)?;
        let own_quote = self.amm_own_quote_removed.checked_add(quote_removed)?;
        let own_virtual = self.amm_own_virtual_delta.checked_add(
            after.virtual_quote_reserve_raw.checked_sub(before.virtual_quote_reserve_raw)?)?;
        self.amm_own_base_added=own_base;
        self.amm_own_quote_removed=own_quote;
        self.amm_own_virtual_delta=own_virtual;
        let wallet_credit = raw_to_sol(quote.net_sol_raw as i128 - STANDARD_NETWORK_FEE_LAMPORTS as i128);
        self.network_fees_raw = self.network_fees_raw.saturating_add(STANDARD_NETWORK_FEE_LAMPORTS);
        self.tokens_held -= pending.tokens_raw;
        self.migration_amm = Some(after.clone());
        self.pending_exit = None;
        self.last_fill = Some(ExecutionAudit {
            side: "sell".into(), status: if self.tokens_held==0 {"paper_filled_migrated_full"} else {"paper_filled_migrated_partial"}.into(),
            triggered_at_ms: pending.triggered_at_ms, ready_at_ms: pending.ready_at_ms, filled_at_ms: now_ms,
            tokens_raw: pending.tokens_raw, quoted_tokens_raw: Some(pending.tokens_raw),
            expected_output_raw: pending.expected_output_raw, min_output_raw: Some(0),
            curve_sol_raw: quote.gross_sol_raw, protocol_fee_raw: quote.protocol_fee_raw,
            creator_fee_raw: quote.creator_fee_raw, lp_fee_raw: quote.lp_fee_raw,
            gross_cost_raw: None, net_sol_raw: Some(quote.net_sol_raw), network_fee_raw: STANDARD_NETWORK_FEE_LAMPORTS,
            state_before: None, state_after: None, amm_state_before: Some(before), amm_state_after: Some(after),
            detail: Some(format!("{}; authenticated reserve quote; provisional paper fill, not an on-chain sale",pending.reason)),
        });
        if self.tokens_held==0 {
            self.is_closed=true; self.state=PositionState::Closed;
            self.exit_reason=Some(pending.reason); self.exit_time=Some(now_ms/1000); self.exit_time_ms=Some(now_ms);
            self.proceeds_sol=self.tranche1_proceeds+wallet_credit;
            return Some(self.proceeds_sol-self.entry_cost_sol);
        }
        self.tranche1_sold=true;
        self.tranche1_proceeds+=wallet_credit;
        self.proceeds_sol=self.tranche1_proceeds;
        None
    }

    /// Land a due pending partial or final sell. `Some(pnl)` is returned only
    /// after the full remaining inventory has actually filled on the curve.
    pub fn land_pending_exit_at_ms(&mut self, curve: &mut CurveState, now_ms: u64) -> Option<f64> {
        let pending = self.pending_exit.as_ref()?.clone();
        if self.state == PositionState::AwaitingMigration || curve.is_complete() {
            self.await_migration();
            return self.land_amm_exit_at_ms(now_ms);
        }
        if !matches!(pending.status, PendingOrderStatus::Pending | PendingOrderStatus::AwaitingData)
            || now_ms < pending.ready_at_ms { return None; }
        let Some(before) = curve.quote_state() else {
            let pending = self.pending_exit.as_mut().expect("pending exit checked");
            pending.status = PendingOrderStatus::AwaitingData;
            pending.last_error = Some("current receipt reserves or fee policy unavailable".into());
            return None;
        };
        let Some(min_output_raw) = pending.min_output_raw else {
            let pending = self.pending_exit.as_mut().expect("pending exit checked");
            pending.status = PendingOrderStatus::AwaitingData;
            pending.last_error = Some("trigger-time min-output quote unavailable".into());
            return None;
        };
        let quote = match before.quote_sell(pending.tokens_raw) {
            Ok(quote) => quote,
            Err(QuoteError::CurveComplete) => {
                self.await_migration();
                return None;
            }
            Err(error) => {
                let pending = self.pending_exit.as_mut().expect("pending exit checked");
                pending.status = PendingOrderStatus::AwaitingData;
                pending.last_error = Some(error.to_string());
                return None;
            }
        };
        if quote.net_sol_raw < min_output_raw {
            let fee = FAILED_GUARD_FEE_LAMPORTS;
            self.network_fees_raw = self.network_fees_raw.saturating_add(fee);
            self.tranche1_proceeds -= raw_to_sol(fee as i128);
            self.proceeds_sol = self.tranche1_proceeds;
            self.tranche1_intent_fired = false;
            let detail = "immutable SOL min-output guard rejected landing quote".to_string();
            self.pending_exit = None;
            self.last_fill = Some(ExecutionAudit {
                amm_state_before: None, amm_state_after: None, lp_fee_raw: 0,
                side: "sell".into(),
                status: "guard_failed".into(),
                triggered_at_ms: pending.triggered_at_ms,
                ready_at_ms: pending.ready_at_ms,
                filled_at_ms: now_ms,
                tokens_raw: 0,
                quoted_tokens_raw: Some(quote.tokens_raw),
                expected_output_raw: pending.expected_output_raw,
                min_output_raw: Some(min_output_raw),
                curve_sol_raw: 0,
                protocol_fee_raw: 0,
                creator_fee_raw: 0,
                gross_cost_raw: None,
                net_sol_raw: None,
                network_fee_raw: fee,
                state_before: Some(before.into()),
                state_after: Some(before.into()),
                detail: Some(detail),
            });
            return None;
        }
        let after = match before.moved(quote.gross_sol_raw, quote.tokens_raw, false) {
            Ok(after) => after,
            Err(error) => {
                let pending = self.pending_exit.as_mut().expect("pending exit checked");
                pending.status = PendingOrderStatus::AwaitingData;
                pending.last_error = Some(error.to_string());
                return None;
            }
        };
        let pre_reserve = curve.real_sol_reserve();
        curve.apply_paper_quote_state(after);
        let post_reserve = curve.real_sol_reserve();
        let network_fee = STANDARD_NETWORK_FEE_LAMPORTS;
        let wallet_credit = raw_to_sol(quote.net_sol_raw as i128 - network_fee as i128);
        self.network_fees_raw = self.network_fees_raw.saturating_add(network_fee);
        self.tokens_held = self.tokens_held.saturating_sub(quote.tokens_raw);
        self.exit_reserve_sol = Some(post_reserve);
        self.sell_impact_pct = Some(if pre_reserve > 0.0 {
            (post_reserve / pre_reserve - 1.0) * 100.0
        } else {
            0.0
        });
        self.pending_exit = None;
        if pending.full_exit && self.tokens_held == 0 {
            self.is_closed = true;
            self.state = PositionState::Closed;
            self.exit_reason = Some(pending.reason.clone());
            self.exit_time = Some(now_ms / 1_000);
            self.exit_time_ms = Some(now_ms);
            self.proceeds_sol = self.tranche1_proceeds + wallet_credit;
            self.last_fill = Some(ExecutionAudit {
                amm_state_before: None, amm_state_after: None, lp_fee_raw: 0,
                side: "sell".into(),
                status: "filled_full_close".into(),
                triggered_at_ms: pending.triggered_at_ms,
                ready_at_ms: pending.ready_at_ms,
                filled_at_ms: now_ms,
                tokens_raw: quote.tokens_raw,
                quoted_tokens_raw: Some(quote.tokens_raw),
                expected_output_raw: pending.expected_output_raw,
                min_output_raw: Some(min_output_raw),
                curve_sol_raw: quote.gross_sol_raw,
                protocol_fee_raw: quote.protocol_fee_raw,
                creator_fee_raw: quote.creator_fee_raw,
                gross_cost_raw: None,
                net_sol_raw: Some(quote.net_sol_raw),
                network_fee_raw: network_fee,
                state_before: Some(before.into()),
                state_after: Some(after.into()),
                detail: Some(pending.reason),
            });
            return Some(self.proceeds_sol - self.entry_cost_sol);
        }

        self.tranche1_sold = true;
        self.tranche1_proceeds += wallet_credit;
        self.proceeds_sol = self.tranche1_proceeds;
        self.last_fill = Some(ExecutionAudit {
                amm_state_before: None, amm_state_after: None, lp_fee_raw: 0,
            side: "sell".into(),
            status: "filled_partial".into(),
            triggered_at_ms: pending.triggered_at_ms,
            ready_at_ms: pending.ready_at_ms,
            filled_at_ms: now_ms,
            tokens_raw: quote.tokens_raw,
            quoted_tokens_raw: Some(quote.tokens_raw),
            expected_output_raw: pending.expected_output_raw,
            min_output_raw: Some(min_output_raw),
            curve_sol_raw: quote.gross_sol_raw,
            protocol_fee_raw: quote.protocol_fee_raw,
            creator_fee_raw: quote.creator_fee_raw,
            gross_cost_raw: None,
            net_sol_raw: Some(quote.net_sol_raw),
            network_fee_raw: network_fee,
            state_before: Some(before.into()),
            state_after: Some(after.into()),
            detail: Some(pending.reason),
        });
        None
    }
}

fn sol_to_raw(sol: f64) -> Option<u64> {
    if !sol.is_finite() || sol <= 0.0 || sol > u64::MAX as f64 / 1e9 {
        return None;
    }
    Some((sol * 1e9).round() as u64)
}

fn raw_to_sol(raw: i128) -> f64 {
    raw as f64 / 1e9
}

pub fn configured_buy_slippage_bps() -> u64 {
    if let Ok(raw) = std::env::var("BUY_SLIPPAGE_PCT") {
        if let Ok(pct) = raw.parse::<f64>() {
            if pct.is_finite() && (0.0..=99.0).contains(&pct) { return (pct*100.0).round() as u64; }
        }
        return 10_000-DEFAULT_MIN_OUTPUT_RETAINED_BPS;
    }
    std::env::var("BUY_SLIPPAGE_BPS").ok().and_then(|v|v.parse::<u64>().ok())
        .filter(|v|*v<=9_900).unwrap_or(10_000-DEFAULT_MIN_OUTPUT_RETAINED_BPS)
}

fn guard_for_slippage_bps(expected_raw: u64, slippage_bps: u64) -> u64 {
    ((expected_raw as u128)*(10_000-slippage_bps.min(9_900)) as u128/10_000) as u64
}

fn min_output_guard(expected_raw: u64) -> u64 {
    guard_for_slippage_bps(expected_raw,configured_buy_slippage_bps())
}

// ==============================================================================
// CURVE MANAGER
// ==============================================================================

pub struct CurveManager {
    pub curves: HashMap<String, CurveState>,
}

impl CurveManager {
    pub fn new() -> Self {
        Self {
            curves: HashMap::new(),
        }
    }

    pub fn register_create(&mut self, mint: &str, creator: &str, now_ts: u64) {
        let entry = self.curves.entry(mint.to_string()).or_insert_with(|| {
            CurveState::new(mint.to_string(), Some(creator.to_string()), now_ts)
        });
        entry.creator = Some(creator.to_string());
    }

    pub fn process_trade(&mut self, trade: PumpTradeEvent) -> Option<StrategySignal> {
        let entry = self
            .curves
            .entry(trade.mint.clone())
            .or_insert_with(|| CurveState::new(trade.mint.clone(), None, trade.timestamp));
        entry.apply_onchain_trade(&trade);
        entry.evaluate_triggers(&trade)
    }

    /// Apply every event from one successful transaction before evaluating
    /// any trigger. Same-transaction events remain atomic to a paper order.
    pub fn process_transaction_events(&mut self, trades: &[PumpTradeEvent]) -> Vec<StrategySignal> {
        let mut mint_order = Vec::new();
        let mut last_trade_by_mint: HashMap<String, PumpTradeEvent> = HashMap::new();
        for trade in trades {
            let entry = self
                .curves
                .entry(trade.mint.clone())
                .or_insert_with(|| CurveState::new(trade.mint.clone(), None, trade.timestamp));
            entry.apply_onchain_trade(trade);
            if !last_trade_by_mint.contains_key(&trade.mint) {
                mint_order.push(trade.mint.clone());
            }
            last_trade_by_mint.insert(trade.mint.clone(), trade.clone());
        }

        mint_order
            .into_iter()
            .filter_map(|mint| {
                let trade = last_trade_by_mint.get(&mint)?;
                self.curves.get_mut(&mint)?.evaluate_triggers(trade)
            })
            .collect()
    }

    pub fn prune_old_curves(&mut self, max_idle_secs: u64, now_ts: u64) {
        let cutoff = now_ts.saturating_sub(max_idle_secs);
        self.curves.retain(|_, c| c.last_trade_ts >= cutoff);
    }
}

// ==============================================================================
// CIRCUIT BREAKER
// ==============================================================================

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct CircuitBreaker {
    pub streak_limit: usize,
    pub loss_ceiling_sol: f64,
    pub cooldown_secs: u64,
    pub window_secs: u64,
    pub consecutive_losses: usize,
    pub trade_history: VecDeque<(u64, f64)>,
    pub cooldown_until: u64,
    pub trip_count: usize,
}

impl CircuitBreaker {
    pub fn for_strategy(strat: StrategyKind) -> Self {
        match strat {
            StrategyKind::DevDumpAbsorption => Self {
                streak_limit: 5,
                loss_ceiling_sol: 0.60,
                cooldown_secs: 3 * 3600,
                window_secs: 6 * 3600,
                consecutive_losses: 0,
                trade_history: VecDeque::new(),
                cooldown_until: 0,
                trip_count: 0,
            },
            StrategyKind::SurvivalShelfBreakout => Self {
                streak_limit: 8,
                loss_ceiling_sol: 0.60,
                cooldown_secs: 4 * 3600,
                window_secs: 8 * 3600,
                consecutive_losses: 0,
                trade_history: VecDeque::new(),
                cooldown_until: 0,
                trip_count: 0,
            },
            StrategyKind::DislocationFloor => Self {
                streak_limit: 10,
                loss_ceiling_sol: 0.50,
                cooldown_secs: 2 * 3600,
                window_secs: 4 * 3600,
                consecutive_losses: 0,
                trade_history: VecDeque::new(),
                cooldown_until: 0,
                trip_count: 0,
            },
            StrategyKind::UpperAthBreakout => Self {
                streak_limit: 6,
                loss_ceiling_sol: 0.75,
                cooldown_secs: 4 * 3600,
                window_secs: 8 * 3600,
                consecutive_losses: 0,
                trade_history: VecDeque::new(),
                cooldown_until: 0,
                trip_count: 0,
            },
            StrategyKind::PreGraduationCarryover => Self {
                streak_limit: 5,
                loss_ceiling_sol: 0.80,
                cooldown_secs: 6 * 3600,
                window_secs: 12 * 3600,
                consecutive_losses: 0,
                trade_history: VecDeque::new(),
                cooldown_until: 0,
                trip_count: 0,
            },
        }
    }

    pub fn is_cooling_down(&self, now_ts: u64) -> bool {
        now_ts < self.cooldown_until
    }

    pub fn record_trade(&mut self, pnl: f64, now_ts: u64) {
        self.trade_history.push_back((now_ts, pnl));
        if pnl > 0.0 {
            self.consecutive_losses = 0;
        } else {
            self.consecutive_losses += 1;
        }

        let cutoff = now_ts.saturating_sub(self.window_secs);
        while let Some(&(ts, _)) = self.trade_history.front() {
            if ts < cutoff {
                self.trade_history.pop_front();
            } else {
                break;
            }
        }

        let rolling_pnl: f64 = self.trade_history.iter().map(|&(_, p)| p).sum();
        let streak_tripped = self.consecutive_losses >= self.streak_limit;
        let ceiling_tripped = rolling_pnl <= -self.loss_ceiling_sol;

        if streak_tripped || ceiling_tripped {
            self.cooldown_until = now_ts + self.cooldown_secs;
            self.trip_count += 1;
            self.consecutive_losses = 0;
        }
    }
}

// ==============================================================================
// TELEMETRY & PERSISTENCE
// ==============================================================================

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct GhostTradeRecord {
    pub event: String, // "OPEN", "CLOSE", "GUARD_FAIL", or "POST_EXIT_UPDATE"
    pub vm_id: String,
    pub timestamp: u64,
    pub datetime_utc: String,
    pub strategy: String,
    pub strategy_code: String,
    pub mint: String,
    pub signal_reserve_sol: Option<f64>,
    pub entry_reserve_sol: f64,
    pub buy_slippage_pct: Option<f64>,
    pub buy_impact_pct: Option<f64>,
    pub tokens_held: u64,
    pub exit_trigger_reserve_sol: Option<f64>,
    pub exit_reserve_sol: Option<f64>,
    pub exit_slippage_pct: Option<f64>,
    pub sell_impact_pct: Option<f64>,
    pub post_exit_reserve_sol: Option<f64>,
    pub post_exit_change_pct: Option<f64>,
    pub post_exit_note: Option<String>,
    pub entry_cost_sol: f64,
    pub proceeds_sol: f64,
    pub net_pnl_sol: f64,
    pub pnl_pct: f64,
    pub peak_roi_pct: f64,
    pub duration_secs: u64,
    pub exit_reason: Option<String>,
    pub virtual_cash_after: f64,
    pub total_equity_after: f64,
    #[serde(default)]
    pub is_whitelisted: bool,
    #[serde(default)]
    pub whitelisted_by: Option<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct StrategySummaryStats {
    pub code: String,
    pub trades: usize,
    pub wins: usize,
    pub losses: usize,
    pub win_rate_pct: f64,
    pub net_pnl_sol: f64,
    pub avg_pnl_sol: f64,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ActivePositionSnapshot {
    pub strategy: String,
    pub strategy_code: String,
    pub mint: String,
    pub signal_reserve_sol: f64,
    pub entry_reserve_sol: f64,
    pub current_reserve_sol: f64,
    pub tokens_held: u64,
    pub executable_proceeds_sol: Option<f64>,
    pub roi_pct: Option<f64>,
    pub peak_roi_pct: f64,
    pub elapsed_secs: u64,
    pub status: String, // "PENDING_LANDING" or "OPEN"
    #[serde(default)]
    pub is_whitelisted: bool,
    #[serde(default)]
    pub whitelisted_by: Option<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct CircuitBreakerSnapshot {
    pub strategy_code: String,
    pub is_cooling: bool,
    pub cooldown_remaining_secs: u64,
    pub consecutive_losses: usize,
    pub streak_limit: usize,
    pub trip_count: usize,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ShieldedCoinRecord {
    pub mint: String,
    pub timestamp: u64,
    pub datetime_utc: String,
    pub reserve_sol: f64,
    pub market_cap_usd: f64,
    pub reason: String,
    pub layer: String,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct GhostSummary {
    pub vm_id: String,
    pub updated_at_utc: String,
    pub uptime_secs: u64,
    pub virtual_cash_sol: f64,
    pub total_equity_sol: f64,
    pub active_positions_count: usize,
    pub total_closed_trades: usize,
    pub wins: usize,
    pub losses: usize,
    pub win_rate_pct: f64,
    pub total_net_pnl_sol: f64,
    pub profit_factor: f64,
    pub strategy_breakdown: HashMap<String, StrategySummaryStats>,
    pub active_positions: Vec<ActivePositionSnapshot>,
    pub recent_closed_trades: Vec<GhostTradeRecord>,
    pub circuit_breaker_statuses: HashMap<String, CircuitBreakerSnapshot>,
    #[serde(default)]
    pub total_shielded_coins: usize,
    #[serde(default)]
    pub recent_shielded_coins: Vec<ShieldedCoinRecord>,
}

pub fn log_ghost_trade(path_str: &str, record: &GhostTradeRecord) -> std::io::Result<()> {
    if let Some(parent) = Path::new(path_str).parent() {
        create_dir_all(parent)?;
    }
    let mut file = OpenOptions::new()
        .create(true)
        .append(true)
        .open(path_str)?;
    let line = serde_json::to_string(record)
        .map_err(|e| std::io::Error::new(std::io::ErrorKind::Other, e))?;
    writeln!(file, "{}", line)?;
    Ok(())
}

pub fn save_ghost_summary(path_str: &str, summary: &GhostSummary) -> std::io::Result<()> {
    if let Some(parent) = Path::new(path_str).parent() {
        create_dir_all(parent)?;
    }
    let tmp_path = format!("{}.tmp", path_str);
    let json_bytes = serde_json::to_vec_pretty(summary)
        .map_err(|e| std::io::Error::new(std::io::ErrorKind::Other, e))?;
    {
        let mut file = File::create(&tmp_path)?;
        file.write_all(&json_bytes)?;
    }
    std::fs::rename(tmp_path, path_str)?;
    Ok(())
}

#[cfg(test)]
mod ghost_fill_tests {
    use super::*;

    #[test]
    fn default_buy_guard_retains_ninety_percent_and_rounds_down() {
        assert_eq!(DEFAULT_MIN_OUTPUT_RETAINED_BPS,9_000);
        assert_eq!(guard_for_slippage_bps(1_000_000,1_000),900_000);
        assert_eq!(guard_for_slippage_bps(100_001,1_000),90_000);
    }


    fn quoted_curve() -> CurveState {
        let mut curve = CurveState::new("test-mint".into(), None, 0);
        curve.v_sol = 100_000_000_000;
        curve.v_tokens = 1_000_000_000_000;
        curve.r_sol = 90_000_000_000;
        curve.r_tokens = 500_000_000_000;
        curve.protocol_fee_bps = Some(100);
        curve.creator_fee_bps = Some(200);
        curve.fee_policy_known = true;
        curve.supported_sol_quote = true;
        curve.reserves_authoritative = true;
        curve
    }

    #[test]
    fn unsupported_quote_state_never_becomes_zero_mark_or_fill() {
        let mut curve = quoted_curve();
        curve.supported_sol_quote = false;
        assert!(curve.quote_state().is_none());

        let mut position = PaperPosition::new_pending_at_ms(
            StrategyKind::DevDumpAbsorption,
            curve.mint.clone(),
            1,
            90.0,
            0.5,
            10,
            70,
        );
        assert!(position.freeze_buy_guard(&curve).is_none());
        assert!(position.try_land_at_ms(&mut curve, 80).is_none());
        assert_eq!(position.tokens_held, 0);
        assert_eq!(position.executable_proceeds_sol(&curve), Some(0.0));
        position.tokens_held = 100; // Retained inventory needs a supported mark.
        assert!(position.executable_proceeds_sol(&curve).is_none());
    }

    #[test]
    fn delayed_buy_uses_frozen_guard_and_separate_fee_ceilings() {
        let mut curve = quoted_curve();
        let signal_state = curve.quote_state().unwrap();
        let mut position = PaperPosition::new_pending_at_ms(
            StrategyKind::DevDumpAbsorption,
            curve.mint.clone(),
            1,
            90.0,
            0.5,
            10,
            70,
        );
        let min_tokens = position.freeze_buy_guard(&curve).unwrap();
        let expected_tokens = position
            .pending_buy
            .as_ref()
            .unwrap()
            .expected_tokens_raw
            .unwrap();

        assert!(position.try_land_at_ms(&mut curve, 79).is_none());
        assert_eq!(position.try_land_at_ms(&mut curve, 80), Some(true));

        let fill = position.last_fill.as_ref().unwrap();
        assert_eq!(fill.side, "buy");
        assert_eq!(fill.status, "filled");
        assert_eq!(fill.expected_output_raw, Some(expected_tokens));
        assert_eq!(fill.min_output_raw, Some(min_tokens));
        assert_eq!(fill.state_before, Some(signal_state.into()));
        assert_eq!(
            sol_to_raw(position.entry_cost_sol),
            Some(fill.gross_cost_raw.unwrap() + STANDARD_NETWORK_FEE_LAMPORTS)
        );
        assert_eq!(position.network_fees_raw, STANDARD_NETWORK_FEE_LAMPORTS);
        assert!(fill.protocol_fee_raw > 0);
        assert!(fill.creator_fee_raw > fill.protocol_fee_raw);
        assert_eq!(curve.quote_state().unwrap().rtokens_raw, curve.r_tokens);
    }

    #[test]
    fn delayed_buy_guard_failure_charges_only_the_failed_attempt_fee() {
        let mut curve = quoted_curve();
        let mut position = PaperPosition::new_pending_at_ms(
            StrategyKind::DevDumpAbsorption,
            curve.mint.clone(),
            1,
            90.0,
            0.5,
            0,
            70,
        );
        position.freeze_buy_guard(&curve).unwrap();
        let frozen_expected = position
            .pending_buy
            .as_ref()
            .unwrap()
            .expected_tokens_raw
            .unwrap();

        // Move the virtual price sharply before the provisional landing time.
        curve.v_sol = 200_000_000_000;
        curve.r_sol = 100_000_000_000;
        assert_eq!(position.try_land_at_ms(&mut curve, 70), Some(false));

        let fill = position.last_fill.as_ref().unwrap();
        assert_eq!(fill.status, "guard_failed");
        assert_eq!(fill.expected_output_raw, Some(frozen_expected));
        assert!(fill.quoted_tokens_raw.unwrap() < frozen_expected);
        assert_eq!(fill.protocol_fee_raw, 0);
        assert_eq!(fill.creator_fee_raw, 0);
        assert_eq!(fill.network_fee_raw, FAILED_GUARD_FEE_LAMPORTS);
        assert_eq!(position.network_fees_raw, FAILED_GUARD_FEE_LAMPORTS);
        assert_eq!(position.entry_cost_sol, 0.000505);
        assert_eq!(curve.r_sol, 100_000_000_000);
    }

    #[test]
    fn partial_and_final_sells_land_after_delay_and_account_fees_once() {
        let mut curve = quoted_curve();
        let mut position = PaperPosition::new_pending_at_ms_with_delays(
            StrategyKind::DevDumpAbsorption,
            curve.mint.clone(),
            1,
            90.0,
            0.5,
            0,
            10,
            70,
        );
        position.state = PositionState::Open;
        position.entry_time_ms = 0;
        position.entry_cost_sol = 0.01;
        position.tokens_held = 100_000_000_000;
        position.original_tokens = 100_000_000_000;

        position.update_at_ms(&mut curve, 1);
        let partial = position.pending_exit.as_ref().unwrap();
        assert_eq!(partial.tokens_raw, 40_000_000_000);
        assert_eq!(partial.ready_at_ms, 71);
        let frozen_partial_output = partial.expected_output_raw;
        assert!(position.land_pending_exit_at_ms(&mut curve, 70).is_none());
        assert!(position.land_pending_exit_at_ms(&mut curve, 71).is_none());
        assert_eq!(position.tokens_held, 60_000_000_000);
        assert!(position.tranche1_proceeds > 0.0);
        assert_eq!(
            position.last_fill.as_ref().unwrap().status,
            "filled_partial"
        );
        assert_eq!(
            position.last_fill.as_ref().unwrap().expected_output_raw,
            frozen_partial_output
        );
        assert_eq!(position.network_fees_raw, STANDARD_NETWORK_FEE_LAMPORTS);

        assert!(position.queue_full_exit(&curve, 72, "test final exit".into()));
        let final_ready = position.pending_exit.as_ref().unwrap().ready_at_ms;
        assert!(position
            .land_pending_exit_at_ms(&mut curve, final_ready - 1)
            .is_none());
        let pnl = position
            .land_pending_exit_at_ms(&mut curve, final_ready)
            .unwrap();
        assert!(position.is_closed);
        assert_eq!(position.tokens_held, 0);
        assert_eq!(position.network_fees_raw, 2 * STANDARD_NETWORK_FEE_LAMPORTS);
        assert_eq!(
            position.last_fill.as_ref().unwrap().status,
            "filled_full_close"
        );
        assert_eq!(pnl, position.proceeds_sol - position.entry_cost_sol);
    }

    #[test]
    fn partial_and_full_exits_accept_a_dumped_landing_quote() {
        for full_exit in [false, true] {
            let mut curve = quoted_curve();
            let mut position = PaperPosition::new_pending_at_ms_with_delays(
                StrategyKind::DevDumpAbsorption,
                curve.mint.clone(),
                1,
                curve.real_sol_reserve(),
                0.5,
                0,
                10,
                70,
            );
            position.state = PositionState::Open;
            position.tokens_held = 100_000_000_000;
            position.original_tokens = position.tokens_held;
            position.entry_cost_sol = 0.5;
            if full_exit {
                assert!(position.queue_full_exit(&curve, 1, "dump test".into()));
            } else {
                assert!(position.queue_partial_exit(&curve, 1, 4_000, "dump test"));
            }
            let pending = position.pending_exit.clone().unwrap();
            assert_eq!(pending.min_output_raw, Some(0));
            // An intervening sell moves the curve well beyond the old 3.5%
            // guard. Reprice at landing instead of rejecting the exit.
            curve.v_sol /= 2;
            curve.v_tokens *= 2;
            curve.r_sol /= 2;
            let landing = curve
                .quote_state()
                .unwrap()
                .quote_sell(pending.tokens_raw)
                .unwrap();
            assert!(landing.net_sol_raw < min_output_guard(pending.expected_output_raw.unwrap()));
            assert!(position.land_pending_exit_at_ms(&mut curve, 70).is_none());
            assert!(position.land_pending_exit_at_ms(&mut curve, 71).is_some() == full_exit);
            let fill = position.last_fill.as_ref().unwrap();
            assert_eq!(fill.net_sol_raw, Some(landing.net_sol_raw));
            assert_eq!(
                fill.status,
                if full_exit {
                    "filled_full_close"
                } else {
                    "filled_partial"
                }
            );
            assert_eq!(
                position.tokens_held,
                if full_exit { 0 } else { 60_000_000_000 }
            );
            assert_eq!(position.network_fees_raw, STANDARD_NETWORK_FEE_LAMPORTS);
        }
    }

    #[test]
    fn curve_completion_retains_inventory_for_migration() {
        let mut curve = quoted_curve();
        let mut position = PaperPosition::new_pending_at_ms(
            StrategyKind::PreGraduationCarryover,
            curve.mint.clone(),
            1,
            90.0,
            0.5,
            0,
            70,
        );
        position.state = PositionState::Open;
        position.tokens_held = 123_456;
        position.original_tokens = 123_456;
        position.entry_cost_sol = 0.5;
        assert!(position.queue_full_exit(&curve, 1, "pending before completion".into()));
        curve.r_tokens = 0;

        assert!(position.land_pending_exit_at_ms(&mut curve, 71).is_none());
        assert!(matches!(position.state, PositionState::AwaitingMigration));
        assert_eq!(position.tokens_held, 123_456);
        assert!(!position.is_closed);
        assert_eq!(
            position.pending_exit.as_ref().unwrap().status,
            PendingOrderStatus::AwaitingMigration
        );
        assert!(position.last_fill.is_none(), "missing pool coverage must not emit a sell fill");
        assert!(position.executable_proceeds_sol(&curve).is_none());
    }

    #[test]
    fn s1_dev_absorption_canonical_parity() {
        let mut curve = CurveState::new("mint-s1".into(), Some("creator-1".into()), 0);
        curve.v_sol = 30_000_000_000;
        curve.v_tokens = 1_000_000_000_000;
        curve.r_sol = 4_000_000_000; // 4.0 SOL (in 1..=5 SOL range)
        curve.r_tokens = 800_000_000_000;
        curve.fee_policy_known = true;
        curve.supported_sol_quote = true;
        curve.reserves_authoritative = true;
        curve.protocol_fee_bps = Some(100);
        curve.creator_fee_bps = Some(200);

        // 1. Creator buys then sells >= 95%
        curve.apply_onchain_trade(&PumpTradeEvent {
            mint: "mint-s1".into(),
            user: "creator-1".into(),
            is_buy: true,
            sol_amount: 1.0,
            token_amount: 100_000_000,
            timestamp: 10,
            slot: 10,
            signature: "sig1".into(),
            is_create: false,
            creator: Some("creator-1".into()),
            onchain_rsol: Some(4_000_000_000),
            onchain_vsol: Some(50_000_000_000),
            onchain_vtokens: Some(1_000_000_000_000),
            onchain_rtokens: Some(800_000_000_000),
            protocol_fee_bps: Some(100),
            creator_fee_bps: Some(200),
            fee_policy_known: true,
            supported_sol_quote: true,
            signer_post_sol_lamports: Some(5_000_000_000),
        });

        // Set peak spot price: v_sol / v_tokens = 50 / 1000 = 0.05
        curve.peak_spot = 0.05;

        // Creator dumps 100%
        curve.apply_onchain_trade(&PumpTradeEvent {
            mint: "mint-s1".into(),
            user: "creator-1".into(),
            is_buy: false,
            sol_amount: 0.9,
            token_amount: 100_000_000,
            timestamp: 15,
            slot: 15,
            signature: "sig2".into(),
            is_create: false,
            creator: Some("creator-1".into()),
            onchain_rsol: Some(3_100_000_000),  // 3.1 SOL
            onchain_vsol: Some(32_500_000_000), // spot = 32.5 / 1000 = 0.0325 (35% dd from 0.05)
            onchain_vtokens: Some(1_000_000_000_000),
            onchain_rtokens: Some(800_000_000_000),
            protocol_fee_bps: Some(100),
            creator_fee_bps: Some(200),
            fee_policy_known: true,
            supported_sol_quote: true,
            signer_post_sol_lamports: Some(5_000_000_000),
        });

        // Post-dump trough is at slot 15 with spot 0.0325
        assert_eq!(curve.trough_slot, Some(15));

        // Outside buyer 1 buys 0.15 SOL at slot 16
        curve.apply_onchain_trade(&PumpTradeEvent {
            mint: "mint-s1".into(),
            user: "buyer-1".into(),
            is_buy: true,
            sol_amount: 0.15,
            token_amount: 4_000_000,
            timestamp: 16,
            slot: 16,
            signature: "sig3".into(),
            is_create: false,
            creator: Some("creator-1".into()),
            onchain_rsol: Some(3_250_000_000),
            onchain_vsol: Some(32_650_000_000),
            onchain_vtokens: Some(996_000_000_000),
            onchain_rtokens: Some(796_000_000_000),
            protocol_fee_bps: Some(100),
            creator_fee_bps: Some(200),
            fee_policy_known: true,
            supported_sol_quote: true,
            signer_post_sol_lamports: Some(5_000_000_000),
        });

        // Outside buyer 2 buys 0.20 SOL at slot 17 (total outside buys = 0.35 SOL >= 0.30 SOL)
        let trade4 = PumpTradeEvent {
            mint: "mint-s1".into(),
            user: "buyer-2".into(),
            is_buy: true,
            sol_amount: 0.20,
            token_amount: 5_000_000,
            timestamp: 17,
            slot: 17,
            signature: "sig4".into(),
            is_create: false,
            creator: Some("creator-1".into()),
            onchain_rsol: Some(3_450_000_000),
            onchain_vsol: Some(32_850_000_000),
            onchain_vtokens: Some(991_000_000_000),
            onchain_rtokens: Some(791_000_000_000),
            protocol_fee_bps: Some(100),
            creator_fee_bps: Some(200),
            fee_policy_known: true,
            supported_sol_quote: true,
            signer_post_sol_lamports: Some(5_000_000_000),
        };
        curve.apply_onchain_trade(&trade4);

        let before_fired = curve.signal_fired.clone();
        let audit = curve.audit_entry_candidates(&trade4);
        assert_eq!(audit[0].strategy, StrategyKind::DevDumpAbsorption);
        assert_eq!(
            curve.signal_fired, before_fired,
            "observer cannot consume a live trigger"
        );
        let mut blocked = curve.clone();
        blocked.is_botted_cabal = true;
        assert_eq!(
            blocked.audit_entry_candidates(&trade4)[0].strategy,
            StrategyKind::DevDumpAbsorption
        );
        assert!(
            blocked.evaluate_triggers(&trade4).is_none(),
            "audit cannot weaken admission gates"
        );

        let signal = curve.evaluate_triggers(&trade4);
        assert!(
            signal.is_some(),
            "S1 should fire on canonical trough absorption"
        );
        let sig = signal.unwrap();
        assert_eq!(sig.strategy, StrategyKind::DevDumpAbsorption);
        assert_eq!(sig.reserve_sol, 3.45);
        assert!(sig.signal_trough_spot.is_some());

        // Check S1 Exit: floor invalidation below trough
        let mut pos = PaperPosition::new_pending_at_ms_with_delays(
            StrategyKind::DevDumpAbsorption,
            curve.mint.clone(),
            17,
            3.45,
            0.5,
            17_000,
            10,
            10,
        );
        pos.state = PositionState::Open;
        pos.entry_cost_sol = 0.50;
        pos.tokens_held = 10_000_000_000;
        pos.original_tokens = pos.tokens_held;
        pos.signal_trough_spot = sig.signal_trough_spot;

        // Curve spot drops below trough spot (0.0325 -> 0.02)
        curve.v_sol = 20_000_000_000;
        curve.v_tokens = 1_000_000_000_000;
        curve.r_sol = 2_000_000_000;
        pos.update_at_ms(&mut curve, 18_000);
        assert!(
            pos.pending_exit.is_some(),
            "S1 should exit when spot drops below signal trough"
        );
    }

    #[test]
    fn s2_survival_shelf_canonical_parity() {
        let mut curve = CurveState::new("mint-s2".into(), Some("creator-2".into()), 0);
        curve.prev_r_sol = 10.5;
        curve.r_sol = 11_200_000_000; // 11.2 SOL (crosses 10.8 from below)
        curve.v_sol = 40_000_000_000;
        curve.v_tokens = 1_000_000_000_000;
        curve.r_tokens = 600_000_000_000;
        curve.created_at_ts = 10;
        curve.fee_policy_known = true;
        curve.supported_sol_quote = true;
        curve.reserves_authoritative = true;
        curve.protocol_fee_bps = Some(100);
        curve.creator_fee_bps = Some(200);

        // 25 qualified outside buyers
        for i in 0..25 {
            curve
                .qualified_outside_buyers
                .insert(format!("buyer-{}", i));
            curve
                .holder_balances
                .insert(format!("buyer-{}", i), 1_000_000);
        }
        // Last 2 outside transactions are buys
        curve.last_outside_buys.push_back(true);
        curve.last_outside_buys.push_back(true);

        // Spot: 40/1000 = 0.04. Trailing high was 0.035
        curve.trailing_30s_spot.push_back((45, 0.035));

        let trade = PumpTradeEvent {
            mint: "mint-s2".into(),
            user: "buyer-26".into(),
            is_buy: true,
            sol_amount: 0.10,
            token_amount: 1_000_000,
            timestamp: 50, // age = 40s >= 30s
            slot: 100,
            signature: "sig-s2".into(),
            is_create: false,
            creator: Some("creator-2".into()),
            onchain_rsol: Some(11_200_000_000),
            onchain_vsol: Some(40_000_000_000),
            onchain_vtokens: Some(1_000_000_000_000),
            onchain_rtokens: Some(600_000_000_000),
            protocol_fee_bps: Some(100),
            creator_fee_bps: Some(200),
            fee_policy_known: true,
            supported_sol_quote: true,
            signer_post_sol_lamports: Some(5_000_000_000),
        };

        let signal = curve.evaluate_triggers(&trade);
        assert!(
            signal.is_some(),
            "S2 should fire when crossing 10.8 SOL with qualified shelf"
        );
        assert_eq!(
            signal.unwrap().strategy,
            StrategyKind::SurvivalShelfBreakout
        );

        // Check S2 Exit: invalidation when reserve drops to <= 9.8 SOL
        let mut pos = PaperPosition::new_pending_at_ms_with_delays(
            StrategyKind::SurvivalShelfBreakout,
            curve.mint.clone(),
            100,
            11.2,
            0.5,
            50_000,
            10,
            10,
        );
        pos.state = PositionState::Open;
        pos.entry_cost_sol = 0.50;
        pos.tokens_held = 10_000_000_000;
        pos.original_tokens = pos.tokens_held;

        curve.r_sol = 9_700_000_000; // 9.7 SOL <= 9.8 SOL
        pos.update_at_ms(&mut curve, 51_000);
        assert!(pos.pending_exit.is_some());
        assert_eq!(
            pos.pending_exit.unwrap().reason,
            "Curve reserves <= 9.8 SOL invalidation"
        );
    }

    #[test]
    fn s4_upper_ath_canonical_parity() {
        let mut curve = CurveState::new("mint-s4".into(), Some("creator-4".into()), 0);
        curve.r_sol = 18_000_000_000; // 18.0 SOL (in 16..=22 range)
        curve.v_sol = 60_000_000_000;
        curve.v_tokens = 1_000_000_000_000;
        curve.r_tokens = 400_000_000_000;
        curve.peak_spot = 0.055;
        curve.fee_policy_known = true;
        curve.supported_sol_quote = true;
        curve.reserves_authoritative = true;
        curve.protocol_fee_bps = Some(100);
        curve.creator_fee_bps = Some(200);

        for i in 0..22 {
            curve
                .qualified_outside_buyers
                .insert(format!("buyer-{}", i));
        }

        // New ATH spot: 60/1000 = 0.06 > 0.055, outside buy = 1.2 SOL >= 1.0 SOL
        let trade = PumpTradeEvent {
            mint: "mint-s4".into(),
            user: "buyer-whale".into(),
            is_buy: true,
            sol_amount: 1.2,
            token_amount: 15_000_000,
            timestamp: 100,
            slot: 200,
            signature: "sig-s4".into(),
            is_create: false,
            creator: Some("creator-4".into()),
            onchain_rsol: Some(18_000_000_000),
            onchain_vsol: Some(60_000_000_000),
            onchain_vtokens: Some(1_000_000_000_000),
            onchain_rtokens: Some(400_000_000_000),
            protocol_fee_bps: Some(100),
            creator_fee_bps: Some(200),
            fee_policy_known: true,
            supported_sol_quote: true,
            signer_post_sol_lamports: Some(5_000_000_000),
        };

        let signal = curve.evaluate_triggers(&trade);
        assert!(
            signal.is_some(),
            "S4 should fire on canonical 16-22 ATH breakout"
        );
        assert_eq!(signal.unwrap().strategy, StrategyKind::UpperAthBreakout);

        // Check S4 Exit: rejection stop after >= 12 slots at net <= -14%
        let mut pos = PaperPosition::new_pending_at_ms_with_delays(
            StrategyKind::UpperAthBreakout,
            curve.mint.clone(),
            200,
            18.0,
            0.5,
            100_000,
            10,
            10,
        );
        pos.state = PositionState::Open;
        pos.entry_cost_sol = 0.50;
        pos.tokens_held = 10_000_000_000;
        pos.original_tokens = pos.tokens_held;
        pos.entry_slot = Some(200);

        // Curve drops at slot 212 (12 slots later) to produce -15% ROI (between -14% and -22%)
        curve.last_slot = 212;
        curve.v_sol = 44_000_000_000;
        curve.r_sol = 14_000_000_000;
        pos.update_at_ms(&mut curve, 101_000);
        assert!(pos.pending_exit.is_some());
        assert!(pos.pending_exit.unwrap().reason.contains("Rejection Stop"));
    }
}
