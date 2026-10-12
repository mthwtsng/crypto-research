"""Read-only receipt custody extraction; no IO, RPC or counterfactual inference.

parse_receipt(receipt, trade_events=None, mint=None) accepts an RPC envelope or
its result. Transfer authority is deliberately distinct from token-account owner.
Unknown ownership, transfers not present in receipts and original guards are NOT
inferred. Output preserves actual instruction execution ordering.
"""
PUMP = '6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P'
TOKENS = {'TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA',
          'TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb'}


def parse_receipt(receipt, trade_events=None, mint=None):
    result = receipt.get('result') if 'result' in receipt else receipt
    if not isinstance(result, dict):
        return dict(available=False, committed=False, transfers=[], trade_bindings=[],
                    accounts={}, issues=['missing_transaction_result'])
    meta = result.get('meta') or {}
    message = result.get('transaction', {}).get('message', {})
    keys = [k.get('pubkey') if isinstance(k, dict) else k for k in message.get('accountKeys', [])]
    issues, accounts = [], {}
    for side in ('preTokenBalances', 'postTokenBalances'):
        for balance in meta.get(side, []):
            if mint is not None and balance.get('mint') != mint: continue
            idx = balance.get('accountIndex')
            if not isinstance(idx, int) or isinstance(idx, bool) or not 0 <= idx < len(keys):
                issues.append('invalid_token_balance_account_index'); continue
            account = keys[idx]
            prior = accounts.get(account)
            owner, token_mint = balance.get('owner'), balance.get('mint')
            if prior and any(prior.get(k) and value and prior[k] != value
                             for k, value in [('owner', owner), ('mint', token_mint)]):
                issues.append('conflicting_pre_post_owner_or_mint:' + account)
            record = accounts.setdefault(account, dict(owner=owner, mint=token_mint))
            if not record.get('owner'): record['owner'] = owner
            if not record.get('mint'): record['mint'] = token_mint
            try: record['pre_raw' if side == 'preTokenBalances' else 'post_raw'] = int(balance['uiTokenAmount']['amount'])
            except (KeyError, TypeError, ValueError): issues.append('invalid_token_balance_amount:' + account)
    inner = {g['index']: g.get('instructions', []) for g in meta.get('innerInstructions', [])}
    ordered = []
    for top_index, instruction in enumerate(message.get('instructions', [])):
        program = instruction.get('programId')
        ordered.append((top_index, -1, instruction, program == PUMP, (top_index, -1) if program == PUMP else None, False))
        stack = {1: program}; pump_context = {1: (top_index, -1)} if program == PUMP else {}
        for inner_index, child in enumerate(inner.get(top_index, [])):
            height = child.get('stackHeight')
            uncertain_context = not isinstance(height, int) or isinstance(height, bool) or height < 2
            if uncertain_context:
                height = 2
            stack = {k: v for k, v in stack.items() if k < height}
            pump_context = {k: v for k, v in pump_context.items() if k < height}
            stack[height] = child.get('programId')
            if child.get('programId') == PUMP: pump_context[height] = (top_index, inner_index)
            context = pump_context[max(pump_context)] if pump_context else None
            ordered.append((top_index, inner_index, child, bool(pump_context), context, uncertain_context and program != PUMP))
    transfers = []
    for top, sub, instruction, under_pump, context, uncertain_context in ordered:
        if instruction.get('programId') not in TOKENS: continue
        parsed = instruction.get('parsed')
        parsed = parsed if isinstance(parsed, dict) else {}
        info = parsed.get('info')
        info = info if isinstance(info, dict) else {}
        kind = parsed.get('type')
        if kind == 'setAuthority' and info.get('authorityType') == 'accountOwner':
            if mint is None or accounts.get(info.get('account'), {}).get('mint') == mint:
                issues.append('unsupported_account_owner_change:' + str(info.get('account')))
        if kind in {'initializeAccount', 'initializeAccount2', 'initializeAccount3'}:
            if mint is not None and info.get('mint') != mint: continue
            account = info.get('account')
            if account:
                prior = accounts.setdefault(account, {})
                if prior.get('owner') and info.get('owner') and prior['owner'] != info['owner']:
                    issues.append('initialize_owner_conflict:' + account)
                prior.update(owner=info.get('owner'), mint=info.get('mint'))
            continue
        if kind not in {'transfer', 'transferChecked'}: continue
        source, destination = info.get('source'), info.get('destination')
        src, dst = accounts.get(source, {}), accounts.get(destination, {})
        token_mint = info.get('mint') or src.get('mint') or dst.get('mint')
        if mint is not None and token_mint != mint: continue
        if uncertain_context: issues.append('missing_inner_stack_context')
        try:
            value = info.get('tokenAmount', {}).get('amount', info.get('amount'))
            if isinstance(value, bool) or not (isinstance(value, int) or
                    isinstance(value, str) and value.isdigit()):
                raise ValueError('noninteger token amount')
            raw = int(value)
            if raw < 0: raise ValueError('negative token amount')
        except (TypeError, ValueError): issues.append('invalid_transfer_amount'); continue
        if not source or not destination or not token_mint:
            issues.append('missing_transfer_identity')
        if not src.get('owner') or not dst.get('owner'):
            issues.append('unknown_transfer_owner:' + str((source, destination)))
        if src.get('mint') and dst.get('mint') and src['mint'] != dst['mint']:
            issues.append('transfer_mint_conflict')
        if any(a.get('mint') and a['mint'] != token_mint for a in (src, dst)):
            issues.append('checked_transfer_mint_conflict')
        transfers.append(dict(source_account=source, destination_account=destination,
            from_owner=src.get('owner'), to_owner=dst.get('owner'), authority=info.get('authority'),
            mint=token_mint, raw=raw, order=[top, sub], top_index=top, inner_index=sub,
            under_pump=under_pump, pump_context=list(context) if context else None,
            trade_event_indices=[], program=instruction.get('programId'), kind=kind))
    bindings = []
    for event_index, event in enumerate(trade_events or []):
        wanted_mint = event.get('mint', mint)
        candidates = [t for t in transfers if not t['trade_event_indices'] and t['under_pump'] and t['mint'] == wanted_mint
                      and t['raw'] == event.get('tokens_raw')]
        if event.get('buy') is False:
            candidates = [t for t in candidates if t['authority'] == event.get('user')]
        elif len(candidates) > 1:
            owner_matches = [t for t in candidates if t['to_owner'] == event.get('user')]
            if owner_matches: candidates = owner_matches
        if len(candidates) != 1:
            issues.append('ambiguous_or_missing_trade_transfer:' + str(event_index)); continue
        transfer = candidates[0]; transfer['trade_event_indices'].append(event_index)
        owner = transfer['to_owner'] if event['buy'] else transfer['from_owner']
        bindings.append(dict(event_index=event_index, event_user=event.get('user'), buy=event['buy'],
            mint=wanted_mint, raw=transfer['raw'], inventory_owner=owner,
            trader_token_account=transfer['destination_account'] if event['buy'] else transfer['source_account'],
            authority=transfer['authority'], transfer_order=transfer['order'], pump_context=transfer['pump_context']))
    return dict(available=True, committed=meta.get('err') is None, actual_error=meta.get('err'),
                chain_fee_lamports=meta.get('fee'), slot=result.get('slot'), block_time=result.get('blockTime'),
                accounts=accounts, transfers=transfers, trade_bindings=bindings,
                issues=sorted(set(issues)), limitations='Only receipt-visible custody; no inferred intervening transfers or counterfactual guard outcomes')
