"""Offline checks for read-only source priority and no early-window refetch."""
import sys
sys.dont_write_bytecode = True
import pathlib
import tempfile
import unittest
from unittest import mock
import collect_cohort as C
import parallel_collect as Q
import local_active_seed as L
import reseed_local_queue as S


class LocalIntegrationTests(unittest.TestCase):
    def test_local_rows_win_and_early_uncached_rows_are_omitted(self):
        local = [{'mint': 'same', 'local_raw_path': '/read-only/source', 'creation_time': C.START}]
        existing = [{'mint': 'same', 'time': C.START}, {'mint': 'early', 'time': C.START},
                    {'mint': 'later', 'time': S.LOCAL_ONLY_END}]
        queue, exclusions = S.build_revision(existing, local)
        self.assertEqual([x['mint'] for x in queue], ['same', 'later'])
        self.assertEqual(queue[0]['local_raw_path'], '/read-only/source')
        self.assertEqual(len(exclusions), 2)

    def test_missing_early_source_never_refetches_curve(self):
        row = dict(mint='testmint', creation={'bonding_curve': 'curve'}, creation_time=C.START, source='test')
        with tempfile.TemporaryDirectory() as temp, mock.patch.object(C, 'P', pathlib.Path(temp)), \
             mock.patch.object(C, 'history', side_effect=AssertionError('unexpected history request')):
            with self.assertRaisesRegex(ValueError, 'local_source_not_eligible:early_window'):
                C.verify(row)

    def test_local_source_miss_is_final_source_exclusion_not_retry_blocker(self):
        row = dict(mint='testmint', creation={'bonding_curve': 'curve'}, creation_time=C.START,
                   source=L.SOURCE, local_raw_path='/read-only/source')
        with tempfile.TemporaryDirectory() as temp, mock.patch.object(C, 'P', pathlib.Path(temp)), \
             mock.patch.object(L, 'import_source', side_effect=L.LocalSourceCoverageError('incomplete_local_curve_history')), \
             mock.patch.object(C, 'history', side_effect=AssertionError('unexpected history request')):
            with self.assertRaises(ValueError) as ctx:
                C.verify(row)
        self.assertEqual(Q.classify_failure(str(ctx.exception), 'ValueError'), 'rejected')


if __name__ == '__main__':
    unittest.main()
