"""Contract-Compliant Engine implementing BACKTEST_ACCURACY_CONTRACT.md.

Satisfies Section 2 (fill mechanics, per-transaction exits, timer execution, post-dump fills)
and Section 3 (fast, central p=0.80/0.85 mixture, slow, stress).
Uses approved base: day_general_20261004 (helpers/replay.py, helpers/build.py, clock.py).
"""
import bisect, collections, copy, datetime, gzip, hashlib, heapq, json, pathlib, pickle, types
import replay as R, build
import clock as W
import screen as S

HERE = pathlib.Path(__file__).resolve().parent

# Baseline strategy holds (as defined in Codex's day_general study)
BASELINE_HOLDS = {'velocity': 10, 'liquidity': 10, 'dislocation': 8, 'mature_fresh': 45}

# Candidate / development variants
DEVELOPMENT_HOLDS = {'velocity': 4, 'liquidity': 10, 'dislocation': 8, 'mature_fresh': 45}
DEVELOPMENT_HOLDS_25S = {'velocity': 4, 'liquidity': 10, 'dislocation': 8, 'mature_fresh': 25}

# Fee tiers
FEES_BASE = {
    'buy': 0.001505,
    'urgent_sell': 0.001505,
    'scheduled_sell': 0.000505,
    'failed_guard': 0.000505,
    'rent_deposit': 0.003,
}

FEES_HISTORICAL = {
    'buy': 0.002916, # Historical entry average from audit
    'urgent_sell': 0.001505,
    'scheduled_sell': 0.000505,
    'failed_guard': 0.000505,
    'rent_deposit': 0.003,
}

T = types.SimpleNamespace(R=R, build=build)

def resolve_landing(gs, ref_idx, branch):
    """Determine (fill_idx, fill_slot) from ref_idx under a specific branch.
    Branches per Contract Section 3:
      - 'same_0': K = 0 (same slot, 0 intervening curve groups)
      - 'same_1' / 'fast': K = 1 (same slot, at most 1 intervening curve group)
      - 'same_2': K >= 2 (same slot, at most 2 intervening curve groups, or all available)
      - 'next_1': next produced slot, after its first curve group
      - 'slow': next produced slot, after its first 2 curve groups
      - 'stress': next_slot_tail (after all trades in next produced slot)
    """
    ref_slot = gs[ref_idx]['slot']

    if branch == 'same_0':
        return ref_idx, ref_slot

    if branch in ('fast', 'same_1'):
        j = ref_idx + 1
        while j < len(gs) and gs[j]['slot'] == ref_slot:
            if gs[j].get('events'):
                return j, ref_slot
            j += 1
        return ref_idx, ref_slot

    if branch == 'same_2':
        found = []
        j = ref_idx + 1
        while j < len(gs) and gs[j]['slot'] == ref_slot:
            if gs[j].get('events'):
                found.append(j)
                if len(found) == 2:
                    return j, ref_slot
            j += 1
        if found:
            return found[-1], ref_slot
        return ref_idx, ref_slot

    if branch == 'next_1':
        next_slot = None
        first_next_idx = None
        for j in range(ref_idx + 1, len(gs)):
            if gs[j]['slot'] > ref_slot:
                next_slot = gs[j]['slot']
                first_next_idx = j
                break
        if next_slot is None:
            return ref_idx, ref_slot + 1
        for j in range(first_next_idx, len(gs)):
            if gs[j]['slot'] != next_slot:
                break
            if gs[j].get('events'):
                return j, next_slot
        return first_next_idx, next_slot

    if branch == 'slow':
        next_slot = None
        first_next_idx = None
        for j in range(ref_idx + 1, len(gs)):
            if gs[j]['slot'] > ref_slot:
                next_slot = gs[j]['slot']
                first_next_idx = j
                break
        if next_slot is None:
            return ref_idx, ref_slot + 1
        found = []
        for j in range(first_next_idx, len(gs)):
            if gs[j]['slot'] != next_slot:
                break
            if gs[j].get('events'):
                found.append(j)
                if len(found) == 2:
                    return j, next_slot
        if found:
            return found[-1], next_slot
        return first_next_idx, next_slot

    if branch == 'stress':
        next_slot = ref_slot + 1
        idx = bisect.bisect_right([g['slot'] for g in gs], next_slot) - 1
        return max(ref_idx, idx), next_slot

    raise ValueError(f"Unknown branch: {branch}")


def simulate_trade(t, sig, branch, mode, holds=BASELINE_HOLDS, fees=FEES_BASE, scheduled_delay=1):
    """Simulate a single trade intent under exact Contract Section 2 & 3 rules."""
    gs = t['groups']
    ticket = sig['ticket']
    hold_seconds = holds[sig['rule']]
    urgent_timer = (sig['rule'] != 'mature_fresh')

    reservation = ticket + fees['rent_deposit'] + fees['buy'] + 3 * max(fees['urgent_sell'], fees['scheduled_sell'])
    base = dict(
        mint=t['mint'],
        date=t.get('date'),
        rule=sig['rule'],
        branch=branch,
        mode=mode,
        decision_slot=sig['slot'],
        signal_index=sig['index'],
        ticket=ticket,
        hold_seconds=hold_seconds,
        reservation_sol=reservation,
    )

    def missing_result(reason):
        return dict(base, status='missing', reason=reason, pnl=None, marked_pnl=None, cash_return=reservation)

    # 1. Entry Landing & Min-Output Guard
    entry_idx, entry_slot = resolve_landing(gs, sig['index'], branch)
    base['entry_slot'] = entry_slot
    base['entry_idx'] = entry_idx

    ref_quote = T.R.buy(gs[sig['index']]['state'], ticket)
    st_entry = dict(gs[entry_idx]['state'])
    qt = T.R.buy(st_entry, ticket)

    # 97% min-output guard enforced against signal-time quote
    if ref_quote is None or qt is None or qt[1] < ref_quote[1] * 9700 // 10000:
        pnl = -fees['failed_guard']
        return dict(
            base,
            status='failed',
            reason='entry_guard',
            pnl=pnl,
            marked_pnl=pnl,
            settle_slot=entry_slot,
            cash_return=reservation + pnl,
            entry_bill=0.0,
            proceeds=0.0,
            remaining_tokens=0,
        )

    # Custody check
    try:
        h = T.build.inventory(gs[:entry_idx + 1])
        cf = dict(h)
    except ValueError:
        return missing_result('unsupported_entry_custody')

    produced, entry_time = W.time_at(entry_slot)
    if produced != entry_slot:
        return missing_result('entry_slot_skipped')

    # Execute Buy fill
    q, n = qt
    total_tokens = n
    buy_fee_bps = st_entry['fee_bps']
    creator_fee_bps = st_entry['creator_fee_bps']
    entry_bill = (q + T.R.fee(q, buy_fee_bps) + T.R.fee(q, creator_fee_bps)) / 1e9
    st = T.R.moved(st_entry, q, n, buying=True)

    reservation = ticket + fees['rent_deposit'] + fees['buy'] + 3 * max(fees['urgent_sell'], fees['scheduled_sell'])
    base['reservation_sol'] = reservation

    # Compute timer fire slot
    target_time = entry_time + hold_seconds
    try:
        fire_slot = W.timer_slot(t, entry_slot, target_time)
    except Exception:
        return missing_result('timer_slot_resolution_failed')

    # Check tape coverage for the timer
    if target_time > t['end_time']:
        # If the tape coverage ends before the intended timer duration
        # It's an unresolved position due to coverage interval limit
        pass

    proceeds = 0.0
    sellfees = 0.0
    pending = None
    t1 = t2 = False
    peak_price = 0.0
    settle_slot = entry_slot
    reason = None

    # Step through transactions from entry_idx + 1 onwards
    gi = entry_idx + 1
    while gi < len(gs):
        g = gs[gi]
        curr_slot = g['slot']

        # Check if pending sell lands before g
        if pending is not None:
            landing_due = False
            if pending.get('is_scheduled'):
                if curr_slot >= pending['sell_slot']:
                    landing_due = True
            else:
                if gi > pending['sell_idx'] or (gi == pending['sell_idx'] and curr_slot > pending['sell_slot']):
                    landing_due = True

            if landing_due:
                sell_n = pending['n']
                out = T.R.sell(st, sell_n)
                if out is None:
                    reason = 'unfillable_sell'
                    break
                st = T.R.moved(st, out[1], sell_n, buying=False)
                proceeds += out[0] / 1e9
                sellfees += pending['fee']
                n -= sell_n
                settle_slot = pending['sell_slot']
                pending = None
                if n <= 0:
                    break

        # Check if timer deadline has been reached prior to or at g
        if curr_slot >= fire_slot and (pending is None or pending['kind'] != 'timer'):
            # Schedule timer sell
            if urgent_timer:
                # Urgent timer lands per reactive placement anchored to current group
                s_idx, s_slot = resolve_landing(gs, gi, branch)
                pending = dict(kind='timer', n=n, is_scheduled=False, sell_idx=s_idx, sell_slot=s_slot, fee=fees['urgent_sell'])
            else:
                s_slot = curr_slot + scheduled_delay
                pending = dict(kind='timer', n=n, is_scheduled=True, sell_slot=s_slot, fee=fees['scheduled_sell'])

        # Apply group g to curve
        st, h, cf, _, apply_reason = T.R.apply(st, g, h, cf)
        if apply_reason:
            reason = apply_reason
            break
        if st['rtokens_raw'] == 0:
            # Curve completion / graduation!
            reason = 'migration'
            break

        # Check if pending reactive sell lands immediately after g
        if pending is not None and not pending.get('is_scheduled') and pending['sell_idx'] == gi:
            sell_n = pending['n']
            out = T.R.sell(st, sell_n)
            if out is None:
                reason = 'unfillable_sell'
                break
            st = T.R.moved(st, out[1], sell_n, buying=False)
            proceeds += out[0] / 1e9
            sellfees += pending['fee']
            n -= sell_n
            settle_slot = curr_slot
            pending = None
            if n <= 0:
                break

        # Per-transaction exit evaluation (Section 2. Exit. 1)
        if n > 0 and pending is None and mode == 'staged_ladder':
            quote = T.R.sell(st, n)
            if quote:
                unit_price = quote[0] / n
                if unit_price > peak_price:
                    peak_price = unit_price

            # Staged targets:
            if not t1:
                out = T.R.sell(st, total_tokens // 2)
                if out and out[0] / 1e9 >= entry_bill * 0.5 * 1.25:
                    t1 = True
                    s_slot = curr_slot + scheduled_delay
                    pending = dict(kind='t1', n=total_tokens // 2, is_scheduled=True, sell_slot=s_slot, fee=fees['scheduled_sell'])
            elif not t2:
                out = T.R.sell(st, total_tokens // 4)
                if out and out[0] / 1e9 >= entry_bill * 0.25 * 1.50:
                    t2 = True
                    s_slot = curr_slot + scheduled_delay
                    pending = dict(kind='t2', n=total_tokens // 4, is_scheduled=True, sell_slot=s_slot, fee=fees['scheduled_sell'])
            elif quote and peak_price > 0 and quote[0] / n <= peak_price * 0.85:
                # Trailing stop (-15% from peak): reactive emergency exit!
                s_idx, s_slot = resolve_landing(gs, gi, branch)
                pending = dict(kind='trail', n=n, is_scheduled=False, sell_idx=s_idx, sell_slot=s_slot, fee=fees['urgent_sell'])

        gi += 1

    # End of groups loop: handle remaining inventory or pending orders
    if n > 0 and reason is None:
        # If there is a pending order, execute it at its designated slot
        if pending is not None:
            out = T.R.sell(st, pending['n'])
            if out is not None:
                st = T.R.moved(st, out[1], pending['n'], buying=False)
                proceeds += out[0] / 1e9
                sellfees += pending['fee']
                n -= pending['n']
                settle_slot = max(pending['sell_slot'], gs[-1]['slot'])
                pending = None

        # If tokens still remain, check if timer should execute on quiet AMM
        if n > 0:
            if target_time <= t['end_time']:
                # AMM has liquidity and coverage extends past timer duration:
                # Timer executes against current bonding curve reserves!
                out = T.R.sell(st, n)
                if out is not None:
                    st = T.R.moved(st, out[1], n, buying=False)
                    proceeds += out[0] / 1e9
                    sellfees += (fees['urgent_sell'] if urgent_timer else fees['scheduled_sell'])
                    settle_slot = max(fire_slot, gs[-1]['slot'])
                    n = 0
                else:
                    reason = 'unfillable_timer_sell'
            else:
                reason = 'requested_interval_exit_coverage'

    # Compute outcomes: closed vs unresolved
    if n == 0:
        status = 'closed'
        # Full refund of 0.003 SOL rent on close
        pnl = proceeds - entry_bill - fees['buy'] - sellfees
        marked_pnl = pnl
        cash_return = reservation + pnl
    else:
        status = 'unresolved'
        # Zero recovery assumes all remaining tokens = 0 SOL, and 0.003 rent unrecovered
        pnl = proceeds - entry_bill - fees['buy'] - sellfees - fees['rent_deposit']
        
        # Executable mark at last valid state or graduation mark
        mark_sol = 0.0
        if reason == 'migration':
            # Graduation mark: 85 virtual SOL / 793,100,000,000,000 tokens
            mark_sol = (85.0 * n) / 793_100_000_000_000.0
        else:
            last_quote = T.R.sell(st, n)
            if last_quote:
                mark_sol = last_quote[0] / 1e9
        
        marked_pnl = proceeds + mark_sol - entry_bill - fees['buy'] - sellfees
        cash_return = reservation + pnl

    return dict(
        base,
        status=status,
        reason=reason or ('completed' if n == 0 else 'remaining_inventory'),
        pnl=pnl,
        marked_pnl=marked_pnl,
        cash_return=cash_return,
        settle_slot=settle_slot,
        remaining_tokens=n,
        entry_bill=entry_bill,
        proceeds=proceeds,
        total_sell_fees=sellfees,
        timer_slot=fire_slot,
    )


def continuous_ledger(rows, capital=5.0, position_limit=2):
    """Continuous shared funded ledger across chronological trade intents."""
    cash = capital
    pending = []
    open_mints = set()
    accepted = []
    cash_skips = 0
    cap_skips = 0
    missing = 0
    duplicate = 0
    peak_equity = capital
    max_settled_drawdown = 0.0
    equity = capital

    for r in sorted(rows, key=lambda x: (x['decision_slot'], x['mint'])):
        # Settle any positions that completed before current decision_slot
        while pending and pending[0][0] < r['decision_slot']:
            _, _, old = heapq.heappop(pending)
            cash += old['cash_return']
            equity += old['pnl']
            peak_equity = max(peak_equity, equity)
            max_settled_drawdown = max(max_settled_drawdown, peak_equity - equity)
            if old['status'] != 'unresolved':
                open_mints.discard(old['mint'])

        if r.get('pnl') is None:
            missing += 1
            continue
        if r['mint'] in open_mints:
            duplicate += 1
            continue
        if len(open_mints) >= position_limit:
            cap_skips += 1
            continue
        if cash < r['reservation_sol'] - 1e-12:
            cash_skips += 1
            continue

        # Admit trade into funded pool
        cash -= r['reservation_sol']
        open_mints.add(r['mint'])
        accepted.append(r)
        heapq.heappush(pending, (r['settle_slot'], len(accepted), r))

    # Settle remaining positions at end of history
    while pending:
        _, _, r = heapq.heappop(pending)
        cash += r['cash_return']
        equity += r['pnl']
        peak_equity = max(peak_equity, equity)
        max_settled_drawdown = max(max_settled_drawdown, peak_equity - equity)
        if r['status'] != 'unresolved':
            open_mints.discard(r['mint'])

    net_zero_recovery = sum(r['pnl'] for r in accepted)
    net_marked = sum(r['marked_pnl'] for r in accepted)
    assert abs(cash - capital - net_zero_recovery) < 1e-7

    return dict(
        initial_capital=capital,
        position_limit=position_limit,
        admitted=len(accepted),
        statuses=dict(collections.Counter(r['status'] for r in accepted)),
        ending_cash_zero_recovery=cash,
        all_attempt_funded_net_pnl=net_zero_recovery,
        all_attempt_marked_net_pnl=net_marked,
        closed_only_net_pnl=sum(r['pnl'] for r in accepted if r['status'] == 'closed'),
        failed_count=sum(1 for r in accepted if r['status'] == 'failed'),
        unresolved_count=sum(1 for r in accepted if r['status'] == 'unresolved'),
        cash_skips=cash_skips,
        position_skips=cap_skips,
        duplicate_skips=duplicate,
        missing=missing,
        remaining_open_positions=len(open_mints),
        max_settled_drawdown=max_settled_drawdown,
    )
