#![allow(dead_code)]

mod bot {
    #[path = "/home/mthwt/code/Crypto/src/bot/ghost_execution.rs"]
    pub mod ghost_execution;
    #[path = "/home/mthwt/code/Crypto/src/bot/migration_amm.rs"]
    pub mod migration_amm;
    #[path = "/home/mthwt/code/Crypto/src/bot/curve_detector.rs"]
    pub mod curve_detector;
}

use bot::curve_detector::{CurveState, PumpTradeEvent};
use serde_json::{json, Value};
use std::collections::{BTreeMap, HashMap, HashSet};
use std::env;
use std::fs::{self, File};
use std::io::{BufRead, BufReader, Write};

const INPUT: &str = "/home/mthwt/code/Crypto/data/ghost_observations.jsonl";
const MANIFEST: &str = "/home/mthwt/code/Crypto/reports/blocked_coin_audit_20261011/MANIFEST.json";
const OUT_ROWS: &str = "/home/mthwt/code/Crypto/reports/blocked_coin_audit_20261011/candidate_rows.jsonl";
const OUT_META: &str = "/home/mthwt/code/Crypto/reports/blocked_coin_audit_20261011/candidate_meta.json";
const SESSION_START_MS: u64 = 1_791_756_021_000;

fn field_u64(v: &Value, name: &str) -> u64 {
    v.get(name).and_then(Value::as_u64).unwrap_or(0)
}

fn field_bool(v: &Value, name: &str) -> bool {
    v.get(name).and_then(Value::as_bool).unwrap_or(false)
}

fn field_string(v: &Value, name: &str) -> String {
    v.get(name).and_then(Value::as_str).unwrap_or_default().to_owned()
}

fn optional_u64(v: &Value, name: &str) -> Option<u64> {
    v.get(name).and_then(Value::as_u64)
}

fn as_u16(v: &Value, name: &str) -> Option<u16> {
    v.get(name).and_then(Value::as_u64).and_then(|n| u16::try_from(n).ok())
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = env::args().skip(1).collect();
    let (input_path, out_rows, out_meta, ordering_model) = if args.is_empty() {
        (INPUT.to_owned(), OUT_ROWS.to_owned(), OUT_META.to_owned(), "provider_receive_order")
    } else if args.len() == 4 && args[0] == "--chain-order" {
        (args[1].clone(), args[2].clone(), args[3].clone(), "slot_transaction_index")
    } else {
        return Err("usage: blocked-source-candidates [--chain-order SORTED_INPUT ROWS_OUT META_OUT]".into());
    };
    let manifest: Value = serde_json::from_slice(&fs::read(MANIFEST)?)?;
    let manifest_input_size = manifest["inputs"]["data/ghost_observations.jsonl"]["size_bytes"]
        .as_u64().ok_or("manifest has no observations size")?;
    let input_limit = if ordering_model == "provider_receive_order" {
        manifest_input_size
    } else {
        fs::metadata(&input_path)?.len()
    };
    let cutoff_ms = manifest["cutoff_ms"].as_u64().ok_or("manifest has no cutoff_ms")?;
    let manifest_start_ms = manifest["start_ms"].as_u64().ok_or("manifest has no start_ms")?;
    if manifest_start_ms != SESSION_START_MS {
        return Err(format!("session-start mismatch: code={} manifest={}", SESSION_START_MS, manifest_start_ms).into());
    }

    let input_file = File::open(&input_path)?;
    let mut reader = BufReader::new(input_file);
    let mut out = File::create(&out_rows)?;
    let mut curves: HashMap<String, CurveState> = HashMap::new();
    let mut create_observed: HashSet<String> = HashSet::new();
    let mut max_received_by_mint: HashMap<String, u64> = HashMap::new();
    let mut seen: HashSet<(String, String, String)> = HashSet::new();
    let mut family_counts: BTreeMap<String, u64> = BTreeMap::new();
    let mut family_mints: BTreeMap<String, HashSet<String>> = BTreeMap::new();
    let mut candidate_mints_with_create: HashSet<String> = HashSet::new();
    let mut candidate_mints_without_create: HashSet<String> = HashSet::new();

    let mut consumed_bytes = 0u64;
    let mut rows_seen = 0u64;
    let mut receipts_through_cutoff = 0u64;
    let mut receipts_before_session = 0u64;
    let mut events_applied = 0u64;
    let mut create_links_seen = 0u64;
    let mut candidates_written = 0u64;
    let mut rows_after_cutoff = 0u64;
    let mut trailing_partial_bytes = 0u64;
    let mut first_received_ms = None;
    let mut last_received_ms = None;

    let mut line = Vec::new();
    loop {
        line.clear();
        let n = reader.read_until(b'\n', &mut line)?;
        if n == 0 { break; }
        let available = input_limit.saturating_sub(consumed_bytes);
        if n as u64 > available {
            // The manifest freezes a byte prefix. Ignore bytes beyond that prefix.
            if available == 0 { break; }
            if n as u64 > available {
                // Since read_until may cross the frozen boundary, the row is not
                // accepted unless its complete newline is inside the frozen prefix.
                if line.get(available as usize - 1) != Some(&b'\n') {
                    trailing_partial_bytes = available;
                    break;
                }
                line.truncate(available as usize);
            }
        }
        consumed_bytes = consumed_bytes.saturating_add(line.len() as u64);
        if line.last() != Some(&b'\n') {
            trailing_partial_bytes = line.len() as u64;
            break;
        }
        rows_seen += 1;
        let receipt: Value = serde_json::from_slice(&line)?;
        let received_ms = field_u64(&receipt, "received_at_ms");
        first_received_ms = Some(first_received_ms.map_or(received_ms, |old: u64| old.min(received_ms)));
        if received_ms > cutoff_ms {
            rows_after_cutoff += 1;
            break;
        }
        receipts_through_cutoff += 1;
        last_received_ms = Some(last_received_ms.map_or(received_ms, |old: u64| old.max(received_ms)));
        if received_ms < SESSION_START_MS { receipts_before_session += 1; }

        let received_ts = received_ms / 1000;
        let slot = field_u64(&receipt, "slot");
        let transaction_index = field_u64(&receipt, "transaction_index");
        let signature = field_string(&receipt, "signature");
        let mut receipt_mints = HashSet::new();
        if let Some(creates) = receipt.get("creators").and_then(Value::as_array) {
            for pair in creates {
                if let Some(mint) = pair.as_array().and_then(|p| p.first()).and_then(Value::as_str) {
                    receipt_mints.insert(mint.to_owned());
                }
            }
        }
        if let Some(events) = receipt.get("events").and_then(Value::as_array) {
            for event in events {
                if let Some(mint) = event.get("mint").and_then(Value::as_str) {
                    receipt_mints.insert(mint.to_owned());
                }
            }
        }
        let prior_chain_receive_max: HashMap<String, Option<u64>> = receipt_mints
            .iter()
            .map(|mint| (mint.clone(), max_received_by_mint.get(mint).copied()))
            .collect();

        // Match the live order: register every create mapping before processing
        // any trade event in the same complete receipt.
        if let Some(creates) = receipt.get("creators").and_then(Value::as_array) {
            for pair in creates {
                let Some(pair) = pair.as_array() else { continue; };
                if pair.len() < 2 { continue; }
                let Some(mint) = pair[0].as_str() else { continue; };
                let Some(creator) = pair[1].as_str() else { continue; };
                create_links_seen += 1;
                let state = curves.entry(mint.to_owned()).or_insert_with(|| {
                    CurveState::new(mint.to_owned(), Some(creator.to_owned()), received_ts)
                });
                state.creator = Some(creator.to_owned());
                create_observed.insert(mint.to_owned());
            }
        }

        let mut last_by_mint: Vec<(String, PumpTradeEvent)> = Vec::new();
        if let Some(events) = receipt.get("events").and_then(Value::as_array) {
            for event in events {
                let mint = field_string(event, "mint");
                if mint.is_empty() { continue; }
                let user = field_string(event, "user");
                let creator = field_string(event, "creator");
                let trade = PumpTradeEvent {
                    mint: mint.clone(),
                    user,
                    is_buy: field_bool(event, "is_buy"),
                    is_create: false,
                    sol_amount: field_u64(event, "sol_raw") as f64 / 1e9,
                    token_amount: field_u64(event, "tokens_raw"),
                    slot,
                    // The current live decoder path uses provider receive time in
                    // whole seconds, not the Pump event timestamp.
                    timestamp: received_ts,
                    signature: signature.clone(),
                    onchain_rsol: optional_u64(event, "rsol_raw"),
                    onchain_vsol: optional_u64(event, "vsol_raw"),
                    onchain_vtokens: optional_u64(event, "vtokens_raw"),
                    onchain_rtokens: optional_u64(event, "rtokens_raw"),
                    protocol_fee_bps: as_u16(event, "fee_bps"),
                    creator_fee_bps: as_u16(event, "creator_fee_bps"),
                    fee_policy_known: field_bool(event, "fee_policy_known"),
                    supported_sol_quote: field_bool(event, "supported_sol_quote"),
                    creator: if creator.is_empty() { None } else { Some(creator) },
                    // Saved ReceiptObservation omits the fee-payer pubkey, so
                    // the live fee-payer-only dust-balance assignment cannot be
                    // reconstructed without guessing.
                    signer_post_sol_lamports: None,
                };
                let state = curves.entry(mint.clone()).or_insert_with(|| {
                    CurveState::new(mint.clone(), None, received_ts)
                });
                state.apply_onchain_trade(&trade);
                events_applied += 1;
                if let Some((_, last)) = last_by_mint.iter_mut().find(|(seen_mint, _)| *seen_mint == mint) {
                    *last = trade;
                } else {
                    last_by_mint.push((mint, trade));
                }
            }
        }
        for mint in &receipt_mints {
            max_received_by_mint
                .entry(mint.clone())
                .and_modify(|old| *old = (*old).max(received_ms))
                .or_insert(received_ms);
        }

        if received_ms < SESSION_START_MS || received_ms > cutoff_ms { continue; }
        for (mint, last_trade) in last_by_mint {
            let Some(state) = curves.get(&mint) else { continue; };
            // Observer first: this clones CurveState and does not mutate the
            // one-shot `signal_fired` set or allow shield state to suppress it.
            let signals = state.audit_entry_candidates(&last_trade);
            if signals.is_empty() { continue; }
            let age_seconds = last_trade.timestamp.saturating_sub(state.created_at_ts);
            let anti_bundle_result = state.check_anti_bundle_safety(age_seconds);
            let anti_bundle_reason = anti_bundle_result.err().map(str::to_owned);
            for signal in signals {
                let family = signal.strategy.code().to_owned();
                let key = (mint.clone(), family.clone(), signature.clone());
                if !seen.insert(key) { continue; }
                let genesis_observed = create_observed.contains(&mint);
                let prior_max_received_ms = prior_chain_receive_max.get(&mint).copied().flatten();
                let prior_state_uses_late_receipt = prior_max_received_ms
                    .map_or(false, |prior_ms| prior_ms > received_ms);
                if genesis_observed {
                    candidate_mints_with_create.insert(mint.clone());
                } else {
                    candidate_mints_without_create.insert(mint.clone());
                }
                *family_counts.entry(family.clone()).or_default() += 1;
                family_mints.entry(family.clone()).or_default().insert(mint.clone());
                let signal_value = serde_json::to_value(&signal)?;
                let row = json!({
                    "timestamp_ms": received_ms,
                    "ordering_model": ordering_model,
                    "candidate_state_is_chain_ordered": ordering_model == "slot_transaction_index",
                    "slot": slot,
                    "transaction_index": transaction_index,
                    "signature": &signature,
                    "mint": &mint,
                    "family": &family,
                    "creation_observed": genesis_observed,
                    "creation_coverage": if genesis_observed { "create receipt observed in saved observation prefix" } else { "genesis unknown; do not claim complete history" },
                    "prior_chain_state_max_received_ms": prior_max_received_ms,
                    "prior_chain_state_uses_later_received_data": prior_state_uses_late_receipt,
                    "signal": signal_value,
                    "signal_reserve_sol": signal.reserve_sol,
                    "spot": state.spot_price(),
                    "qualified_buyer_count": state.qualified_outside_buyers.len(),
                    "anti_bundle_clear": anti_bundle_reason.is_none(),
                    "anti_bundle_first_reason": anti_bundle_reason.as_deref(),
                    "anti_bundle_check_age_seconds": age_seconds,
                    "runtime_whitelist_context_reconstructed": false,
                    "async_fresh_wallet_cabal_state_reconstructed": false,
                    "receipt": &receipt
                });
                serde_json::to_writer(&mut out, &row)?;
                out.write_all(b"\n")?;
                candidates_written += 1;
            }
        }
    }
    out.flush()?;

    let family_unique_mints: BTreeMap<String, usize> = family_mints
        .into_iter().map(|(family, mints)| (family, mints.len())).collect();
    let output_bytes = fs::metadata(&out_rows)?.len();
    let meta = json!({
        "task": "offline source-predicate candidate audit",
        "input": INPUT,
        "processing_input": input_path,
        "ordering_model": ordering_model,
        "input_manifest_path": MANIFEST,
        "input_manifest_size_bytes": manifest_input_size,
        "processing_input_limit_bytes": input_limit,
        "processing_bytes_consumed": consumed_bytes,
        "manifest_cutoff_ms": cutoff_ms,
        "manifest_session_start_ms": SESSION_START_MS,
        "manifest_warmup_start_ms": first_received_ms,
        "last_receipt_at_or_before_cutoff_ms": last_received_ms,
        "rows_seen_including_first_after_cutoff": rows_seen,
        "receipts_through_cutoff": receipts_through_cutoff,
        "receipts_before_candidate_window_used_for_state": receipts_before_session,
        "first_post_cutoff_rows_seen": rows_after_cutoff,
        "trailing_partial_bytes_within_manifest_prefix": trailing_partial_bytes,
        "curve_trade_events_applied": events_applied,
        "create_mappings_observed": create_links_seen,
        "candidate_rows": candidates_written,
        "candidate_counts_by_family": family_counts,
        "unique_mints_by_family": family_unique_mints,
        "candidate_mints_with_create_observed": candidate_mints_with_create.len(),
        "candidate_mints_without_create_observed": candidate_mints_without_create.len(),
        "candidate_rows_path": out_rows,
        "candidate_rows_bytes": output_bytes,
        "method": [
            if ordering_model == "provider_receive_order" { "Parsed only complete newline-terminated ReceiptObservation rows inside the MANIFEST frozen byte prefix and received_at_ms cutoff." } else { "Parsed the complete sorted ReceiptObservation file built only from complete rows inside the MANIFEST frozen byte prefix and received_at_ms cutoff." },
            "Mirrored the live order: register receipt create mappings, apply every event in the complete receipt in log order, then evaluate only the last event per mint.",
            "Used current Rust CurveState.apply_onchain_trade and observer-only CurveState.audit_entry_candidates; candidate audit runs before the anti-bundle check and does not mutate signal_fired.",
            "Dedupe key is mint/family/signature. Repeated source-predicate opportunities on later signatures remain visible.",
            "Each candidate row embeds the complete original receipt JSON, including all events and raw_logs.",
            if ordering_model == "slot_transaction_index" {
                "Chain-order output is a canonical chronology diagnostic; records may have arrived after the candidate receipt and this output does not claim those predicates were available to the live process at that receive time."
            } else {
                "Receive-order output mirrors the observed stream order used by the live process; the frozen tape contains same-slot transaction-index inversions, so it is not canonical block order."
            }
        ],
        "source_screen_scope": "anti-bundle CurveState check only; runtime whitelist context and asynchronous fresh-wallet/cabal state are not reconstructed; not holder RPC verdict, live admission, funding/capacity, execution, or PnL",
        "coverage_and_limitations": [
            "A mint without an observed create mapping has unknown genesis and incomplete pre-prefix history; candidate predicates can be missed or distorted.",
            "ReceiptObservation lacks the fee payer pubkey, so signer_post_sol_lamports is deliberately not assigned to any user; fresh-wallet/dust anti-bundle state is therefore not reconstructed.",
            "Tracked wallet and KOL whitelist files/environment are not used; a deterministic anti-bundle reason can be bypassed in the running process for a whitelisted coin.",
            "No create event is fabricated as a trade. The live code registers the create mapping before receipt trades, which this helper mirrors.",
            "Source predicates are current checked-out Rust behavior, not proof of deployed binary/config parity or canonical registry parity."
        ]
    });
    fs::write(&out_meta, serde_json::to_vec_pretty(&meta)?)?;
    eprintln!("wrote {candidates_written} source-predicate candidate rows; {receipts_through_cutoff} receipts through cutoff");
    Ok(())
}

