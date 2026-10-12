import urllib.request
import json
import time
import os

RPC = "https://mainnet.helius-rpc.com/?api-key=1ce358dd-cb6b-4354-9073-2147d7f35d58"

wallets = [
    {"addr": "C4JRuZx3nAFGqJ8ZcYuwWhRGxL4N9ZwpsErjfhGqxxAf", "name": "broke bot lol"},
    {"addr": "97jv9pjCf5D7VUZEyj6XnXBC5JF23Vsagc3bvSF6GRmL", "name": "Cbot7"},
    {"addr": "nya666pQkP3PzWxi7JngU3rRMHuc7zbLK8c8wxQ4qpT", "name": "russianbot"},
    {"addr": "85YwZaQa8SATizDxCwZ8z5EpdpLvy5Ub9zp1a3TkaHrL", "name": "snipebot"},
    {"addr": "niggerd597QYedtvjQDVHZTCCGyJrwHNm2i49dkm5zS", "name": "nbot"},
    {"addr": "AURAEDwoBtWnqkzUfGQ2CVF53BFU5NoTCt5MeL4C1wPu", "name": "bot12"},
    {"addr": "4BHBSZA96XCaepYLvmteV6wLqKTqJPyfkME941X5PqHP", "name": "bot"},
    {"addr": "8TPkrBcRayR3EJzaxXb87XGmJs9k1U8tdc7wX3GJgw1z", "name": "1 sol bot"},
    {"addr": "4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3", "name": "Snippebot"},
    {"addr": "8dtx2tr4TuJsYpri2suggFu1pg3DVjFLBBVmhtDy1MEF", "name": "Bottom Bidder"},
    {"addr": "J3gZFpvsCsmA5zwqXgUpyqNLBoGGcJzmnfRwbHFR6KfU", "name": "bottty"},
    {"addr": "bcnzSs3F6F3MG7utvEQHpd8A53nRBM8ZM4TfEs2Zmcp", "name": "bottimus"},
    {"addr": "EaaCfVxVboPx1wht6Xvqcmq6LVhDW5ouyCBMiu2tafBG", "name": "asdasd"},
    {"addr": "7ovu7sqYQGcHwUnLfVfwjCx5VGBCiJmBrsrBv2ab1Ltx", "name": "bot"},
    {"addr": "BuekUk3YMmm7Agnb4ni1qMCmShVpeBTdQZYNyihyzr7u", "name": "insane bot"},
    {"addr": "5DC3tMyFSXeujJn9KWnh1MkM8QCgXXm2tDEGpjhcwFck", "name": "bot"},
    {"addr": "Fhbh1DTUDKt6qu9zVg8Q5VgnZa1WWWbxBxG6pCoJoggA", "name": "boooooot"},
    {"addr": "9QbcuwBLEDXKgJLx6rJKMnYfeXmTovBPzUmkAu9s4a19", "name": "cbot14"},
    {"addr": "2gnL2LdN2mSyk6Y7oBrNinZoEi11F2SdhiHCYF1R3vGY", "name": "Botty"},
    {"addr": "72MUPELEkUU5riN8ZPdfVssXWC6L8EViZ9FybHEmqT6J", "name": "1sol bot"},
    {"addr": "haqqiUUXB5gp7gDbSjpEkw3phAjQb25r86uXJsZQgWq", "name": "bot"},
    {"addr": "94iQuYjVgTwGXxtM7ywfpzfLvx3gN4oQRuc9osRE2pEm", "name": "Bot"}
]

def rpc_call(method, params):
    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode("utf-8")
    req = urllib.request.Request(RPC, headers={"Content-Type": "application/json"}, data=payload)
    resp = urllib.request.urlopen(req)
    return json.loads(resp.read().decode("utf-8")).get("result")

def rpc_batch(calls):
    batch = []
    for i, (method, params) in enumerate(calls):
        batch.append({"jsonrpc": "2.0", "id": i, "method": method, "params": params})
    payload = json.dumps(batch).encode("utf-8")
    req = urllib.request.Request(RPC, headers={"Content-Type": "application/json"}, data=payload)
    resp = urllib.request.urlopen(req)
    data = json.loads(resp.read().decode("utf-8"))
    data.sort(key=lambda x: x["id"])
    return [d.get("result") for d in data]

print("1. Fetching SOL Balances for all 22 wallets...")
bal_calls = [("getBalance", [w["addr"]]) for w in wallets]
bal_results = rpc_batch(bal_calls)
for w, r in zip(wallets, bal_results):
    w["balance"] = (r.get("value", 0) / 1e9) if r else 0.0

print(f"{'NAME':15} | {'ADDRESS':44} | {'SOL BALANCE':>12}")
print("-" * 78)
for w in wallets:
    print(f"{w['name']:15} | {w['addr']:44} | {w['balance']:10.2f} SOL")
