"""Download and stitch post-migration AMM pool histories for all 8 S5 mints."""
import json
import gzip
import pathlib
import sys
import time

ROOT = pathlib.Path.cwd()
sys.path.insert(0, str(ROOT / "research/frozen_21day_validation_20261008"))
import rpc_pool as R
import run_after_collection as RAC

s5_mints = [
    "3yJsenghPtwkAoLmwL8hRDmxZrDFScj8T7FFutwBpump",
    "Ft9SNGXt29RJ5PKW2PA86ANUKSSkJi2HMcwyHP31pump",
    "BopHFrb6tzVo87d2oqawpBTJLtDYU3G6u56dYUo8pump",
    "DnjjGyuLVfQFZoQAJv2gNGcAzhyc4CdFaKHMMcWdpump",
    "4YTQ2bmCycn4vLiKWjWLe8swEFDWkxByJDE2uCWUpump",
    "CXdRBoRWmWWeUDHkFgmH6D566sFFccaTsrgCGaGSpump",
    "2VVBKWfWTpAwdkDFLCz5SsAeZDxFrzmsKHvchLc5pump",
    "87QtDtqHj1uatfmuwF7oBcmMaUfFpAUE7NNrpbkWpump",
]

def main():
    print("Starting AMM continuation download and stitch for 8 S5 mints...", flush=True)
    results = []
    for idx, mint in enumerate(s5_mints, 1):
        t0 = time.time()
        dest = R.OUT / "execution_tapes" / (mint + ".json.gz")
        if dest.exists():
            tape = json.load(gzip.open(dest, "rt"))
            venues = {g.get("venue") for g in tape["groups"]}
            print(f"[{idx}/8] Mint {mint[:12]}... already on disk! Groups: {len(tape['groups'])}, Venues: {venues}", flush=True)
            results.append({"mint": mint, "groups": len(tape["groups"]), "venues": list(venues), "status": "existing"})
            continue
        
        signals = json.load(open(R.OUT / "signals_by_mint" / (mint + ".json")))
        print(f"[{idx}/8] Mint {mint[:12]}...: fetching pool transactions from RPC...", flush=True)
        try:
            tape = RAC.continuation(mint, signals)
            venues = {g.get("venue") for g in tape["groups"]}
            dt = time.time() - t0
            print(f"[{idx}/8] SUCCESS: Mint {mint[:12]}... done in {dt:.1f}s. Groups: {len(tape['groups'])}, Venues: {venues}", flush=True)
            results.append({"mint": mint, "groups": len(tape["groups"]), "venues": list(venues), "status": "downloaded"})
        except Exception as e:
            print(f"[{idx}/8] ERROR for Mint {mint[:12]}...: {e}", flush=True)
            results.append({"mint": mint, "error": str(e), "status": "error"})

    print("\nDownload summary:", json.dumps(results, indent=2))

if __name__ == "__main__":
    main()
