"""Test landing and placement logic under contract section 3."""
import sys, pickle, gzip, bisect
sys.path.append('research/day_general_20261004')
sys.path.append('research/day_general_20261004/helpers')
import base_engine as B
import clock as W
import screen as S

def resolve_landing(gs, ref_idx, branch):
    """Resolve (fill_idx, fill_slot) from ref_idx under a specific branch.
    Branches:
      'same_0': K=0, directly after ref_idx
      'same_1': K=1, after 1 intervening same-slot group if exists, else 0
      'same_2': K=2, after 2 intervening same-slot groups if exist, else all available same-slot
      'next_1': next produced slot, after its 1st curve group
      'fast': same as same_1
      'slow': next produced slot, after its first 2 curve groups
      'stress': next_slot_tail (after all groups in next produced slot)
    """
    ref_slot = gs[ref_idx]['slot']
    
    if branch == 'same_0':
        return ref_idx, ref_slot
        
    elif branch in ('fast', 'same_1'):
        # At most 1 intervening curve group in the same slot
        j = ref_idx + 1
        while j < len(gs) and gs[j]['slot'] == ref_slot:
            if gs[j].get('events'):
                return j, ref_slot
            j += 1
        return ref_idx, ref_slot

    elif branch == 'same_2':
        # At most 2 intervening curve groups in same slot
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

    elif branch == 'next_1':
        # Next produced slot, after its first curve group
        # Find next slot with groups
        next_slot = None
        first_next_idx = None
        for j in range(ref_idx + 1, len(gs)):
            if gs[j]['slot'] > ref_slot:
                next_slot = gs[j]['slot']
                first_next_idx = j
                break
        if next_slot is None:
            # No further groups in tape, next produced slot is ref_slot + 1
            return ref_idx, ref_slot + 1
        # In next_slot, find after its first group with events
        for j in range(first_next_idx, len(gs)):
            if gs[j]['slot'] != next_slot:
                break
            if gs[j].get('events'):
                return j, next_slot
        return first_next_idx, next_slot

    elif branch == 'slow':
        # Next produced slot, after its first 2 curve groups
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

    elif branch == 'stress':
        # Next slot tail: after all trades in next produced slot
        next_slot = ref_slot + 1
        # Find all groups up to next_slot
        idx = bisect.bisect_right([g['slot'] for g in gs], next_slot) - 1
        return max(ref_idx, idx), next_slot

    raise ValueError(f"Unknown branch: {branch}")

if __name__ == '__main__':
    tapes = pickle.load(gzip.open('research/day_general_20261004/TAPES.pkl.gz', 'rb'))
    for t in tapes[:5]:
        sigs = S.detect(t)
        if not sigs: continue
        sig = sigs[0]
        gs = t['groups']
        print(f"Mint {t['mint'][:8]} sig {sig['rule']} at idx={sig['index']} slot={sig['slot']}")
        for br in ['same_0', 'same_1', 'same_2', 'next_1', 'fast', 'slow', 'stress']:
            idx, slot = resolve_landing(gs, sig['index'], br)
            print(f"  {br:8s}: fill_idx={idx} (delta={idx - sig['index']}) fill_slot={slot} (slot_delta={slot - sig['slot']})")
