//! Yellowstone / Solami gRPC Canonical Starting 5 Detection & Ghost Paper Runner.
//!
//! Subscribes directly to real-time Solana Pump.fun bonding curve transactions
//! via Yellowstone gRPC (e.g. Solami, Triton, Helius).
//!
//! Completely removes legacy KOL copy-trading logic.
//! Evaluates the Canonical Starting 5 strategies with Developer Gate & Tailored Dynamic Exits:
//! 1. Strat 1: Post-Dev Dump Absorption (broad_recovery)
//! 2. Strat 2: 10.8 SOL Survival Shelf Breakout (fresh_expansion)
//! 3. Strat 3: Whale Dislocation Floor / Two-Buyer Bounce (quiet_absorption)
//! 4. Strat 4: Upper ATH Breakout (upper_ath_breakout)
//! 5. Strat 5: Pre-Graduation AMM Carryover (late_continuation)
//!
//! Enforces:
//! - Developer Gate: Rejects tokens where creator holds > 15% of bag.
//! - Freshness Filter (S2): Restricts age <= 240s and outside buyers <= 80 to prevent bagholder fatigue.
//! - Tailored Dynamic Exits for S1–S5 per MASTER_STRATEGY_REGISTRY.md.
//! - Structured JSONL logging to `data/ghost_trades.jsonl`.
//! - Rolling telemetry summary to `data/ghost_summary.json`.
//! - Calibrated Strategy-Dependent Circuit Breakers.
//! - 15.0 SOL Virtual Bankroll, 0.50 SOL ticket, Max 2 Concurrent Positions.

#[path = "../bot/mod.rs"]
mod bot;

use std::{
    collections::{HashMap, HashSet, VecDeque},
    env,
    sync::Arc,
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};

use anyhow::Result;
use chrono::Utc;
use futures::StreamExt;
use tokio::sync::{Mutex, Semaphore};
use yellowstone_grpc_client::GeyserGrpcClient;
use yellowstone_grpc_proto::prelude::{
    subscribe_update::UpdateOneof, CommitmentLevel, SubscribeRequest,
    SubscribeRequestFilterTransactions,
};
use yellowstone_grpc_proto::tonic::transport::ClientTlsConfig;

use bot::curve_detector::{
    ActivePositionSnapshot, CircuitBreaker,
    CircuitBreakerSnapshot, CurveManager, GhostSummary, GhostTradeRecord, PaperPosition,
    PumpTradeEvent, ShieldedCoinRecord, StrategyKind, StrategySignal, StrategySummaryStats, PUMP_PROGRAM_ID,
};

fn now_unix_secs() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs()
}

/// Only successful complete receipt events are eligible market observations.
fn observation_trades(obs: &bot::pump_receipt_decoder::ReceiptObservation, fee_payer: Option<&str>) -> Vec<PumpTradeEvent> {
    obs.events.iter().map(|ev| PumpTradeEvent {
        mint: ev.mint.clone(), user: ev.user.clone(), is_buy: ev.is_buy,
        is_create: false, sol_amount: ev.sol_raw as f64 / 1e9,
        token_amount: ev.tokens_raw, slot: obs.slot,
        timestamp: obs.received_at_ms / 1000, signature: obs.signature.clone(),
        onchain_rsol: Some(ev.rsol_raw), onchain_vsol: Some(ev.vsol_raw),
        onchain_vtokens: Some(ev.vtokens_raw), onchain_rtokens: Some(ev.rtokens_raw),
        creator: Some(ev.creator.clone()),
        protocol_fee_bps: u16::try_from(ev.fee_bps).ok(),
        creator_fee_bps: u16::try_from(ev.creator_fee_bps).ok(),
        fee_policy_known: ev.fee_policy_known, supported_sol_quote: ev.supported_sol_quote,
        signer_post_sol_lamports: if fee_payer == Some(ev.user.as_str()) { obs.signer_post_sol_lamports } else { None },
    }).collect()
}

fn now_unix_ms() -> u64 {
    SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_millis() as u64
}

fn append_json(path: &str, value: &serde_json::Value) -> std::io::Result<()> {
    use std::io::Write;
    if let Some(parent) = std::path::Path::new(path).parent() { std::fs::create_dir_all(parent)?; }
    let mut file = std::fs::OpenOptions::new().create(true).append(true).open(path)?;
    writeln!(file, "{}", value)
}

fn write_checkpoint_atomic(path: &str, value: &serde_json::Value) -> Result<()> {
    use std::io::Write;
    let target=std::path::Path::new(path);
    if let Some(parent)=target.parent() { std::fs::create_dir_all(parent)?; }
    let temp=target.with_extension(format!("{}.tmp",std::process::id()));
    let mut file=std::fs::File::create(&temp)?;
    file.write_all(&serde_json::to_vec(value)?)?;file.sync_all()?;
    std::fs::rename(temp,target)?;
    Ok(())
}

#[derive(Clone, serde::Serialize, serde::Deserialize)]
struct IntentContext {
    value: serde_json::Value,
}

fn load_whitelisted_wallets() -> HashMap<String, String> {
    let mut map = HashMap::new();

    // 1. Primary: load tracked_wallets.txt
    let tracked_path = env::var("TRACKED_WALLETS_FILE").unwrap_or_else(|_| "tracked_wallets.txt".to_string());
    if let Ok(content) = std::fs::read_to_string(&tracked_path) {
        for line in content.lines() {
            let line = line.trim();
            if line.is_empty() || line.starts_with('#') { continue; }
            let mut parts = line.split('#');
            let wallet_part = parts.next().unwrap_or("").trim();
            let label_part = parts.next().map(|s| s.trim()).unwrap_or("Tracked");
            if wallet_part.is_empty() { continue; }
            for w in wallet_part.split(',') {
                let w = w.trim();
                if w.len() >= 32 && w.len() <= 44 {
                    map.insert(w.to_string(), label_part.to_string());
                }
            }
        }
    }

    // 2. Optional: load kol_wallets.txt if enabled
    let enable_kol = env::var("WHITELIST_KOL_WALLETS")
        .map(|v| v == "true" || v == "1")
        .unwrap_or(false);
    let kol_path = env::var("KOL_WALLETS_FILE").unwrap_or_else(|_| "kol_wallets.txt".to_string());
    if enable_kol && std::path::Path::new(&kol_path).exists() {
        if let Ok(content) = std::fs::read_to_string(&kol_path) {
            let mut kol_count = 0;
            for line in content.lines() {
                let line = line.trim();
                if line.is_empty() || line.starts_with('#') { continue; }
                let mut parts = line.split('#');
                let wallet_part = parts.next().unwrap_or("").trim();
                let label_part = parts.next().map(|s| s.trim()).unwrap_or("KOL");
                if wallet_part.is_empty() { continue; }
                for w in wallet_part.split(',') {
                    let w = w.trim();
                    if w.len() >= 32 && w.len() <= 44 {
                        map.entry(w.to_string()).or_insert_with(|| format!("KOL: {}", label_part));
                        kol_count += 1;
                    }
                }
            }
            eprintln!("[info] Loaded {} KOL wallets from {}", kol_count, kol_path);
        }
    }

    // 3. Optional: extra wallets from TRACKED_WALLETS env var
    if let Ok(env_str) = env::var("TRACKED_WALLETS") {
        for w in env_str.split(',') {
            let w = w.trim();
            if w.len() >= 32 && w.len() <= 44 {
                map.entry(w.to_string()).or_insert_with(|| "Env Tracked".to_string());
            }
        }
    }

    eprintln!("[info] Active whitelisted smart money wallets: {}", map.len());
    for (wallet, label) in &map {
        eprintln!("       - {} ({})", wallet, label);
    }
    map
}

struct AppState {
    curve_mgr: CurveManager,
    paper_positions: Vec<PaperPosition>,
    closed_positions: Vec<PaperPosition>,
    circuit_breakers: HashMap<StrategyKind, CircuitBreaker>,
    virtual_cash: f64,
    bankroll_initial: f64,
    max_positions: usize,
    vm_id: String,
    trades_log_path: String,
    summary_path: String,
    start_time: Instant,
    observations_path: String,
    intents_path: String,
    sources: HashMap<String, serde_json::Value>,
    position_ids: HashMap<String, String>,
    intents: HashMap<String, IntentContext>,
    next_intent: u64,
    delay_ms: u64,
    stream_connected: bool,
    last_stream_ms: u64,
    seen_signatures: HashSet<String>,
    signature_order: VecDeque<String>,
    undecoded_receipts: u64,
    failed_buy_costs: HashMap<StrategyKind, f64>,
    failed_buy_attempts: u64,
    reconcile_enabled: bool,
    holder_screen_times: HashMap<String, u64>,
    holder_screen_retry_after: HashMap<String, u64>,
    shielded_coins: Vec<ShieldedCoinRecord>,
    shielded_coins_log_path: String,
    min_scan_mcap_usd: f64,
    sol_usd_price: f64,
    whitelisted_wallets: HashMap<String, String>,
}

impl AppState {
    fn checkpoint_value(&self) -> serde_json::Value {
        serde_json::json!({"version":1,"saved_at_ms":now_unix_ms(),"vm_id":self.vm_id,
            "virtual_cash":self.virtual_cash,"bankroll_initial":self.bankroll_initial,
            "paper_positions":self.paper_positions,"closed_positions":self.closed_positions,
            "curves":self.curve_mgr.curves,"circuit_breakers":self.circuit_breakers,
            "sources":self.sources,"position_ids":self.position_ids,"intents":self.intents,
            "next_intent":self.next_intent,"failed_buy_costs":self.failed_buy_costs,
            "failed_buy_attempts":self.failed_buy_attempts,"shielded_coins":self.shielded_coins})
    }

    fn restore_checkpoint(&mut self, value: &serde_json::Value) -> Result<()> {
        anyhow::ensure!(value["version"].as_u64()==Some(1), "unsupported runtime checkpoint version");
        // Deserialize fully before mutating any funded ledger state.
        let positions: Vec<PaperPosition>=serde_json::from_value(value["paper_positions"].clone())?;
        let closed: Vec<PaperPosition>=serde_json::from_value(value["closed_positions"].clone())?;
        let mut curves: HashMap<String,bot::curve_detector::CurveState>=serde_json::from_value(value["curves"].clone())?;
        let breakers=serde_json::from_value(value["circuit_breakers"].clone())?;
        let sources=serde_json::from_value(value["sources"].clone())?;
        let ids=serde_json::from_value(value["position_ids"].clone())?;
        let intents=serde_json::from_value(value["intents"].clone())?;
        let failed=serde_json::from_value(value["failed_buy_costs"].clone())?;
        let shielded=serde_json::from_value(value["shielded_coins"].clone())?;
        let cash=value["virtual_cash"].as_f64().filter(|v|v.is_finite()).ok_or_else(||anyhow::anyhow!("invalid checkpoint cash"))?;
        let bankroll=value["bankroll_initial"].as_f64().filter(|v|v.is_finite()&&*v>0.0).ok_or_else(||anyhow::anyhow!("invalid checkpoint bankroll"))?;
        let vm=value["vm_id"].as_str().ok_or_else(||anyhow::anyhow!("checkpoint VM missing"))?.to_owned();
        let next=value["next_intent"].as_u64().ok_or_else(||anyhow::anyhow!("checkpoint sequence missing"))?;
        let failed_count=value["failed_buy_attempts"].as_u64().ok_or_else(||anyhow::anyhow!("checkpoint failed count missing"))?;
        for pos in &positions { anyhow::ensure!(curves.contains_key(&pos.mint), "checkpoint lacks held coin state"); }
        for curve in curves.values_mut() {
            curve.reserves_authoritative=false;curve.reserves_from_paper_fill=false;
            curve.audit_in_flight=false;curve.fresh_wallets_audited=false;
        }
        self.paper_positions=positions; self.closed_positions=closed;self.curve_mgr.curves=curves;
        self.circuit_breakers=breakers;self.sources=sources;self.position_ids=ids;self.intents=intents;
        self.failed_buy_costs=failed;self.shielded_coins=shielded;self.virtual_cash=cash;
        self.bankroll_initial=bankroll;self.vm_id=vm;self.next_intent=next;self.failed_buy_attempts=failed_count;
        self.holder_screen_times.clear();self.holder_screen_retry_after.clear();
        self.stream_connected=false;self.last_stream_ms=0;
        for pos in &mut self.paper_positions { pos.migration_amm=None; }
        Ok(())
    }

    fn record_shielded_coin(&mut self, mint: &str, reason: &str, layer: &str, now_ts: u64) {
        if self.curve_mgr.curves.get(mint).is_some_and(|c| c.is_whitelisted) {
            return;
        }
        if self.shielded_coins.iter().any(|c| c.mint == mint) {
            return;
        }
        let (reserve_sol, mcap_usd) = self.curve_mgr.curves.get(mint).map_or((0.0, 0.0), |c| {
            (c.real_sol_reserve(), c.market_cap_usd(self.sol_usd_price))
        });
        let record = ShieldedCoinRecord {
            mint: mint.to_string(),
            timestamp: now_ts,
            datetime_utc: Utc::now().to_rfc3339(),
            reserve_sol,
            market_cap_usd: mcap_usd,
            reason: reason.to_string(),
            layer: layer.to_string(),
        };
        self.shielded_coins.push(record.clone());
        let val = serde_json::to_value(&record).unwrap_or_default();
        if let Err(e) = append_json(&self.shielded_coins_log_path, &val) {
            eprintln!("[warn] Failed to log shielded coin: {}", e);
        }
    }

    fn holder_screen_ready(&self, mint: &str, now_ms: u64) -> bool {
        if self.curve_mgr.curves.get(mint).is_some_and(|c| c.is_whitelisted) {
            return true;
        }
        self.holder_screen_times.get(mint).is_some_and(|at|
            now_ms >= *at && now_ms - *at < 30_000)
            && self.curve_mgr.curves.get(mint).is_some_and(|curve|
                curve.fresh_wallets_audited && !curve.audit_in_flight && !curve.is_botted_cabal)
    }

    fn calculate_total_equity(&self) -> f64 {
        let open_mark: f64 = self
            .paper_positions
            .iter()
            .map(|pos| {
                if matches!(pos.state, bot::curve_detector::PositionState::PendingLanding { .. }) {
                    return pos.pending_buy.as_ref().map(|p| p.ticket_raw as f64 / 1e9 + bot::curve_detector::STANDARD_NETWORK_FEE_LAMPORTS as f64 / 1e9).unwrap_or(0.0); // Reserved, still unspent cash.
                }
                if let Some(curve) = self.curve_mgr.curves.get(&pos.mint) {
                    pos.executable_proceeds_sol(curve).unwrap_or(pos.entry_cost_sol)
                } else {
                    pos.entry_cost_sol
                }
            })
            .sum();
        self.virtual_cash + open_mark
    }

    fn open_pending_position(&mut self, signal: &StrategySignal, now_ms: u64) {
        if self.paper_positions.len() >= self.max_positions {
            return;
        }
        // Enforce canonical contract: Same-mint open positions block another entry
        if self.paper_positions.iter().any(|p| p.mint == signal.mint) {
            return;
        }
        // Mint Protection: Never re-enter a mint that has already been traded or closed
        if self.closed_positions.iter().any(|p| p.mint == signal.mint) {
            return;
        }
        // An unfinished/unknown holder screen cannot authorize an entry.
        if !self.holder_screen_ready(&signal.mint, now_ms) {
            return;
        }
        let ticket_sol = 0.50;
        let total_cost = ticket_sol + (bot::curve_detector::STANDARD_NETWORK_FEE_LAMPORTS as f64 / 1e9);
        if self.virtual_cash < total_cost {
            return;
        }
        self.virtual_cash -= total_cost;
        let mut pos = PaperPosition::new_pending_at_ms_with_delays(
            signal.strategy,
            signal.mint.clone(),
            signal.slot,
            signal.reserve_sol,
            ticket_sol,
            now_ms,
            self.delay_ms,
            self.delay_ms,
        );
        pos.signal_trough_spot = signal.signal_trough_spot;
        pos.entry_slot = Some(signal.slot);
        if let Some(curve) = self.curve_mgr.curves.get(&signal.mint) {
            pos.is_whitelisted = curve.is_whitelisted;
            pos.whitelisted_by = curve.whitelisted_by.clone();
        }
        let minimum = self.curve_mgr.curves.get(&signal.mint).and_then(|curve| pos.freeze_buy_guard(curve));
        let Some(minimum) = minimum else {
            self.virtual_cash += total_cost;
            return;
        };
        let position_id = format!("{}-{}-{}", self.vm_id, now_ms, self.next_intent);
        self.position_ids.insert(signal.mint.clone(), position_id);
        let mut context = self.new_intent(&signal.mint, "buy", now_ms);
        context.value["holder_screen_policy"] = "top_holder_balance_policy_v2".into();
        context.value["holder_screen_completed_at_ms"] = self.holder_screen_times
            .get(&signal.mint).copied().map(serde_json::Value::from)
            .unwrap_or(serde_json::Value::Null);
        context.value["gross_budget_raw"] = 500_000_000u64.into();
        context.value["min_output_raw"] = minimum.into();
        self.persist_intent(&context);
        self.intents.insert(signal.mint.clone(), context);
        let is_whitelisted = pos.is_whitelisted;
        let whitelisted_by = pos.whitelisted_by.clone();
        self.paper_positions.push(pos);

        println!(
            "\n>>> [QUEUEING BUY] Strategy: {} [{}] | Mint: {}",
            signal.strategy.as_str(),
            signal.strategy.code(),
            signal.mint
        );
        if is_whitelisted {
            println!("    🌟 WHITELIST STATUS: Bypassed all shields via {}", whitelisted_by.as_deref().unwrap_or("Tracked Wallet"));
        }
        println!(
            "    Signal Reserve: {:.2} SOL | Dev Bag: {:.1}% | Breadth: {} buyers | Slot: {}",
            signal.reserve_sol, signal.developer_held_pct, signal.buyer_breadth, signal.slot
        );
        println!("    Trigger Context: {}\n", signal.details);
    }

    fn try_land_pending_buys(&mut self, trade_mint: &str, now_ms: u64) {
        let now_ts = now_ms / 1000;
        let mut newly_landed = Vec::new();
        let mut newly_rejected = Vec::new();

        // Unsubmitted paper intents are cancelled if screening blacklists the
        // mint or expires before landing; never defer an old entry signal until
        // a later audit clears. This is not a claimed on-chain cancellation.
        let is_whitelisted = self.curve_mgr.curves.get(trade_mint).is_some_and(|c| c.is_whitelisted);
        let blacklisted = !is_whitelisted && self.curve_mgr.curves.get(trade_mint).is_some_and(|c| c.is_botted_cabal);
        if !self.holder_screen_ready(trade_mint, now_ms) {
            let cancelled: Vec<usize> = self.paper_positions.iter().enumerate()
                .filter(|(_, p)| p.mint == trade_mint && matches!(p.state,
                    bot::curve_detector::PositionState::PendingLanding { .. }))
                .map(|(index, _)| index).collect();
            for index in cancelled.into_iter().rev() {
                let position = self.paper_positions.remove(index);
                let refund = position.pending_buy.as_ref().map(|buy|
                    buy.ticket_raw as f64 / 1e9
                        + bot::curve_detector::STANDARD_NETWORK_FEE_LAMPORTS as f64 / 1e9)
                    .unwrap_or(0.0);
                self.virtual_cash += refund;
                if let Some(context) = self.intents.remove(trade_mint) {
                    let mut row = context.value;
                    row["event"] = "CANCEL".into();
                    row["status"] = if blacklisted { "paper_cancelled_holder_blacklist" }
                        else { "paper_cancelled_holder_screen_unavailable" }.into();
                    row["cancelled_at_ms"] = now_ms.into();
                    row["network_fee_raw"] = 0u64.into();
                    row["actual_fill_established"] = false.into();
                    if let Err(error) = append_json(&self.intents_path, &row) {
                        eprintln!("[error] Paper cancellation audit failed: {}", error);
                    }
                }
                self.position_ids.remove(trade_mint);
            }
            return;
        }
        if let Some(curve) = self.curve_mgr.curves.get_mut(trade_mint) {
            for pos in self.paper_positions.iter_mut() {
                if pos.mint == trade_mint && matches!(pos.state, bot::curve_detector::PositionState::PendingLanding { .. }) {
                    let reserved = pos.pending_buy.as_ref().map(|p| p.ticket_raw as f64 / 1e9 + bot::curve_detector::STANDARD_NETWORK_FEE_LAMPORTS as f64 / 1e9).unwrap_or(0.0);
                    if let Some(landed) = pos.try_land_at_ms(curve, now_ms) {
                        self.virtual_cash += reserved - pos.entry_cost_sol;
                        if landed {
                            newly_landed.push(pos.clone());
                        } else {
                            newly_rejected.push(pos.clone());
                        }
                    }
                }
            }
        }

        for landed_pos in newly_landed {
            if let Some(audit) = &landed_pos.last_fill {
                self.persist_fill(&landed_pos.mint, &serde_json::to_value(audit).unwrap_or_default());
            }
            let total_equity = self.calculate_total_equity();
            let rec = GhostTradeRecord {
                event: "OPEN".to_string(),
                vm_id: self.vm_id.clone(),
                timestamp: now_ts,
                datetime_utc: Utc::now().to_rfc3339(),
                strategy: landed_pos.strategy.as_str().to_string(),
                strategy_code: landed_pos.strategy.code().to_string(),
                mint: landed_pos.mint.clone(),
                signal_reserve_sol: Some(landed_pos.signal_reserve_sol),
                entry_reserve_sol: landed_pos.entry_reserve_sol,
                buy_slippage_pct: Some(landed_pos.buy_slippage_pct),
                buy_impact_pct: Some(landed_pos.buy_impact_pct),
                tokens_held: landed_pos.tokens_held,
                exit_trigger_reserve_sol: None,
                exit_reserve_sol: None,
                exit_slippage_pct: None,
                sell_impact_pct: None,
                post_exit_reserve_sol: None,
                post_exit_change_pct: None,
                post_exit_note: None,
                entry_cost_sol: landed_pos.entry_cost_sol,
                proceeds_sol: 0.0,
                net_pnl_sol: 0.0,
                pnl_pct: 0.0,
                peak_roi_pct: 0.0,
                duration_secs: 0,
                exit_reason: None,
                virtual_cash_after: self.virtual_cash,
                total_equity_after: total_equity,
                is_whitelisted: landed_pos.is_whitelisted,
                whitelisted_by: landed_pos.whitelisted_by.clone(),
            };
            self.log_trade(&rec);

            println!(
                "\n>>> [BUY LANDED & FILLED] Strategy: {} [{}] | Mint: {}",
                landed_pos.strategy.as_str(),
                landed_pos.strategy.code(),
                landed_pos.mint
            );
            println!(
                "    Landed Reserve: {:.4} SOL (Signal: {:.4} SOL | Slip: {:>+4.2}% | Impact: {:>+4.2}%)",
                landed_pos.entry_reserve_sol, landed_pos.signal_reserve_sol, landed_pos.buy_slippage_pct, landed_pos.buy_impact_pct
            );
            println!(
                "    Tokens Received: {} tokens | Cost: {:.6} SOL (incl. fee)\n",
                landed_pos.tokens_held, landed_pos.entry_cost_sol
            );
        }

        for rej_pos in newly_rejected {
            if rej_pos.entry_cost_sol > 0.0 {
                self.failed_buy_attempts += 1;
                *self.failed_buy_costs.entry(rej_pos.strategy).or_default() += rej_pos.entry_cost_sol;
                if let Some(cb) = self.circuit_breakers.get_mut(&rej_pos.strategy) {
                    cb.record_trade(-rej_pos.entry_cost_sol, now_ts);
                }
            }
            if let Some(audit) = &rej_pos.last_fill {
                self.persist_fill(&rej_pos.mint, &serde_json::to_value(audit).unwrap_or_default());
            }
            let total_equity = self.calculate_total_equity();
            let rec = GhostTradeRecord {
                event: "GUARD_FAIL".to_string(),
                vm_id: self.vm_id.clone(),
                timestamp: now_ts,
                datetime_utc: Utc::now().to_rfc3339(),
                strategy: rej_pos.strategy.as_str().to_string(),
                strategy_code: rej_pos.strategy.code().to_string(),
                mint: rej_pos.mint.clone(),
                signal_reserve_sol: Some(rej_pos.signal_reserve_sol),
                entry_reserve_sol: rej_pos.entry_reserve_sol,
                buy_slippage_pct: Some(rej_pos.buy_slippage_pct),
                buy_impact_pct: Some(0.0),
                tokens_held: 0,
                exit_trigger_reserve_sol: None,
                exit_reserve_sol: None,
                exit_slippage_pct: None,
                sell_impact_pct: None,
                post_exit_reserve_sol: None,
                post_exit_change_pct: None,
                post_exit_note: None,
                entry_cost_sol: rej_pos.entry_cost_sol,
                proceeds_sol: 0.0,
                net_pnl_sol: -rej_pos.entry_cost_sol,
                pnl_pct: -100.0,
                peak_roi_pct: 0.0,
                duration_secs: 0,
                exit_reason: rej_pos.exit_reason.clone(),
                virtual_cash_after: self.virtual_cash,
                total_equity_after: total_equity,
                is_whitelisted: rej_pos.is_whitelisted,
                whitelisted_by: rej_pos.whitelisted_by.clone(),
            };
            self.log_trade(&rec);
            println!(
                "\n*** [SLIPPAGE GUARD REJECTED] Mint: {} | Buy min-output tolerance: {:.1}% | Paper failed fee: 0.000505 SOL\n",
                rej_pos.mint, bot::curve_detector::configured_buy_slippage_bps() as f64 / 100.0
            );
        }

        self.paper_positions.retain(|p| !p.is_closed);
    }

    fn update_positions(&mut self, trade_mint: &str, now_ms: u64) {
        let now_ts = now_ms / 1000;
        let mut newly_closed = Vec::new();
        let mut queued = Vec::new();
        let mut filled = Vec::new();
        if let Some(curve) = self.curve_mgr.curves.get_mut(trade_mint) {
            for pos in self.paper_positions.iter_mut().filter(|p| p.mint == trade_mint) {
                let before = pos.tranche1_proceeds;
                let before_trigger = pos.pending_exit.as_ref().map(|p| p.triggered_at_ms);
                pos.update_at_ms(curve, now_ms);
                if let Some(pending) = &pos.pending_exit {
                    if Some(pending.triggered_at_ms) != before_trigger {
                        queued.push(serde_json::to_value(pending).unwrap_or_default());
                    }
                }
                if let Some(net_pnl) = pos.land_pending_exit_at_ms(curve, now_ms) {
                    newly_closed.push((net_pnl, pos.clone()));
                }
                self.virtual_cash += pos.tranche1_proceeds - before;
                if let Some(audit) = &pos.last_fill {
                    if audit.filled_at_ms == now_ms && audit.side == "sell" {
                        filled.push(serde_json::to_value(audit).unwrap_or_default());
                    }
                }
            }
        }
        for pending in queued {
            let mut context = self.new_intent(trade_mint, "sell", now_ms);
            context.value["quantity_tokens_raw"] = pending["tokens_raw"].clone();
            context.value["min_output_raw"] = pending["min_output_raw"].clone();
            context.value["ready_at_ms"] = pending["ready_at_ms"].clone();
            context.value["pending"] = pending;
            self.persist_intent(&context);
            self.intents.insert(trade_mint.to_string(), context);
        }
        for audit in filled { self.persist_fill(trade_mint, &audit); }

        if !newly_closed.is_empty() {
            self.paper_positions.retain(|p| !p.is_closed);
            for (net_pnl, closed_pos) in newly_closed {
                self.virtual_cash += closed_pos.proceeds_sol - closed_pos.tranche1_proceeds;
                if let Some(cb) = self.circuit_breakers.get_mut(&closed_pos.strategy) {
                    cb.record_trade(net_pnl, now_ts);
                }

                let total_equity = self.calculate_total_equity();
                let duration_secs = closed_pos
                    .exit_time
                    .unwrap_or(now_ts)
                    .saturating_sub(closed_pos.entry_time);
                let pnl_pct = (net_pnl / closed_pos.entry_cost_sol) * 100.0;

                let rec = GhostTradeRecord {
                    event: "CLOSE".to_string(),
                    vm_id: self.vm_id.clone(),
                    timestamp: now_ts,
                    datetime_utc: Utc::now().to_rfc3339(),
                    strategy: closed_pos.strategy.as_str().to_string(),
                    strategy_code: closed_pos.strategy.code().to_string(),
                    mint: closed_pos.mint.clone(),
                    signal_reserve_sol: Some(closed_pos.signal_reserve_sol),
                    entry_reserve_sol: closed_pos.entry_reserve_sol,
                    buy_slippage_pct: Some(closed_pos.buy_slippage_pct),
                    buy_impact_pct: Some(closed_pos.buy_impact_pct),
                    tokens_held: 0,
                    exit_trigger_reserve_sol: closed_pos.exit_trigger_reserve_sol,
                    exit_reserve_sol: closed_pos.exit_reserve_sol,
                    exit_slippage_pct: closed_pos.exit_slippage_pct,
                    sell_impact_pct: closed_pos.sell_impact_pct,
                    post_exit_reserve_sol: None,
                    post_exit_change_pct: None,
                    post_exit_note: None,
                    entry_cost_sol: closed_pos.entry_cost_sol,
                    proceeds_sol: closed_pos.proceeds_sol,
                    net_pnl_sol: net_pnl,
                    pnl_pct,
                    peak_roi_pct: closed_pos.peak_executable_roi * 100.0,
                    duration_secs,
                    exit_reason: closed_pos.exit_reason.clone(),
                    virtual_cash_after: self.virtual_cash,
                    total_equity_after: total_equity,
                    is_whitelisted: closed_pos.is_whitelisted,
                    whitelisted_by: closed_pos.whitelisted_by.clone(),
                };

                self.log_trade(&rec);

                println!(
                    "\n<<< [SELL EXECUTED & FILLED] Strategy: {} [{}] | Mint: {}",
                    closed_pos.strategy.as_str(),
                    closed_pos.strategy.code(),
                    closed_pos.mint
                );
                println!(
                    "    Reason: {} | Net PnL: {:>+8.4} SOL ({:>+6.1}%) | Proceeds: {:.4} SOL | Peak Exec ROI: {:>+6.1}% | Duration: {}s",
                    closed_pos.exit_reason.as_deref().unwrap_or("Unknown"),
                    net_pnl,
                    pnl_pct,
                    closed_pos.proceeds_sol,
                    closed_pos.peak_executable_roi * 100.0,
                    duration_secs
                );
                println!(
                    "    Exit Trigger: {:.4} SOL -> Landed Exit: {:.4} SOL (Sell Impact: {:>+4.2}%)\n",
                    closed_pos.exit_trigger_reserve_sol.unwrap_or(0.0),
                    closed_pos.exit_reserve_sol.unwrap_or(0.0),
                    closed_pos.sell_impact_pct.unwrap_or(0.0)
                );

                self.closed_positions.push(closed_pos);
            }
        }
    }

    fn update_post_exit_tracking(&mut self, trade_mint: &str, current_reserve: f64, now_ts: u64) {
        for closed_pos in self.closed_positions.iter_mut() {
            if closed_pos.mint == trade_mint {
                let exit_t = closed_pos.exit_time.unwrap_or(0);
                if now_ts >= exit_t && now_ts.saturating_sub(exit_t) <= 60 {
                    let exit_r = closed_pos.exit_reserve_sol.unwrap_or(closed_pos.entry_reserve_sol);
                    closed_pos.post_exit_reserve_sol = Some(current_reserve);
                    let diff_pct = if exit_r > 0.0 { (current_reserve / exit_r - 1.0) * 100.0 } else { 0.0 };
                    closed_pos.post_exit_change_pct = Some(diff_pct);
                    if diff_pct <= -10.0 {
                        closed_pos.post_exit_note = Some(format!("Dump escaped ({:+.1}%)", diff_pct));
                    } else if diff_pct >= 15.0 {
                        closed_pos.post_exit_note = Some(format!("Left on table ({:+.1}%)", diff_pct));
                    } else {
                        closed_pos.post_exit_note = Some(format!("Stabilized ({:+.1}%)", diff_pct));
                    }
                }
            }
        }
    }

    fn check_wall_clock_timeouts(&mut self, now_ms: u64) {
        // Receive-clock estimates stop when stream continuity is unavailable.
        if !self.stream_connected || now_ms.saturating_sub(self.last_stream_ms) > 2_000 {
            self.invalidate_market_coverage();
            // Authenticated RPC pool coverage is independent of the curve feed.
            let migrated: Vec<String>=self.paper_positions.iter()
                .filter(|p|p.state==bot::curve_detector::PositionState::AwaitingMigration)
                .map(|p|p.mint.clone()).collect();
            for mint in migrated {self.update_positions(&mint,now_ms);}
            return;
        }
        let mints: Vec<String> = self.paper_positions.iter().map(|p| p.mint.clone()).collect();
        for mint in mints {
            self.try_land_pending_buys(&mint, now_ms);
            self.update_positions(&mint, now_ms);
        }
    }

    fn invalidate_market_coverage(&mut self) {
        // A later update on another mint cannot restore a stale held coin.
        for curve in self.curve_mgr.curves.values_mut() {
            curve.reserves_authoritative = false;
            curve.reserves_from_paper_fill = false;
        }
    }

    fn new_intent(&mut self, mint: &str, side: &str, now_ms: u64) -> IntentContext {
        self.next_intent += 1;
        let mut value = self.sources.get(mint).cloned().unwrap_or_else(|| serde_json::json!({}));
        value["event"] = "INTENT".into();
        value["mint"] = mint.into(); value["side"] = side.into();
        value["position_id"] = self.position_ids.get(mint).cloned().unwrap_or_default().into();
        value["intent_id"] = format!("{}-intent-{}", self.vm_id, self.next_intent).into();
        value["received_at_ms"] = now_ms.into();
        value["ready_at_ms"] = now_ms.saturating_add(self.delay_ms).into();
        value["network_fee_raw"] = bot::curve_detector::STANDARD_NETWORK_FEE_LAMPORTS.into();
        value["execution_model"] = "provisional_receive_clock_quote_v2".into();
        value["placement_calibrated"] = false.into();
        value["our_signature"] = serde_json::Value::Null;
        IntentContext { value }
    }

    fn persist_intent(&self, context: &IntentContext) {
        if let Err(e) = append_json(&self.intents_path, &context.value) {
            eprintln!("[error] Intent audit failed: {}", e);
        }
    }

    fn persist_fill(&self, mint: &str, audit: &serde_json::Value) {
        if let Some(context) = self.intents.get(mint) {
            let mut value = context.value.clone();
            value["event"] = if audit["status"].as_str().is_some_and(|status| status.starts_with("filled")) { "FILL" } else { "FAIL" }.into();
            value["fill"] = audit.clone();
            if let Some(fields) = audit.as_object() {
                for (key, field) in fields { value[key] = field.clone(); }
            }
            value["actual_fill_established"] = false.into();
            if let Err(e) = append_json(&self.intents_path, &value) {
                eprintln!("[error] Fill audit failed: {}", e);
            }
        }
    }

    fn log_trade(&self, record: &GhostTradeRecord) {
        let mut value = serde_json::to_value(record).unwrap_or_default();
        if let Some(context) = self.intents.get(&record.mint) {
            if let Some(fields) = context.value.as_object() {
                for (key, field) in fields {
                    if key != "event" { value[key] = field.clone(); }
                }
            }
        }
        value["execution_model"] = "provisional_receive_clock_quote_v2".into();
        value["actual_fill_established"] = false.into();
        if let Err(e) = append_json(&self.trades_log_path, &value) {
            eprintln!("[error] Trade audit failed: {}", e);
        }
        if record.event == "CLOSE" { self.reconcile_after_exit(value); }
    }

    fn reconcile_after_exit(&self, value: serde_json::Value) {
        if !self.reconcile_enabled { return; }
        // A new immutable report revises the estimate; original fills stay intact.
        let id: String = value["intent_id"].as_str().unwrap_or("unknown").chars()
            .filter(|c| c.is_ascii_alphanumeric() || *c == '-').collect();
        let directory = format!("reports/ghost_post_exit/{}-{}", id, now_unix_ms());
        let input = format!("{}.jsonl", directory);
        let position = value["position_id"].as_str().unwrap_or("");
        let actions = std::fs::read_to_string(&self.intents_path).unwrap_or_default();
        let mut selected = Vec::new();
        for line in actions.lines() {
            if let Ok(row) = serde_json::from_str::<serde_json::Value>(line) {
                if row["position_id"].as_str() == Some(position) { selected.push(row); }
            }
        }
        selected.push(value);
        for row in &selected {
            if let Err(e) = append_json(&input, row) {
                eprintln!("[error] Reconciliation input failed: {}", e); return;
            }
        }
        let observations = self.observations_path.clone();
        tokio::task::spawn_blocking(move || {
            // RPC confirmation needs time; no hypothetical order has a signature.
            std::thread::sleep(Duration::from_secs(3));
            match std::process::Command::new("python3")
                .args(["scripts/reconcile_ghost_fills.py", "--intents", &input,
                       "--observations", &observations, "--output-dir", &directory,
                       "--commitment", "confirmed"])
                .output() {
                Ok(output) if output.status.success() => {
                    println!("[audit] Post-exit placement report: {}/report.json", directory);
                }
                Ok(_) => eprintln!("[warn] Post-exit audit failed; input retained: {}", input),
                Err(e) => eprintln!("[warn] Unable to start post-exit audit: {}", e),
            }
        });
    }

    fn generate_summary(&self, now_ts: u64) -> GhostSummary {
        let uptime_secs = self.start_time.elapsed().as_secs();
        let total_closed = self.closed_positions.len();
        let wins = self
            .closed_positions
            .iter()
            .filter(|p| p.proceeds_sol > p.entry_cost_sol)
            .count();
        let losses = total_closed.saturating_sub(wins);
        let win_rate_pct = if total_closed > 0 {
            (wins as f64 / total_closed as f64) * 100.0
        } else {
            0.0
        };
        let total_net_pnl_sol: f64 = self
            .closed_positions
            .iter()
            .map(|p| p.proceeds_sol - p.entry_cost_sol)
            .sum::<f64>() - self.failed_buy_costs.values().sum::<f64>();
        let gross_win: f64 = self
            .closed_positions
            .iter()
            .filter(|p| p.proceeds_sol > p.entry_cost_sol)
            .map(|p| p.proceeds_sol - p.entry_cost_sol)
            .sum();
        let gross_loss: f64 = self
            .closed_positions
            .iter()
            .filter(|p| p.proceeds_sol <= p.entry_cost_sol)
            .map(|p| p.entry_cost_sol - p.proceeds_sol)
            .sum();
        let profit_factor = if gross_loss > 0.0 {
            gross_win / gross_loss
        } else if gross_win > 0.0 {
            99.9
        } else {
            1.0
        };
        let total_equity_sol = self.calculate_total_equity();

        let mut strategy_breakdown = HashMap::new();
        for strat in StrategyKind::all() {
            let strat_closed: Vec<&PaperPosition> = self
                .closed_positions
                .iter()
                .filter(|p| p.strategy == strat)
                .collect();
            let c_len = strat_closed.len();
            let c_wins = strat_closed
                .iter()
                .filter(|p| p.proceeds_sol > p.entry_cost_sol)
                .count();
            let c_losses = c_len.saturating_sub(c_wins);
            let c_pnl: f64 = strat_closed
                .iter()
                .map(|p| p.proceeds_sol - p.entry_cost_sol)
                .sum::<f64>() - self.failed_buy_costs.get(&strat).copied().unwrap_or(0.0);
            strategy_breakdown.insert(
                strat.code().to_string(),
                StrategySummaryStats {
                    code: strat.code().to_string(),
                    trades: c_len,
                    wins: c_wins,
                    losses: c_losses,
                    win_rate_pct: if c_len > 0 {
                        (c_wins as f64 / c_len as f64) * 100.0
                    } else {
                        0.0
                    },
                    net_pnl_sol: c_pnl,
                    avg_pnl_sol: if c_len > 0 {
                        c_pnl / c_len as f64
                    } else {
                        0.0
                    },
                },
            );
        }

        let active_positions = self
            .paper_positions
            .iter()
            .map(|pos| {
                let (roi_pct, proceeds, status_str) = if let Some(curve) = self.curve_mgr.curves.get(&pos.mint) {
                    let proceeds = pos.executable_proceeds_sol(curve);
                    let r = proceeds.map(|quote| ((quote + pos.tranche1_proceeds - pos.entry_cost_sol) / pos.entry_cost_sol) * 100.0);
                    let st = match pos.state {
                        bot::curve_detector::PositionState::PendingLanding { .. } => "PENDING_LANDING".to_string(),
                        bot::curve_detector::PositionState::Open => "OPEN".to_string(),
                        bot::curve_detector::PositionState::AwaitingMigration => if proceeds.is_some() { "AMM_OPEN".to_string() } else { "AWAITING_MIGRATION".to_string() },
                        bot::curve_detector::PositionState::Closed => "CLOSED".to_string(),
                    };
                    (r, proceeds, st)
                } else {
                    (None, None, "AWAITING_COVERAGE".to_string())
                };

                ActivePositionSnapshot {
                    strategy: pos.strategy.as_str().to_string(),
                    strategy_code: pos.strategy.code().to_string(),
                    mint: pos.mint.clone(),
                    signal_reserve_sol: pos.signal_reserve_sol,
                    entry_reserve_sol: pos.entry_reserve_sol,
                    current_reserve_sol: pos.current_reserve_sol,
                    tokens_held: pos.tokens_held,
                    executable_proceeds_sol: proceeds,
                    roi_pct,
                    peak_roi_pct: pos.peak_executable_roi * 100.0,
                    elapsed_secs: now_ts.saturating_sub(pos.entry_time),
                    status: status_str,
                    is_whitelisted: pos.is_whitelisted,
                    whitelisted_by: pos.whitelisted_by.clone(),
                }
            })
            .collect();

        let mut circuit_breaker_statuses = HashMap::new();
        for (strat, cb) in self.circuit_breakers.iter() {
            circuit_breaker_statuses.insert(
                strat.code().to_string(),
                CircuitBreakerSnapshot {
                    strategy_code: strat.code().to_string(),
                    is_cooling: cb.is_cooling_down(now_ts),
                    cooldown_remaining_secs: cb.cooldown_until.saturating_sub(now_ts),
                    consecutive_losses: cb.consecutive_losses,
                    streak_limit: cb.streak_limit,
                    trip_count: cb.trip_count,
                },
            );
        }

        let recent_closed_trades = self
            .closed_positions
            .iter()
            .rev()
            .take(20)
            .map(|closed_pos| {
                let duration_secs = closed_pos
                    .exit_time
                    .unwrap_or(now_ts)
                    .saturating_sub(closed_pos.entry_time);
                let net_pnl = closed_pos.proceeds_sol - closed_pos.entry_cost_sol;
                let pnl_pct = (net_pnl / closed_pos.entry_cost_sol) * 100.0;
                GhostTradeRecord {
                    event: "CLOSE".to_string(),
                    vm_id: self.vm_id.clone(),
                    timestamp: closed_pos.exit_time.unwrap_or(now_ts),
                    datetime_utc: Utc::now().to_rfc3339(),
                    strategy: closed_pos.strategy.as_str().to_string(),
                    strategy_code: closed_pos.strategy.code().to_string(),
                    mint: closed_pos.mint.clone(),
                    signal_reserve_sol: Some(closed_pos.signal_reserve_sol),
                    entry_reserve_sol: closed_pos.entry_reserve_sol,
                    buy_slippage_pct: Some(closed_pos.buy_slippage_pct),
                    buy_impact_pct: Some(closed_pos.buy_impact_pct),
                    tokens_held: 0,
                    exit_trigger_reserve_sol: closed_pos.exit_trigger_reserve_sol,
                    exit_reserve_sol: closed_pos.exit_reserve_sol,
                    exit_slippage_pct: closed_pos.exit_slippage_pct,
                    sell_impact_pct: closed_pos.sell_impact_pct,
                    post_exit_reserve_sol: closed_pos.post_exit_reserve_sol,
                    post_exit_change_pct: closed_pos.post_exit_change_pct,
                    post_exit_note: closed_pos.post_exit_note.clone(),
                    entry_cost_sol: closed_pos.entry_cost_sol,
                    proceeds_sol: closed_pos.proceeds_sol,
                    net_pnl_sol: net_pnl,
                    pnl_pct,
                    peak_roi_pct: closed_pos.peak_executable_roi * 100.0,
                    duration_secs,
                    exit_reason: closed_pos.exit_reason.clone(),
                    virtual_cash_after: self.virtual_cash,
                    total_equity_after: total_equity_sol,
                    is_whitelisted: closed_pos.is_whitelisted,
                    whitelisted_by: closed_pos.whitelisted_by.clone(),
                }
            })
            .collect();

        GhostSummary {
            vm_id: self.vm_id.clone(),
            updated_at_utc: Utc::now().to_rfc3339(),
            uptime_secs,
            virtual_cash_sol: self.virtual_cash,
            total_equity_sol,
            active_positions_count: self.paper_positions.len(),
            total_closed_trades: total_closed,
            wins,
            losses,
            win_rate_pct,
            total_net_pnl_sol,
            profit_factor,
            strategy_breakdown,
            active_positions,
            recent_closed_trades,
            circuit_breaker_statuses,
            total_shielded_coins: self.shielded_coins.len(),
            recent_shielded_coins: self.shielded_coins.iter().rev().take(20).cloned().collect(),
        }
    }
}

#[tokio::main]
async fn main() -> Result<()> {
    dotenvy::dotenv().ok();
    dotenvy::from_filename("../.secrets/crypto.env.txt").ok();

    println!("==========================================================================================");
    println!("     SOLANA CANONICAL STARTING 5 REAL-TIME BONDING CURVE DETECTOR & GHOST ENGINE");
    println!("     Zero-Capital Forward Live Mode | Yellowstone / Solami gRPC Ingress");
    println!("==========================================================================================");

    // Resolve Ingress Endpoint & API Key / Token (Supports Solami, Triton, Shyft):
    let mut resolved_endpoint = env::var("TRITON_GRPC_URL")
        .or_else(|_| env::var("SOLAMI_GRPC_URL"))
        .or_else(|_| env::var("GRPC_ENDPOINT"))
        .or_else(|_| env::var("GRPC_URL"))
        .ok();
    let mut resolved_token = env::var("TRITON_API_KEY")
        .or_else(|_| env::var("SOLAMI_API_KEY"))
        .or_else(|_| env::var("GRPC_X_TOKEN"))
        .or_else(|_| env::var("X_TOKEN"))
        .ok();

    if resolved_endpoint.is_none() {
        if let Ok(sources_str) = env::var("GRPC_SOURCES") {
            for part in sources_str.split(',') {
                let segs: Vec<&str> = part.split('|').collect();
                if segs.len() >= 2 {
                    resolved_endpoint = Some(segs[1].trim().to_string());
                    if segs.len() >= 3 && resolved_token.is_none() {
                        resolved_token = Some(segs[2].trim().to_string());
                    }
                    break;
                } else if !part.trim().is_empty() {
                    resolved_endpoint = Some(part.trim().to_string());
                    break;
                }
            }
        }
    }

    let endpoint = resolved_endpoint.unwrap_or_else(|| "https://grpc.solami.dev".to_string());
    let token = resolved_token.unwrap_or_else(|| "sk_7hPGeJuMS_ASwhlvlxKBn_6N5hm8I4bKSP8xyaRFSXI".to_string());

    let bankroll_initial: f64 = env::var("PAPER_BANKROLL_SOL")
        .ok()
        .and_then(|v| v.parse().ok())
        .unwrap_or(15.0);

    let max_positions: usize = env::var("MAX_POSITIONS")
        .ok()
        .and_then(|v| v.parse().ok())
        .unwrap_or(10);

    let vm_id = env::var("VM_ID").unwrap_or_else(|_| "vm-local".to_string());
    let trades_log_path = env::var("GHOST_TRADES_PATH").unwrap_or_else(|_| "data/ghost_trades.jsonl".to_string());
    let summary_path = env::var("GHOST_SUMMARY_PATH").unwrap_or_else(|_| "data/ghost_summary.json".to_string());
    let shielded_coins_log_path = env::var("GHOST_SHIELDED_PATH").unwrap_or_else(|_| "data/ghost_shielded_coins.jsonl".to_string());
    let min_scan_mcap_usd: f64 = env::var("MIN_SCAN_MCAP_USD").ok().and_then(|v| v.parse().ok()).unwrap_or(8000.0);
    let sol_usd_price: f64 = env::var("SOL_USD_PRICE").ok().and_then(|v| v.parse().ok()).unwrap_or(145.0);

    println!("Configuration:");
    println!(" • Ingress: Yellowstone gRPC at {}", endpoint);
    println!(" • VM Identifier: {}", vm_id);
    println!(" • Filter: Pump.fun Program ({})", PUMP_PROGRAM_ID);
    println!(" • Mode: ZERO-CAPITAL GHOST / PAPER TRADING (0 SOL at risk)");
    println!(" • Virtual Bankroll: {:.2} SOL | Ticket: 0.50 SOL | Max Positions: {}", bankroll_initial, max_positions);
    println!(" • Scan Filter: MIN ${:.0} MCAP (sub-8k microcaps bypassed) | Assumed SOL: ${:.2}", min_scan_mcap_usd, sol_usd_price);
    println!(" • Logging: Trades -> {} | Summary -> {} | Shielded -> {}", trades_log_path, summary_path, shielded_coins_log_path);
    println!(" • Strategies: S1 (Dev Absorption), S2 (Survival Shelf), S3 (Dislocation Floor), S4 (Upper ATH), S5 (Carryover)");
    println!("------------------------------------------------------------------------------------------\n");

    let mut breakers = HashMap::new();
    for strat in StrategyKind::all() {
        breakers.insert(strat, CircuitBreaker::for_strategy(strat));
    }

    let state = Arc::new(Mutex::new(AppState {
        curve_mgr: CurveManager::new(),
        paper_positions: Vec::new(),
        closed_positions: Vec::new(),
        circuit_breakers: breakers,
        virtual_cash: bankroll_initial,
        bankroll_initial,
        max_positions,
        vm_id,
        trades_log_path,
        summary_path,
        start_time: Instant::now(),
        observations_path: env::var("GHOST_OBSERVATIONS_PATH").unwrap_or_else(|_| "data/ghost_observations.jsonl".into()),
        intents_path: env::var("GHOST_INTENTS_PATH").unwrap_or_else(|_| "data/ghost_intents.jsonl".into()),
        sources: HashMap::new(), position_ids: HashMap::new(), intents: HashMap::new(),
        next_intent: 0,
        delay_ms: env::var("GHOST_FILL_DELAY_MS").ok().and_then(|v| v.parse().ok()).unwrap_or(70).max(30),
        stream_connected: false, last_stream_ms: 0,
        seen_signatures: HashSet::new(), signature_order: VecDeque::new(), undecoded_receipts: 0,
        failed_buy_costs: HashMap::new(), failed_buy_attempts: 0,
        reconcile_enabled: env::var("GHOST_RECONCILE_POST_EXIT").map_or(true, |v| v != "false" && v != "0"),
        holder_screen_times: HashMap::new(),
        holder_screen_retry_after: HashMap::new(),
        shielded_coins: Vec::new(),
        shielded_coins_log_path,
        min_scan_mcap_usd,
        sol_usd_price,
        whitelisted_wallets: load_whitelisted_wallets(),
    }));

    let rpc_url = env::var("SOLANA_RPC_URL")
        .unwrap_or_else(|_| {
            let key = env::var("SOLAMI_API_KEY")
                .unwrap_or_else(|_| "sk_7hPGeJuMS_ASwhlvlxKBn_6N5hm8I4bKSP8xyaRFSXI".to_string());
            format!("https://rpc.solami.dev/sol?api_key={}", key)
        });
    let http_client = reqwest::Client::builder()
        .timeout(Duration::from_millis(2500))
        .build()
        .unwrap_or_default();
    // Read-only diagnostic mode; no gRPC connection or paper orders are started.
    if let Ok(mint) = env::var("GHOST_SCREEN_MINT") {
        let report = bot::holder_screen::screen_holders(&http_client, &rpc_url, &mint).await;
        let value = serde_json::json!({"mint":mint,"report":report});
        if let Ok(path) = env::var("GHOST_HOLDER_SCREEN_PATH") {
            append_json(&path, &value)?;
        }
        println!("{}", serde_json::to_string_pretty(&value)?);
        return Ok(());
    }
    let holder_screen_slots = Arc::new(Semaphore::new(1));
    let holder_screen_last_start = Arc::new(Mutex::new(Instant::now() - Duration::from_secs(1)));
    let holder_screen_fallback_rpc = env::var("HOLDER_SCREEN_FALLBACK_RPC_URL")
        .unwrap_or_else(|_| "https://rpc.shyft.to?api_key=owfc3zuSXH37YG0U".into());
    let holder_screen_path = env::var("GHOST_HOLDER_SCREEN_PATH")
        .unwrap_or_else(|_| "data/ghost_holder_screen.jsonl".into());

    // Authenticated read-only migration diagnostic; no subscriptions/orders.
    if let Ok(mint)=env::var("GHOST_MIGRATION_CHECK_MINT") {
        let snapshot=bot::migration_amm::fetch_snapshot(&http_client,&rpc_url,&mint,None).await
            .map_err(|error|anyhow::anyhow!(error))?;
        let tokens=env::var("GHOST_MIGRATION_CHECK_TOKENS").ok().and_then(|v|v.parse::<u64>().ok()).unwrap_or(1);
        let quote=snapshot.quote_sell(tokens).ok();
        println!("{}",serde_json::to_string_pretty(&serde_json::json!({"snapshot":snapshot,"quote":quote,
            "actual_fill_established":false,"orders_created":0}))?);
        return Ok(());
    }

    let checkpoint_path=env::var("GHOST_STATE_PATH").unwrap_or_else(|_|"data/ghost_runtime_state.json".into());
    if std::path::Path::new(&checkpoint_path).exists() {
        let saved: serde_json::Value=serde_json::from_slice(&std::fs::read(&checkpoint_path)?)?;
        let mut s=state.lock().await;
        s.restore_checkpoint(&saved)?;
        println!("[info] Resumed VM {} with {} retained positions and preserved cash",s.vm_id,s.paper_positions.len());
        if env::var("RESET_CIRCUIT_BREAKERS").map(|v| v == "1" || v == "true").unwrap_or(false) {
            for (strat, cb) in s.circuit_breakers.iter_mut() {
                cb.cooldown_until = 0;
                cb.consecutive_losses = 0;
                println!("[info] Reset circuit breaker cooldown for {}", strat.as_str());
            }
        }
    } else {
        let summary=state.lock().await.summary_path.clone();
        if let Ok(bytes)=std::fs::read(summary) {
            if let Ok(saved)=serde_json::from_slice::<serde_json::Value>(&bytes) {
                anyhow::ensure!(saved["active_positions"].as_array().is_none_or(|p|p.is_empty()),
                    "existing inventory has no runtime checkpoint; refuse a bankroll reset. Preserve/recover prior VM before restart");
            }
        }
    }
    {
        let value=state.lock().await.checkpoint_value();
        write_checkpoint_atomic(&checkpoint_path,&value)?;
        let st=state.clone();
        tokio::spawn(async move {
            loop {
                tokio::time::sleep(Duration::from_secs(1)).await;
                let value=st.lock().await.checkpoint_value();
                if let Err(error)=write_checkpoint_atomic(&checkpoint_path,&value) {eprintln!("[error] Runtime checkpoint write failed: {}",error);}
            }
        });
    }

    // Independent read-only pool observations. A paper sale needs a snapshot
    // completed after its immutable ready time; old telemetry marks cannot fill.
    {
        let st=state.clone(); let client=http_client.clone();
        let primary=rpc_url.clone(); let fallback=holder_screen_fallback_rpc.clone();
        let evidence_path=env::var("GHOST_AMM_EVIDENCE_PATH").unwrap_or_else(|_|"data/ghost_amm_evidence.jsonl".into());
        tokio::spawn(async move {
            loop {
                let candidates: Vec<(String,Option<String>)> = {
                    let s=st.lock().await;
                    s.paper_positions.iter().filter(|p| p.tokens_held>0 && (p.state==bot::curve_detector::PositionState::AwaitingMigration
                        || p.current_reserve_sol>=65.0)).map(|p|(p.mint.clone(),p.migration_amm.as_ref().map(|a|a.pool.clone()))).collect()
                };
                for (mint,pool) in candidates {
                    let mut result=bot::migration_amm::fetch_snapshot(&client,&primary,&mint,pool.as_deref()).await;
                    if result.is_err() && fallback!=primary { result=bot::migration_amm::fetch_snapshot(&client,&fallback,&mint,pool.as_deref()).await; }
                    if let Ok(snapshot)=result {
                        let mut s=st.lock().await;
                        let vm_id=s.vm_id.clone();
                        for pos in s.paper_positions.iter_mut().filter(|p|p.mint==mint) {
                            let discarded=pos.pending_exit.as_ref().is_some_and(|p|p.venue.is_none() && p.trigger_quote_state.is_none());
                            if let Err(error)=pos.attach_amm_snapshot(snapshot.clone()) { eprintln!("[warn] AMM inventory observation rejected: {}",error); continue; }
                            if let Err(error)=append_json(&evidence_path,&serde_json::json!({"event":"AUTHENTICATED_AMM_SNAPSHOT","vm_id":vm_id,
                                "mint":mint,"snapshot":snapshot,"discarded_legacy_unquoted_intent":discarded,
                                "our_signature":null,"actual_fill_established":false})) {eprintln!("[error] AMM evidence write failed: {}",error);pos.migration_amm=None;}
                        }
                        s.update_positions(&mint,now_unix_ms());
                    }
                }
                tokio::time::sleep(Duration::from_millis(200)).await;
            }
        });
    }

    // Periodic Telemetry Dashboard & Snapshot Writer (Every 10s)
    {
        let st = state.clone();
        tokio::spawn(async move {
            loop {
                tokio::time::sleep(Duration::from_secs(10)).await;
                let now_ts = now_unix_secs();
                let s = st.lock().await;
                let summary = s.generate_summary(now_ts);

                // Include provenance so diagnostic cashflow is not a profit claim.
                let mut summary_value = serde_json::to_value(&summary).unwrap_or_default();
                summary_value["execution_model"] = "provisional_receive_clock_curve_and_amm_quotes_v3".into();
                summary_value["buy_slippage_pct"] = (bot::curve_detector::configured_buy_slippage_bps() as f64 / 100.0).into();
                summary_value["buy_min_output_retained_bps"] = (10_000 - bot::curve_detector::configured_buy_slippage_bps()).into();
                summary_value["amm_execution"] = "authenticated_RPC_snapshot_paper_quotes_no_onchain_sales".into();
                summary_value["amm_fill_clock"] = "first_fresh_pool_snapshot_after_intent_ready_time_not_calibrated".into();
                summary_value["fill_delay_ms"] = s.delay_ms.into();
                summary_value["placement_calibrated"] = false.into();
                summary_value["performance_validated"] = false.into();
                summary_value["failed_buy_attempts"] = s.failed_buy_attempts.into();
                summary_value["failed_buy_cost_sol"] = s.failed_buy_costs.values().sum::<f64>().into();
                summary_value["undecoded_receipts"] = s.undecoded_receipts.into();
                summary_value["stream_connected"] = s.stream_connected.into();
                summary_value["holder_screen_policy"] = serde_json::json!({
                    "version":"top_holder_balance_policy_v2", "top_token_accounts":20,
                    "minimum_wallet_sample":5,"low_balance_lamports":1_000_000_000u64,
                    "low_balance_fraction_gte":0.5,"recent_wallet_rule_enabled":false,
                    "clear_ttl_ms":30_000,
                    "pending_or_unknown_entry":"skip"});
                summary_value["holder_screen_counts"] = serde_json::json!({
                    "blacklisted":s.curve_mgr.curves.values().filter(|c| c.is_botted_cabal).count(),
                    "in_flight":s.curve_mgr.curves.values().filter(|c| c.audit_in_flight).count(),
                    "clear_current":s.curve_mgr.curves.keys().filter(|mint|
                        s.holder_screen_ready(mint, now_ts.saturating_mul(1000))).count(),
                    "completed_unknown_or_expired":s.holder_screen_times.keys().filter(|mint|
                        s.curve_mgr.curves.get(*mint).is_some_and(|c|
                            !c.is_botted_cabal && !c.audit_in_flight)
                        && !s.holder_screen_ready(mint, now_ts.saturating_mul(1000))).count()});
                summary_value["mark_unresolved_count"] = s.paper_positions.iter().filter(|p| {
                    !matches!(p.state, bot::curve_detector::PositionState::PendingLanding { .. }) &&
                    s.curve_mgr.curves.get(&p.mint).and_then(|c| p.executable_proceeds_sol(c)).is_none()
                }).count().into();
                // Atomic replacement avoids exposing a partially written summary.
                let temp = format!("{}.tmp", s.summary_path);
                if let Err(e) = std::fs::write(&temp, summary_value.to_string())
                    .and_then(|_| std::fs::rename(&temp, &s.summary_path)) {
                    eprintln!("[warn] Failed to save ghost summary: {}", e);
                }

                // Console Dashboard
                println!("\n==========================================================================================");
                println!(
                    "GHOST RUNNER [{}] | Uptime: {}m {}s | Curves Tracked: {} | Equity: {:.4} SOL (Net: {:+.4} SOL)",
                    summary.vm_id,
                    summary.uptime_secs / 60,
                    summary.uptime_secs % 60,
                    s.curve_mgr.curves.len(),
                    summary.total_equity_sol,
                    summary.total_net_pnl_sol
                );
                println!(
                    "Ghost Trades: {} closed ({} W / {} L) | Win Rate: {:.1}% | Profit Factor: {:.2} | Active: {}/{}",
                    summary.total_closed_trades,
                    summary.wins,
                    summary.losses,
                    summary.win_rate_pct,
                    summary.profit_factor,
                    summary.active_positions_count,
                    s.max_positions
                );
                println!("------------------------------------------------------------------------------------------");
                println!("STRATEGY BREAKDOWN:");
                for strat in StrategyKind::all() {
                    let code = strat.code();
                    if let Some(stats) = summary.strategy_breakdown.get(code) {
                        println!(
                            " • {:<4} {:<28}: {:>3} trades | {:>2}W / {:>2}L ({:>5.1}%) | Net: {:>+7.4} SOL",
                            code, strat.as_str(), stats.trades, stats.wins, stats.losses, stats.win_rate_pct, stats.net_pnl_sol
                        );
                    }
                }
                if !summary.active_positions.is_empty() {
                    println!("------------------------------------------------------------------------------------------");
                    println!("ACTIVE GHOST POSITIONS:");
                    for pos in &summary.active_positions {
                        println!(
                            " • [{:<4}] Mint: {}.. | Reserve: {:.2} SOL | ROI: {:>+6.1}% (Peak: {:>+6.1}%) | Age: {}s",
                            pos.strategy_code,
                            &pos.mint[..8.min(pos.mint.len())],
                            pos.current_reserve_sol,
                            pos.roi_pct.unwrap_or(f64::NAN),
                            pos.peak_roi_pct,
                            pos.elapsed_secs
                        );
                    }
                }
                println!("------------------------------------------------------------------------------------------");
                println!("CIRCUIT BREAKER STATUSES:");
                for strat in StrategyKind::all() {
                    let code = strat.code();
                    if let Some(cb_stat) = summary.circuit_breaker_statuses.get(code) {
                        let status_str = if cb_stat.is_cooling {
                            format!("COOLDOWN ({}s remaining)", cb_stat.cooldown_remaining_secs)
                        } else {
                            format!("ACTIVE (Loss streak: {}/{})", cb_stat.consecutive_losses, cb_stat.streak_limit)
                        };
                        println!(" • {:<4} {:<28}: {} (Trips: {})", code, strat.as_str(), status_str, cb_stat.trip_count);
                    }
                }
                if summary.total_shielded_coins > 0 {
                    println!("------------------------------------------------------------------------------------------");
                    println!("SHIELDED / BLOCKED CABAL COINS (Total Blocked: {}):", summary.total_shielded_coins);
                    for coin in summary.recent_shielded_coins.iter().take(5) {
                        println!(
                            " • [{:<18}] Mint: {}.. | ${:.1}k MC ({:.2} SOL) | Reason: {}",
                            coin.layer,
                            &coin.mint[..8.min(coin.mint.len())],
                            coin.market_cap_usd / 1000.0,
                            coin.reserve_sol,
                            coin.reason
                        );
                    }
                }
                println!("==========================================================================================\n");
            }
        });
    }

    // Dedicated 500ms Wall-Clock Timeout Checker
    {
        let st = state.clone();
        tokio::spawn(async move {
            loop {
                tokio::time::sleep(Duration::from_millis(10)).await;
                let mut s = st.lock().await;
                s.check_wall_clock_timeouts(now_unix_ms());
            }
        });
    }

    let mut consecutive_failures = 0;
    loop {
        let mut builder = match GeyserGrpcClient::build_from_shared(endpoint.clone()) {
            Ok(b) => b,
            Err(e) => {
                eprintln!("[error] invalid gRPC endpoint: {}", e);
                tokio::time::sleep(Duration::from_secs(5)).await;
                continue;
            }
        };

        if !token.is_empty() {
            builder = match builder.x_token(Some(token.clone())) {
                Ok(b) => b,
                Err(e) => {
                    eprintln!("[error] invalid x-token: {}", e);
                    tokio::time::sleep(Duration::from_secs(5)).await;
                    continue;
                }
            };
        }

        if endpoint.starts_with("https://") {
            builder = match builder.tls_config(ClientTlsConfig::new().with_native_roots()) {
                Ok(b) => b,
                Err(e) => {
                    eprintln!("[error] TLS config error: {}", e);
                    tokio::time::sleep(Duration::from_secs(5)).await;
                    continue;
                }
            };
        }

        println!("[info] Connecting to Yellowstone gRPC stream at {}...", endpoint);
        let mut client = match builder.connect().await {
            Ok(c) => {
                println!("[info] Connected to Yellowstone gRPC successfully!");
                consecutive_failures = 0;
                c
            }
            Err(e) => {
                consecutive_failures += 1;
                let delay = (consecutive_failures * 2).min(30);
                eprintln!("[warn] gRPC connection failed: {}. Retrying in {}s...", e, delay);
                tokio::time::sleep(Duration::from_secs(delay)).await;
                continue;
            }
        };

        let mut tx_filter = HashMap::new();
        tx_filter.insert(
            "pump_trades".to_string(),
            SubscribeRequestFilterTransactions {
                vote: Some(false),
                failed: Some(false),
                account_include: vec![PUMP_PROGRAM_ID.to_string()],
                account_exclude: vec![],
                account_required: vec![],
                signature: None,
            },
        );

        let request = SubscribeRequest {
            transactions: tx_filter,
            commitment: Some(CommitmentLevel::Processed as i32),
            ..Default::default()
        };

        let (_sink, mut stream) = match client.subscribe_with_request(Some(request)).await {
            Ok(pair) => pair,
            Err(e) => {
                eprintln!("[warn] Subscription request failed: {}. Retrying...", e);
                tokio::time::sleep(Duration::from_secs(3)).await;
                continue;
            }
        };

        state.lock().await.stream_connected = true;
        println!("[info] Actively streaming real-time Pump.fun bonding curve transactions!\n");

        while let Some(msg_res) = stream.next().await {
            let msg = match msg_res {
                Ok(m) => m,
                Err(e) => {
                    eprintln!("[warn] Stream error: {}. Reconnecting...", e);
                    break;
                }
            };

            let Some(update_oneof) = msg.update_oneof else { continue; };
            let UpdateOneof::Transaction(tx_update) = update_oneof else { continue; };
            let Some(tx_info) = tx_update.transaction else { continue; };

            let now_ms = now_unix_ms();
            let mut s = state.lock().await;
            if now_ms.saturating_sub(s.last_stream_ms) > 2_000 {
                s.invalidate_market_coverage();
            }
            s.last_stream_ms = now_ms;
            let Some(obs) = bot::pump_receipt_decoder::decode_observation(&tx_info, tx_update.slot, now_ms) else {
                s.undecoded_receipts += 1;
                continue; // No instruction-limit fallback is allowed.
            };
            if !s.seen_signatures.insert(obs.signature.clone()) { continue; }
            s.signature_order.push_back(obs.signature.clone());
            if s.signature_order.len() > 50_000 {
                if let Some(old) = s.signature_order.pop_front() { s.seen_signatures.remove(&old); }
            }
            if let Err(e) = append_json(&s.observations_path, &serde_json::to_value(&obs)?) {
                eprintln!("[error] Observation audit failed: {}", e);
                continue;
            }
            for (mint, creator) in &obs.creators {
                s.curve_mgr.register_create(mint, creator, now_ms / 1000);
                let creator_label = s.whitelisted_wallets.get(creator).cloned();
                if let Some(label) = creator_label {
                    if let Some(curve) = s.curve_mgr.curves.get_mut(mint) {
                        let desc = format!("Creator {}: {}", label, creator);
                        curve.mark_whitelisted(desc);
                        println!(
                            "\n🌟 [TRACKED CREATOR DETECTED] Mint: {} | Created by Tracked Wallet: {} ({}) | ALL SHIELDS BYPASSED!",
                            mint, label, creator
                        );
                    }
                }
            }
            let fee_payer = tx_info.transaction.as_ref().and_then(|tx| tx.message.as_ref())
                .and_then(|msg| msg.account_keys.first()).map(|key| bs58::encode(key).into_string());
            let mut final_trades: Vec<(String, PumpTradeEvent)> = Vec::new();
            for trade in observation_trades(&obs, fee_payer.as_deref()) {
                let wl_label = if trade.is_buy {
                    s.whitelisted_wallets.get(&trade.user).cloned()
                } else {
                    None
                };
                let curve = s.curve_mgr.curves.entry(trade.mint.clone())
                    .or_insert_with(|| bot::curve_detector::CurveState::new(trade.mint.clone(), None, now_ms / 1000));
                
                // Tracked Wallet / Whitelist Detection on Buys
                if let Some(label) = wl_label {
                    if !curve.is_whitelisted {
                        let desc = format!("{}: {}", label, trade.user);
                        curve.mark_whitelisted(desc);
                        println!(
                            "\n🌟 [TRACKED BUY DETECTED] Mint: {} | Bought by Tracked Wallet: {} ({}) | Size: {:.2} SOL | ALL SHIELDS BYPASSED!",
                            trade.mint, label, trade.user, trade.sol_amount
                        );
                    }
                }

                curve.apply_onchain_trade(&trade);
                if let Some((_, last)) = final_trades.iter_mut().find(|(mint, _)| *mint == trade.mint) {
                    *last = trade;
                } else { final_trades.push((trade.mint.clone(), trade)); }
            }
            // Every instruction of the source transaction is applied atomically
            // before landing earlier intents or evaluating fresh triggers.
            for (mint, trade) in final_trades {
                s.sources.insert(mint.clone(), serde_json::json!({
                    "source_signature": obs.signature, "source_slot": obs.slot,
                    "source_transaction_index": obs.transaction_index,
                    "source_received_at_ms": obs.received_at_ms,
                    "venue": "curve"
                }));
                s.try_land_pending_buys(&mint, now_ms);
                s.update_positions(&mint, now_ms);

                // Start before the low-reserve S1 window as well as later entries.
                // A bounded audit may finish too late; pending/unknown means skip,
                // never buy using an unverified freshness verdict.
                let sol_usd_price = s.sol_usd_price;
                let min_scan_mcap_usd = s.min_scan_mcap_usd;
                let last_screen = s.holder_screen_times.get(&mint).copied();
                let due = last_screen.map_or(true, |at| now_ms.saturating_sub(at) >= 30_000)
                    && s.holder_screen_retry_after.get(&mint).map_or(true, |at| now_ms >= *at);
                if let Some(curve) = s.curve_mgr.curves.get_mut(&mint) {
                    let mcap_usd = curve.market_cap_usd(sol_usd_price);
                    if due && mcap_usd >= min_scan_mcap_usd
                        && !curve.audit_in_flight && !curve.is_botted_cabal
                        && !curve.is_whitelisted
                        && curve.unique_non_dev_buyers.len() >= 5
                    {
                        if let Ok(permit) = holder_screen_slots.clone().try_acquire_owned() {
                            curve.audit_in_flight = true;
                            curve.fresh_wallets_audited = false;
                            let client = http_client.clone();
                            let rpc = rpc_url.clone();
                            let mint_clone = mint.clone();
                            let st = state.clone();
                            let path = holder_screen_path.clone();
                            let pacing = holder_screen_last_start.clone();
                            let fallback_rpc = holder_screen_fallback_rpc.clone();
                            tokio::spawn(async move {
                                let _permit = permit;
                                {
                                    let mut last_start = pacing.lock().await;
                                    let elapsed = last_start.elapsed();
                                    if elapsed < Duration::from_secs(1) {
                                        tokio::time::sleep(Duration::from_secs(1) - elapsed).await;
                                    }
                                    *last_start = Instant::now();
                                }
                                let mut report = bot::holder_screen::screen_holders(&client, &rpc, &mint_clone).await;
                                let primary_rate_limited = report.status == "unknown"
                                    && report.reason.as_deref().is_some_and(|reason| reason.contains("HTTP 429"));
                                let mut rpc_provider = "primary";
                                if primary_rate_limited && fallback_rpc != rpc {
                                    report = bot::holder_screen::screen_holders(&client, &fallback_rpc, &mint_clone).await;
                                    rpc_provider = "fallback";
                                }
                                let mut s = st.lock().await;
                                let finished_ms = now_unix_ms();
                                s.holder_screen_times.insert(mint_clone.clone(), finished_ms);
                                let rate_limited = report.status == "unknown"
                                    && report.reason.as_deref().is_some_and(|reason| reason.contains("HTTP 429"));
                                s.holder_screen_retry_after.insert(mint_clone.clone(),
                                    finished_ms.saturating_add(if rate_limited {120_000} else {30_000}));
                                let is_blocked = report.status == "blocked";
                                let block_reason = report.reason.clone();
                                if let Some(c) = s.curve_mgr.curves.get_mut(&mint_clone) {
                                    c.audit_in_flight = false;
                                    c.fresh_wallets_audited = report.status == "clear";
                                    c.fresh_wallets_ratio = if report.sampled_wallets > 0
                                        && report.evidence.iter().all(|wallet| wallet.recent.is_some()) {
                                        Some(report.recent_wallets as f64 / report.sampled_wallets as f64)
                                    } else { None };
                                    if is_blocked {
                                        c.is_botted_cabal = true;
                                        println!("[HOLDER SHIELD] Blacklisted {}: {}", mint_clone,
                                            block_reason.as_deref().unwrap_or("holder policy"));
                                    }
                                }
                                if is_blocked {
                                    s.record_shielded_coin(&mint_clone,
                                        block_reason.as_deref().unwrap_or("holder policy"),
                                        "rpc_holder_screen", finished_ms / 1000);
                                }
                                let row = serde_json::json!({
                                    "event":"HOLDER_SCREEN", "vm_id":s.vm_id,
                                    "mint":mint_clone, "report":report,
                                    "rpc_provider":rpc_provider,
                                    "primary_rate_limited":primary_rate_limited,
                                    "policy":{"top_token_accounts":20,"minimum_wallet_sample":5,
                                        "low_balance_lamports":1_000_000_000u64,
                                        "low_balance_fraction_gte":0.5,"recent_wallet_rule_enabled":false,
                                        "clear_ttl_ms":30_000}
                                });
                                if let Err(error) = append_json(&path, &row) {
                                    eprintln!("[error] Holder screen evidence write failed: {}", error);
                                    if let Some(c) = s.curve_mgr.curves.get_mut(&mint_clone) {
                                        c.fresh_wallets_audited = false;
                                    }
                                }
                            });
                        }
                    }
                }

                let holder_ready = s.holder_screen_ready(&mint, now_ms);
                let (signal, reserve, anti_bundle) = {
                    let curve = s.curve_mgr.curves.get_mut(&mint).expect("applied curve");
                    let mcap_usd = curve.market_cap_usd(sol_usd_price);
                    let allow_scan = curve.is_whitelisted || mcap_usd >= min_scan_mcap_usd;
                    let signal = if (holder_ready || curve.is_whitelisted) && curve.quote_state().is_some() && allow_scan {
                        curve.evaluate_triggers(&trade)
                    } else {
                        None
                    };
                    (signal, curve.real_sol_reserve(), curve.anti_bundle_reason.clone())
                };
                if let Some(reason) = anti_bundle {
                    s.record_shielded_coin(&mint, &reason, "onchain_anti_bundle", now_ms / 1000);
                }
                s.update_post_exit_tracking(&mint, reserve, now_ms / 1000);
                if let Some(signal) = signal {
                    let cooling = s.circuit_breakers.get(&signal.strategy)
                        .map_or(false, |cb| cb.is_cooling_down(now_ms / 1000));
                    let is_botted = s.curve_mgr.curves.get(&signal.mint).map_or(false, |c| !c.is_whitelisted && c.is_botted_cabal);
                    if !cooling && !is_botted { s.open_pending_position(&signal, now_ms); }
                }
            }
        }

        {
            let mut s = state.lock().await;
            s.stream_connected = false;
            s.invalidate_market_coverage();
        }
        tokio::time::sleep(Duration::from_secs(2)).await;
    }
}

#[cfg(test)]
mod ghost_accounting_tests {
    use super::*;

    fn app() -> AppState {
        static TEST_DIRECTORY_ID: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
        let directory = format!("/tmp/ghost-accounting-{}-{}-{}", std::process::id(), now_unix_ms(),
            TEST_DIRECTORY_ID.fetch_add(1, std::sync::atomic::Ordering::Relaxed));
        let mut curve = bot::curve_detector::CurveState::new("mint".into(), Some("creator".into()), 0);
        curve.v_sol = 40_000_000_000;
        curve.v_tokens = 800_000_000_000_000;
        curve.r_sol = 10_000_000_000;
        curve.r_tokens = 500_000_000_000_000;
        curve.protocol_fee_bps = Some(95);
        curve.creator_fee_bps = Some(30);
        curve.fee_policy_known = true;
        curve.supported_sol_quote = true;
        curve.reserves_authoritative = true;
        curve.fresh_wallets_audited = true;
        let mut manager = CurveManager::new();
        manager.curves.insert("mint".into(), curve);
        AppState {
            curve_mgr: manager, paper_positions: vec![], closed_positions: vec![],
            circuit_breakers: HashMap::new(), virtual_cash: 15.0, bankroll_initial: 15.0,
            max_positions: 2, vm_id: "test".into(),
            trades_log_path: format!("{}/trades.jsonl", directory),
            summary_path: format!("{}/summary.json", directory), start_time: Instant::now(),
            observations_path: format!("{}/observations.jsonl", directory),
            intents_path: format!("{}/intents.jsonl", directory),
            sources: HashMap::from([("mint".into(), serde_json::json!({
                "source_signature":"signal", "source_slot":1,"source_transaction_index":0
            }))]),
            position_ids: HashMap::new(), intents: HashMap::new(), next_intent: 0,
            delay_ms:70, stream_connected:true,last_stream_ms:1_000,
            seen_signatures:HashSet::new(),signature_order:VecDeque::new(),undecoded_receipts:0,
            failed_buy_costs:HashMap::new(),failed_buy_attempts:0,reconcile_enabled:false,
            holder_screen_times:HashMap::from([("mint".into(),1_000)]),
            holder_screen_retry_after:HashMap::new(),
            shielded_coins: vec![],
            shielded_coins_log_path: format!("{}/shielded.jsonl", directory),
            min_scan_mcap_usd: 0.0,
            sol_usd_price: 145.0,
            whitelisted_wallets: HashMap::new(),
        }
    }

    #[test]
    fn tracked_wallet_whitelist_bypasses_all_shields_and_authorizes_buy() {
        let mut app = app();
        {
            let curve = app.curve_mgr.curves.get_mut("mint").unwrap();
            curve.is_botted_cabal = true;
            curve.fresh_wallets_audited = false;
            curve.audit_in_flight = true;
            curve.block_0_tokens_bought = 300_000_000_000_000; // > 20%
            assert!(curve.check_anti_bundle_safety(5).is_err());
        }
        
        // Before whitelist: anti-bundle errors and holder screen fails
        assert!(!app.holder_screen_ready("mint", 1_000));
        app.open_pending_position(&signal(), 1_000);
        assert!(app.paper_positions.is_empty());

        // Whitelist by tracked wallet (e.g. Chester)
        {
            let curve = app.curve_mgr.curves.get_mut("mint").unwrap();
            curve.mark_whitelisted("Chester: PMJA8UQDyWTFw2Smhyp9jGA6aTaP7jKHR7BPudrgyYN".into());
            assert!(curve.is_whitelisted);
            assert!(!curve.is_botted_cabal);
            assert!(curve.check_anti_bundle_safety(5).is_ok());
        }
        assert!(app.holder_screen_ready("mint", 1_000));

        // Now buy authorizes immediately
        app.open_pending_position(&signal(), 1_000);
        assert_eq!(app.paper_positions.len(), 1);
        assert!(app.paper_positions[0].is_whitelisted);
        assert_eq!(app.paper_positions[0].whitelisted_by.as_deref(), Some("Chester: PMJA8UQDyWTFw2Smhyp9jGA6aTaP7jKHR7BPudrgyYN"));

        // Lands successfully after fill delay without being cancelled
        app.try_land_pending_buys("mint", 1_070);
        assert_eq!(app.paper_positions.len(), 1);
        assert!(matches!(app.paper_positions[0].state, bot::curve_detector::PositionState::Open));
    }

    #[test]
    fn holder_screen_pending_unknown_and_expired_cannot_authorize_a_buy() {
        let mut app = app();
        app.curve_mgr.curves.get_mut("mint").unwrap().fresh_wallets_audited = false;
        app.open_pending_position(&signal(), 1_000);
        assert!(app.paper_positions.is_empty());
        assert_eq!(app.virtual_cash, 15.0);
        let curve = app.curve_mgr.curves.get_mut("mint").unwrap();
        curve.fresh_wallets_audited = true;
        curve.audit_in_flight = true;
        app.open_pending_position(&signal(), 1_000);
        assert!(app.paper_positions.is_empty());
        app.curve_mgr.curves.get_mut("mint").unwrap().audit_in_flight = false;
        app.open_pending_position(&signal(), 31_000);
        assert!(app.paper_positions.is_empty());
        app.holder_screen_times.insert("mint".into(), 31_000);
        app.open_pending_position(&signal(), 31_000);
        assert_eq!(app.paper_positions.len(), 1);
    }

    #[test]
    fn expired_holder_screen_cancels_paper_buy_instead_of_delaying_old_signal() {
        let mut app = app();
        app.open_pending_position(&signal(), 1_000);
        app.try_land_pending_buys("mint", 31_000);
        assert!(app.paper_positions.is_empty());
        assert!((app.virtual_cash - 15.0).abs() < 1e-12);
        assert_eq!(app.failed_buy_attempts, 0);
    }

    #[test]
    fn holder_blacklist_cancels_unsubmitted_paper_buy_and_refunds_reservation() {
        let mut app = app();
        app.open_pending_position(&signal(), 1_000);
        assert_eq!(app.paper_positions.len(), 1);
        app.curve_mgr.curves.get_mut("mint").unwrap().is_botted_cabal = true;
        app.try_land_pending_buys("mint", 1_070);
        assert!(app.paper_positions.is_empty());
        assert!((app.virtual_cash - 15.0).abs() < 1e-12);
        assert_eq!(app.failed_buy_attempts, 0);
        assert!(app.closed_positions.is_empty());
        let rows = std::fs::read_to_string(&app.intents_path).unwrap();
        let last: serde_json::Value = serde_json::from_str(rows.lines().last().unwrap()).unwrap();
        assert_eq!(last["event"], "CANCEL");
        assert_eq!(last["network_fee_raw"], 0);
    }

    fn signal() -> StrategySignal {
        StrategySignal {strategy:StrategyKind::DevDumpAbsorption,mint:"mint".into(),
            reserve_sol:10.0,buyer_breadth:40,developer_held_pct:0.0,timestamp:1,
            slot:1,signal_trough_spot:None,details:"test signal".into()}
    }

    fn external_buy(app: &mut AppState, budget: u64) {
        let curve = app.curve_mgr.curves.get_mut("mint").unwrap();
        let state = curve.quote_state().unwrap();
        let quote = state.quote_buy(budget).unwrap();
        let after = state.moved(quote.curve_sol_raw, quote.tokens_raw, true).unwrap();
        curve.v_sol=after.vsol_raw;curve.v_tokens=after.vtokens_raw;
        curve.r_sol=after.rsol_raw;curve.r_tokens=after.rtokens_raw;
    }

    #[test]
    fn reserved_cash_is_not_a_loss_and_buy_lands_after_delay() {
        let mut app=app();app.open_pending_position(&signal(),1_000);
        assert!((app.calculate_total_equity()-15.0).abs()<1e-9);
        app.check_wall_clock_timeouts(1_069);
        assert_eq!(app.paper_positions[0].tokens_held,0);
        app.check_wall_clock_timeouts(1_070);
        let p=&app.paper_positions[0];assert!(p.tokens_held>0);
        assert!((app.virtual_cash-(15.0-p.entry_cost_sol)).abs()<1e-9);
        assert_eq!(p.last_fill.as_ref().unwrap().filled_at_ms,1_070);
    }

    #[test]
    fn failed_buy_refunds_ticket_and_charges_only_the_attempt_fee() {
        let mut app=app();app.open_pending_position(&signal(),1_000);
        external_buy(&mut app,5_000_000_000);
        app.check_wall_clock_timeouts(1_070);
        assert!(app.paper_positions.is_empty());assert!(app.closed_positions.is_empty());
        let fee=bot::curve_detector::FAILED_GUARD_FEE_LAMPORTS as f64/1e9;
        assert!((app.virtual_cash-(15.0-fee)).abs()<1e-9);
        let summary=app.generate_summary(2);
        assert!((summary.total_net_pnl_sol+fee).abs()<1e-9);
        assert_eq!(summary.total_closed_trades,0);assert_eq!(app.failed_buy_attempts,1);
    }

    #[test]
    fn a_partial_sale_credits_cash_only_at_its_landing() {
        let mut app=app();app.open_pending_position(&signal(),1_000);
        app.check_wall_clock_timeouts(1_070);
        external_buy(&mut app,10_000_000_000);
        let before=app.virtual_cash;app.update_positions("mint",1_200);
        assert!(app.paper_positions[0].pending_exit.is_some());
        assert!((app.virtual_cash-before).abs()<1e-9);
        app.update_positions("mint",1_269);assert!((app.virtual_cash-before).abs()<1e-9);
        app.update_positions("mint",1_270);
        let proceeds=app.paper_positions[0].tranche1_proceeds;
        assert!(proceeds>0.0);assert!((app.virtual_cash-before-proceeds).abs()<1e-9);
        let audit=std::fs::read_to_string(&app.intents_path).unwrap();
        let row:serde_json::Value=serde_json::from_str(audit.lines().last().unwrap()).unwrap();
        assert_eq!(row["event"],"FILL");assert_eq!(row["status"],"filled_partial");
        app.update_positions("mint",1_280);
        assert!((app.virtual_cash-before-proceeds).abs()<1e-9);
    }

    #[test]
    fn missing_stream_coverage_never_fills_a_due_intent() {
        let mut app=app();app.open_pending_position(&signal(),1_000);
        app.stream_connected=false;app.check_wall_clock_timeouts(1_100);
        assert_eq!(app.paper_positions[0].tokens_held,0);
        app.stream_connected=true;app.check_wall_clock_timeouts(4_000);
        assert_eq!(app.paper_positions[0].tokens_held,0);
        // A heartbeat/transaction on another coin must not restore this coin.
        app.last_stream_ms=4_001;app.check_wall_clock_timeouts(4_010);
        assert_eq!(app.paper_positions[0].tokens_held,0);
        assert!(app.curve_mgr.curves["mint"].quote_state().is_none());
    }

    fn amm_fixture(mint: &str, at_ms: u64) -> bot::migration_amm::AmmSnapshot {
        bot::migration_amm::AmmSnapshot {
            pool:"authenticated-pool-fixture".into(), mint:mint.into(),base_vault:"base-vault".into(),quote_vault:"quote-vault".into(),
            base_reserve_raw:100_000_000_000_000,quote_reserve_raw:150_000_000_000,virtual_quote_reserve_raw:0,
            base_decimals:6,lp_fee_bps:20,protocol_fee_bps:5,creator_fee_bps:30,
            context_slot:100,observed_at_ms:at_ms,opened_at_ms:at_ms,source:"authenticated fixture".into(),
            base_supply_raw:1_000_000_000_000_000,fee_tiers:vec![],global_fallback_fees:None,
            fee_deferred_mode:false,supports_fee_deferred_mode:true,
        }
    }

    fn migrating_position(strategy: StrategyKind) -> (PaperPosition,bot::curve_detector::CurveState) {
        let mut pos=PaperPosition::new_pending_at_ms_with_delays(strategy,"migrated-mint".into(),100,72.0,0.5,1_000,70,70);
        pos.state=bot::curve_detector::PositionState::AwaitingMigration;
        pos.entry_cost_sol=0.501505;pos.tokens_held=1_500_000_000_000;pos.original_tokens=pos.tokens_held;
        pos.migration_detected_at_ms=Some(1_000);
        let mut curve=bot::curve_detector::CurveState::new(pos.mint.clone(),None,0);
        curve.r_tokens=0;
        (pos,curve)
    }

    #[test]
    fn migrated_spot_alone_cannot_mark_queue_or_credit_a_sale() {
        let (mut pos,mut curve)=migrating_position(StrategyKind::PreGraduationCarryover);
        pos.post_migration_spot_sol=Some(100.0);
        assert!(pos.executable_proceeds_sol_at_ms(&curve,1_000_000).is_none());
        pos.update_at_ms(&mut curve,1_000_000);
        assert!(pos.pending_exit.is_none());
        assert_eq!(pos.tokens_held,1_500_000_000_000);
        assert_eq!(pos.network_fees_raw,0);
    }

    #[test]
    fn migrated_s5_half_and_timeout_use_fresh_landing_quotes_and_preserve_ready_time() {
        let (mut pos,mut curve)=migrating_position(StrategyKind::PreGraduationCarryover);
        pos.attach_amm_snapshot(amm_fixture(&pos.mint,20_000)).unwrap();
        let mark=pos.executable_proceeds_sol_at_ms(&curve,20_000).unwrap();
        assert!(mark>2.0 && mark<2.25); // Finite-size quote below spot*inventory.
        pos.update_at_ms(&mut curve,20_000);
        let first=pos.pending_exit.as_ref().unwrap().clone();
        assert_eq!(first.tokens_raw,750_000_000_000);
        assert_eq!(first.ready_at_ms,20_070);
        for t in [20_010,20_020,20_060] {pos.update_at_ms(&mut curve,t);}
        assert_eq!(pos.pending_exit.as_ref().unwrap().ready_at_ms,20_070);
        assert!(pos.land_pending_exit_at_ms(&mut curve,20_070).is_none());
        assert_eq!(pos.tokens_held,1_500_000_000_000); // Pre-ready snapshot cannot fill.
        let mut landed=amm_fixture(&pos.mint,20_070);
        landed.quote_reserve_raw=120_000_000_000; // Intervening dump: accept actual quote, no sell guard.
        let expected=landed.quote_sell(first.tokens_raw).unwrap().net_sol_raw;
        pos.attach_amm_snapshot(landed).unwrap();
        assert!(pos.land_pending_exit_at_ms(&mut curve,20_070).is_none());
        assert_eq!(pos.tokens_held,750_000_000_000);
        assert!(pos.tranche1_sold);
        assert_eq!(pos.last_fill.as_ref().unwrap().net_sol_raw,Some(expected));
        assert_ne!(pos.last_fill.as_ref().unwrap().net_sol_raw,first.expected_output_raw);
        assert_eq!(pos.network_fees_raw,bot::curve_detector::STANDARD_NETWORK_FEE_LAMPORTS);
        let partial_credit=pos.tranche1_proceeds;
        // Isolate the opening timer here; the next test covers the prior-peak trail.
        pos.peak_executable_roi=0.0;
        let mut later=amm_fixture(&pos.mint,50_000);later.quote_reserve_raw=120_000_000_000;
        pos.attach_amm_snapshot(later).unwrap();
        pos.update_at_ms(&mut curve,50_000);
        let pending=pos.pending_exit.as_ref().unwrap();
        assert_eq!(pending.tokens_raw,750_000_000_000);
        assert!(pending.reason.contains("30s after authenticated AMM opening"));
        assert_eq!(pending.ready_at_ms,50_070);
        let mut final_snapshot=amm_fixture(&pos.mint,50_070);final_snapshot.quote_reserve_raw=120_000_000_000;
        pos.attach_amm_snapshot(final_snapshot).unwrap();
        let pnl=pos.land_pending_exit_at_ms(&mut curve,50_070).unwrap();
        assert_eq!(pos.tokens_held,0);assert!(pos.is_closed);
        assert_eq!(pos.network_fees_raw,2*bot::curve_detector::STANDARD_NETWORK_FEE_LAMPORTS);
        assert_eq!(pnl,pos.proceeds_sol-pos.entry_cost_sol);
        assert!(pos.proceeds_sol>partial_credit);
        assert!(pos.last_fill.as_ref().unwrap().amm_state_before.is_some());
    }

    #[test]
    fn s5_relative_trail_carries_into_amm_and_stale_data_preserves_inventory() {
        let (mut pos,mut curve)=migrating_position(StrategyKind::PreGraduationCarryover);
        pos.tranche1_sold=true;pos.tranche1_intent_fired=true;pos.tranche1_proceeds=1.0;
        pos.peak_executable_roi=8.0;
        pos.attach_amm_snapshot(amm_fixture(&pos.mint,20_000)).unwrap();
        pos.update_at_ms(&mut curve,22_001);
        assert!(pos.pending_exit.is_none());
        pos.update_at_ms(&mut curve,20_001);
        assert!(pos.pending_exit.as_ref().unwrap().reason.contains("8% relative"));
        assert!(pos.land_pending_exit_at_ms(&mut curve,25_000).is_none());
        assert_eq!(pos.tokens_held,1_500_000_000_000);
    }

    #[test]
    fn original_s3_timer_executes_into_amm_without_replacing_it_with_s5() {
        let (mut pos,mut curve)=migrating_position(StrategyKind::DislocationFloor);
        pos.entry_time_ms=0;
        pos.attach_amm_snapshot(amm_fixture(&pos.mint,60_000)).unwrap();
        pos.update_at_ms(&mut curve,60_000);
        assert!(pos.pending_exit.as_ref().unwrap().reason.contains("S3 60s"));
        pos.attach_amm_snapshot(amm_fixture(&pos.mint,60_070)).unwrap();
        assert!(pos.land_pending_exit_at_ms(&mut curve,60_070).is_some());
        assert_eq!(pos.strategy,StrategyKind::DislocationFloor);
    }

    #[test]
    fn runtime_checkpoint_retains_inventory_cash_breakers_and_pending_readiness() {
        let mut first=app();
        let (mut pos,curve)=migrating_position(StrategyKind::PreGraduationCarryover);
        pos.attach_amm_snapshot(amm_fixture(&pos.mint,20_000)).unwrap();
        let mut curve=curve;
        pos.update_at_ms(&mut curve,20_000);
        first.curve_mgr.curves.insert(pos.mint.clone(),curve);
        first.virtual_cash=13.498495;
        first.paper_positions.push(pos);
        first.circuit_breakers.insert(StrategyKind::PreGraduationCarryover,CircuitBreaker::for_strategy(StrategyKind::PreGraduationCarryover));
        first.next_intent=42;
        let value=first.checkpoint_value();
        let mut restored=app();restored.restore_checkpoint(&value).unwrap();
        assert_eq!(restored.virtual_cash,first.virtual_cash);
        assert_eq!(restored.paper_positions[0].tokens_held,first.paper_positions[0].tokens_held);
        assert_eq!(restored.paper_positions[0].pending_exit.as_ref().unwrap().ready_at_ms,20_070);
        assert_eq!(restored.next_intent,42);
        assert!(restored.paper_positions[0].migration_amm.is_none());
        assert!(!restored.stream_connected);
        assert!(!restored.curve_mgr.curves["migrated-mint"].reserves_authoritative);
        let path=format!("/tmp/migration-checkpoint-{}-{}.json",std::process::id(),now_unix_ms());
        write_checkpoint_atomic(&path,&value).unwrap();
        let read:serde_json::Value=serde_json::from_slice(&std::fs::read(&path).unwrap()).unwrap();
        assert_eq!(read["virtual_cash"],value["virtual_cash"]);
        std::fs::remove_file(path).unwrap();
    }
}
