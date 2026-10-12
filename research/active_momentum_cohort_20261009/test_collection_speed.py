"""Offline regressions for the shortened collector path; no strategy replay or RPC."""
import sys
sys.dont_write_bytecode=True

import base64
import gzip
import hashlib
import json
import pathlib
import tempfile
import unittest
from unittest import mock

import collect_cohort as C


def b58encode(raw):
    alphabet="123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    n=int.from_bytes(raw,"big");out=""
    while n:
        n,rem=divmod(n,58);out=alphabet[rem]+out
    return "1"*(len(raw)-len(raw.lstrip(b"\0")))+(out or "")


def trade_tx(index,mint,curve,reserve,*,bound_curve=True,failed=False):
    discriminator=hashlib.sha256(b"global:buy").digest()[:8]
    data=b58encode(discriminator+(1).to_bytes(8,"little")+(1).to_bytes(8,"little"))
    accounts=[curve if bound_curve else "wrong-bonding-curve",mint]
    return {
        "transaction":{"signatures":[f"trade-{index}"],"message":{"instructions":[
            {"programId":C.D.PUMP,"data":data,"accounts":accounts}]}},
        "meta":{"err":{"failed":True} if failed else None,"innerInstructions":[]},
        "slot":index,"transactionIndex":index,"blockTime":index,
        "_events":[dict(mint=mint,quote_is_sol=True,buy=True,rsol_raw=reserve)],
    }


def raw_tx(signature,block_time,slot):
    return {"transaction":{"signatures":[signature],"message":{"instructions":[]}},
            "meta":{"err":None,"innerInstructions":[]},"slot":slot,
            "transactionIndex":slot,"blockTime":block_time}


class CollectionSpeedTests(unittest.TestCase):
    def test_long_pool_cache_trims_to_240_without_rpc_and_preserves_source(self):
        mint="pool-mint";migration_time=1000
        migration={"mint":mint,"pool":"pool","bonding_curve":"curve",
                   "signature":"migration-sig","slot":1,"index":0,"time":migration_time}
        txs=[raw_tx("migration-sig",migration_time,1),raw_tx("pool-120",1120,2),
             raw_tx("pool-240",1240,3),raw_tx("pool-3600",4600,4)]
        pool={"mint":mint,"migration":migration,
              "coverage":{"lower_time":migration_time,"upper_time":4600,
                          "exhausted":True,"receipts":len(txs)},"transactions":txs}
        with tempfile.TemporaryDirectory() as temp:
            root=pathlib.Path(temp)/"collector";outside=pathlib.Path(temp)/"source.json.gz"
            path=root/"raw_pools"/(mint+".json.gz");root.mkdir()
            C.R.save(outside,pool);original=outside.read_bytes();path.parent.mkdir()
            path.symlink_to(outside)
            with mock.patch.object(C,"P",root),mock.patch.object(C,"history",side_effect=AssertionError("RPC history")),\
                 mock.patch.object(C.R,"rpc",side_effect=AssertionError("RPC")):
                retained=C.retain_pool_horizon(path,mint,migration)
            self.assertEqual(outside.read_bytes(),original)
            self.assertFalse(path.is_symlink())
            self.assertEqual([C.sig(z) for z in retained["transactions"]],
                             ["migration-sig","pool-120","pool-240"])
            coverage=retained["coverage"]
            self.assertEqual(coverage["upper_time"],migration_time+240)
            self.assertEqual(coverage["retained_through_time"],migration_time+240)
            self.assertEqual(coverage["receipts"],3)
            self.assertEqual(coverage["source_receipts"],4)
            self.assertEqual(coverage["source_upper_time"],4600)
            derivation=retained["coverage_superset_derivation"]
            self.assertEqual(derivation["retained_receipts"],3)
            archived=root/derivation["source_archive"]
            self.assertEqual(archived.read_bytes(),original)

    def test_one_hour_cached_audit_is_reused_and_keeps_its_bound_proof(self):
        mint="audited-mint";creation_time=C.START+10;migration_time=C.START+1000
        curve="curve-key";pool_address="pool-key"
        creation={"mint":mint,"bonding_curve":curve,"user":"creator",
                  "virtual_sol_reserves":30_000_000_000,"virtual_token_reserves":1_000_000,
                  "real_token_reserves":500_000}
        migration={"mint":mint,"pool":pool_address,"bonding_curve":curve,
                   "signature":"migration-sig","slot":20,"index":0,"time":migration_time}
        creation_tx=raw_tx("creation-sig",creation_time,10)
        migration_tx=raw_tx("migration-sig",migration_time,20)
        later_curve_tx=raw_tx("curve-later",migration_time+300,21)
        raw={"mint":mint,"creation_metadata":creation,"creation_signature":"creation-sig",
             "creation_time":creation_time,"requested_end_time":migration_time+3600,
             "migration":migration,"custody_extensions":[],
             "coverage":{"exhausted":True,"lower_time":creation_time,
                         "upper_time":migration_time+3600,"receipts":3},
             "transactions":[creation_tx,migration_tx,later_curve_tx]}
        bound={"mint":mint,"inventory_key":"token_account","creation_metadata":creation,
               "parity":{"error":None},"groups":[{"source_status":"succeeded"}],
               "block_order_verification":{"checked_slots":2}}
        audit={"mint":mint,"verifier_version":C.VERIFIER_VERSION,"status":"verified",
               "creation_time":creation_time,"creation_signature":"creation-sig",
               "migration_status":True,"migration":migration,"source_groups_checked":1,
               "verified_block_slots":2}
        pool_txs=[migration_tx,raw_tx("pool-240",migration_time+240,22),
                  raw_tx("pool-hour",migration_time+3600,23)]
        pool={"mint":mint,"migration":migration,
              "coverage":{"lower_time":migration_time,"upper_time":migration_time+3600,
                          "exhausted":True,"receipts":3},"transactions":pool_txs}
        with tempfile.TemporaryDirectory() as temp:
            root=pathlib.Path(temp)
            for folder in ("audits","raw_curves","bound_curve_tapes","raw_pools"):
                (root/folder).mkdir()
            C.R.save(root/"audits"/(mint+".json"),audit)
            C.R.save(root/"raw_curves"/(mint+".json.gz"),raw)
            C.R.save(root/"bound_curve_tapes"/(mint+".json.gz"),bound)
            C.R.save(root/"raw_pools"/(mint+".json.gz"),pool)
            original_pool=(root/"raw_pools"/(mint+".json.gz")).read_bytes()
            def creations(tx):return [creation] if C.sig(tx)=="creation-sig" else []
            def migrations(tx):return [migration] if C.sig(tx)=="migration-sig" else []
            proof={"error":None,"groups_checked":1,"successful_curve_trade_transactions":50,
                   "qualified_outside_buyers":25,"peak_reserve_sol":12,
                   "peak":{"creator_share":0.01,"unknown_owner_tokens_raw":0}}
            with mock.patch.object(C,"P",root),mock.patch.object(C.D,"creations",side_effect=creations),\
                 mock.patch.object(C,"decoded_migrations",side_effect=migrations),\
                 mock.patch.object(C,"parity",return_value=proof):
                reused=C.validated_cached_audit(mint)
            self.assertIsNotNone(reused)
            self.assertEqual(reused["required_post_migration_seconds"],240)
            trimmed=C.read(root/"raw_pools"/(mint+".json.gz"))
            self.assertEqual(trimmed["coverage"]["upper_time"],migration_time+240)
            self.assertEqual(len(trimmed["transactions"]),2)
            self.assertTrue((root/"archive"/"raw_pools_before_240s").is_dir())
            archive=next((root/"archive"/"raw_pools_before_240s").glob("*.json.gz"))
            self.assertEqual(archive.read_bytes(),original_pool)
            trimmed_curve=C.read(root/"raw_curves"/(mint+".json.gz"))
            self.assertEqual(trimmed_curve["requested_end_time"],migration_time+240)
            self.assertNotIn("curve-later",{C.sig(z) for z in trimmed_curve["transactions"]})

    def test_early_reject_ignores_failed_and_unrelated_amm_events(self):
        mint="curve-mint";curve="curve-key"
        txs=[trade_tx(i,mint,curve,11_000_000_000) for i in range(49)]
        txs.append(trade_tx(50,mint,curve,90_000_000_000,failed=True))
        amm=raw_tx("unrelated-amm",51,51)
        amm["_events"]=[dict(mint=mint,quote_is_sol=True,buy=True,rsol_raw=99_000_000_000)]
        txs.append(amm)
        d={"creation_metadata":{"bonding_curve":curve},"requested_end_time":1000,
           "coverage":{"exhausted":True,"upper_time":1000},"transactions":txs}
        with mock.patch.object(C.D,"events",side_effect=lambda tx:tx.get("_events",[])),\
             mock.patch.object(C,"decoded_migrations",return_value=[]):
            metrics=C.early_curve_metrics(d,mint)
            self.assertEqual(metrics["successful_curve_trade_transactions"],49)
            self.assertEqual(metrics["peak_reserve_raw"],11_000_000_000)
            self.assertEqual(C.early_curve_rejection(d,mint),
                             "fewer_than_50_successful_curve_trade_transactions")
            incomplete=dict(d,coverage={"exhausted":False,"upper_time":1000})
            self.assertIsNone(C.early_curve_rejection(incomplete,mint))

    def test_ambiguous_curve_account_binding_disables_early_reject(self):
        mint="curve-mint";curve="curve-key"
        txs=[trade_tx(i,mint,curve,11_000_000_000) for i in range(49)]
        txs.append(trade_tx(50,mint,curve,99_000_000_000,bound_curve=False))
        d={"creation_metadata":{"bonding_curve":curve},"requested_end_time":1000,
           "coverage":{"exhausted":True,"upper_time":1000},"transactions":txs}
        with mock.patch.object(C.D,"events",side_effect=lambda tx:tx.get("_events",[])),\
             mock.patch.object(C,"decoded_migrations",return_value=[]):
            self.assertIsNone(C.early_curve_metrics(d,mint))
            self.assertIsNone(C.early_curve_rejection(d,mint))

    def test_verify_rejects_dead_complete_curve_before_parity_or_rpc(self):
        mint="curve-mint";curve="curve-key";creation_time=C.START+1
        txs=[trade_tx(i,mint,curve,11_000_000_000) for i in range(49)]
        d={"mint":mint,"creation_metadata":{"mint":mint,"bonding_curve":curve,
            "user":"creator"},"requested_end_time":1000,
           "coverage":{"exhausted":True,"upper_time":1000},"migration":None,
           "transactions":txs,"custody_extensions":[]}
        candidate={"mint":mint,"creation":d["creation_metadata"],
                   "creation_time":creation_time,"source":"test"}
        with tempfile.TemporaryDirectory() as temp:
            root=pathlib.Path(temp);(root/"raw_curves").mkdir()
            C.R.save(root/"raw_curves"/(mint+".json.gz"),d)
            with mock.patch.object(C,"P",root),mock.patch.object(C.D,"events",side_effect=lambda tx:tx.get("_events",[])),\
                 mock.patch.object(C,"decoded_migrations",return_value=[]),\
                 mock.patch.object(C,"bind",side_effect=AssertionError("full bind called")),\
                 mock.patch.object(C,"parity",side_effect=AssertionError("parity called")),\
                 mock.patch.object(C,"history",side_effect=AssertionError("history RPC called")),\
                 mock.patch.object(C.R,"rpc",side_effect=AssertionError("RPC called")):
                with self.assertRaisesRegex(ValueError,"fewer_than_50_successful_curve_trade_transactions"):
                    C.verify(candidate)


if __name__=="__main__":unittest.main()
