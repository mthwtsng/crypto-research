# Calibrated Starting 5 Strategies Backup (October 10, 2026)

Backup of high-performing calibrated rules established during live shadow testing before remote fetch/pull.

## Exact Calibrated Entry Rules (`src/bot/curve_detector.rs`)

### S1: Dev Dump Absorption
- Reserves: 1.0 – 5.0 SOL
- Creator sold >= 95% of allocation (or 0 balance)
- Drawdown: 25% – 60% from peak
- Post-trough timing: within 3 slots of post-peak trough
- Buyer breadth: >= 2 distinct non-creator buyers buying >= 0.30 SOL total

### S2: Survival Shelf Breakout
- Cross 10.8 SOL from below (reserves 10.8 – 14.0 SOL)
- Age: >= 30s
- Qualified outside buyers: >= 25 (buying >= 0.05 SOL)
- Max holder topshare: <= 20% of circulating supply
- Last 2 outside transactions: buys only
- New price above trailing 30s high

### S3: Dislocation Floor / Two-Buyer Bounce
- Dip: >= 15% drop and >= 1.5 SOL outside sell in reserves 8.0 – 18.0 SOL
- Bounce confirmation: within 2 slots of dip, >= 2 buy groups, >= 2 distinct buyers
- **Calibrated Community Depth Filter:** `self.qualified_outside_buyers.len() >= 35`
- Reserves remain 8.0 – 18.0 SOL

### S4: Upper ATH Breakout
- Reserves: 16.0 – 22.0 SOL
- Price: new ATH (`s >= peak_spot`)
- **Calibrated Buyer Breadth Filter:** `self.qualified_outside_buyers.len() >= 35` (raised from 22 to filter out sybil rugs)
- Outside buy >= 0.95 SOL in signal transaction

### S5: Pre-Graduation AMM Carryover
- Cross 72.0 SOL from below
- Holder count: >= 100 observed holders
- 5-slot outside net flow: > 0
- **Calibrated Graduation Velocity Filter:** `self.unique_non_dev_buyers.len() >= 50` (ensures high velocity into 84.85 SOL graduation)

---

## Exact Calibrated Exit Rules (`src/bot/curve_detector.rs`)

### S1 Exit
- Stop Loss: `roi <= -0.10 || below_trough`
- Profit Tranche 1: 40% tokens at +25%
- Trailing Stop: 15 percentage-point trail from peak on remainder

### S2 Exit
- Reserve Invalidation: `!migrated && reserve <= 9.8 SOL`
- Breakeven Ratchet: arm at `+10%`, exit at `roi <= 0.00`
- Profit Tranche 1: 40% tokens at `+30%`
- Trailing Stop: 15 percentage-point trail on remainder

### S3 Exit
- **Calibrated Stop Loss:** `elapsed_secs >= 18 && roi <= -0.18` (18s grace period prevents premature friction stop-outs)
- Dynamic Trailing Ratchet: arm at `+20%` peak with 10 percentage-point trail
- Primary Timeout: 60s

### S4 Exit
- Profit Tranche 1: 50% tokens at `+20%`
- Trailing Stop: 6% relative trail on remainder (`(1.0 + roi) <= (1.0 + peak_roi) * 0.94`)
- Catastrophic Stop: `roi <= -0.22`
- **Calibrated Rejection Stop:** `current_slot >= e_slot + 12 && roi <= -0.14 && self.peak_executable_roi < 0.10` (only triggers if initial breakout failed to pump)

### S5 Exit
- Pre-Graduation Invalidation: `!migrated && reserve <= 60.0 SOL`
- Post-Graduation AMM Exit:
  - 50% tokens at authenticated AMM opening
  - 8% relative trail on remainder
  - 30s post-AMM timeout
