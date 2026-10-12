import json
import urllib.request
import time

SHYFT_RPC = "https://rpc.shyft.to?api_key=owfc3zuSXH37YG0U"

with open("scratch/rkjc_cache/signatures.json") as f:
    sigs = json.load(f)

sigs_rev = list(reversed(sigs))
print("Total signatures:", len(sigs_rev))

# Let's inspect the first 20 signatures
def get_tx(sig):
    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "getTransaction", "params": [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}]}).encode()
    req = urllib.request.Request(SHYFT_RPC, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode()).get("result")
    except Exception as e:
        print("Error fetching", sig, e)
        return None

print("\n--- Inspecting first 10 transactions in launch slot ---")
for i, s in enumerate(sigs_rev[:10]):
    tx = get_tx(s["signature"])
    if not tx:
        continue
    slot = tx["slot"]
    signers = [acc["pubkey"] for acc in tx["transaction"]["message"]["accountKeys"] if acc.get("signer")]
    logs = tx["meta"]["logMessages"]
    # check instructions
    is_create = any("Instruction: InitializeMint" in l or "Instruction: Create" in l for l in logs)
    is_buy = any("Instruction: Buy" in l for l in logs)
    pre_sol = tx["meta"]["preBalances"][0] / 1e9
    post_sol = tx["meta"]["postBalances"][0] / 1e9
    sol_spent = pre_sol - post_sol
    print(f"Tx {i} (slot {slot}): signer={signers[0]} create={is_create} buy={is_buy} sol_spent={sol_spent:.4f} SOL")

