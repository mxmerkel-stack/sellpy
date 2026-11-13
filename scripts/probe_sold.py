#!/usr/bin/env python3
"""Temporär: sucht Felder für Verkaufs-/Zahlungsdatum bei Artikeln mit Status 'såld'."""
import json, sys, re
from pathlib import Path
from playwright.sync_api import sync_playwright
sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_sellpy as F

out = {"valid": {}, "invalid": {}, "suggest": []}
CANDS = """sold soldAt soldDate dateSold saleDate orderedAt orderDate order shippedAt deliveredAt delivered paymentDate payoutDate payOutDate
paidOutAt expectedPayoutDate expectedPaymentDate creditedAt sharePaidAt shareDate sellerShare share sellerPayment payment payments
soldPrice salePrice sellingPrice price priceSold finalPrice sellerAmount sellerCredit credit commission fee adFee returnDeadline returnPeriodEnd
returnableUntil returnUntil canReturn buyer sale orderItem orderItems payout sellerPayout balanceTransactions transactions
statusChangedAt statusUpdatedAt updatedAt sellerItemStatusUpdatedAt itemStatusUpdatedAt reservedAt boughtAt purchasedAt purchaseDate
availableAt payableAt payAt approvedAt packedAt processedAt dateProcessed""".split()
with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    ctx = b.new_context(locale="de-DE", timezone_id="Europe/Berlin", viewport={"width": 1280, "height": 900},
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")
    page = ctx.new_page(); sess = {}
    def on_req(r):
        t = r.headers.get("x-parse-session-token")
        if t: sess.update(token=t, app=r.headers.get("x-parse-application-id"))
    page.on("request", on_req)
    F.login(page)
    page.goto(F.BASE + "/sales", wait_until="domcontentloaded", timeout=60000)
    for _ in range(20):
        if sess.get("token"): break
        page.wait_for_timeout(500)
    s = F.Sellpy(page, sess["token"], sess["app"])
    uid = s.q("query { currentUser { objectId } }")["data"]["currentUser"]["objectId"]
    r = s.q("""query($u:ID!){ items(where:{itemStatus:{equalTo:"såld"}, user:{have:{objectId:{equalTo:$u}}}}, first: 50){ edges { node { objectId createdAt paidAt putOnShelfAt } } } }""", {"u": uid}, allow_errors=True)
    out["sald_raw"] = r
    nodes = [e["node"] for e in ((r.get("data") or {}).get("items") or {}).get("edges", [])]
    ids = [n["objectId"] for n in nodes]; out["ids"] = ids
    if ids:
        for c in CANDS:
            for sub in ("", " { objectId }", " { amount currency }", " { edges { node { objectId } } }"):
                rr = s.q("query($i:ID!){ items(where:{objectId:{equalTo:$i}}, first:1){ edges { node { objectId %s%s } } } }" % (c, sub), {"i": ids[0]}, allow_errors=True)
                errs = rr.get("errors")
                if not errs:
                    node = rr["data"]["items"]["edges"][0]["node"] if rr["data"]["items"]["edges"] else None
                    out["valid"][c + sub] = node.get(c) if node else None
                    break
                msg = errs[0].get("message", "")
                if "Did you mean" in msg or "Cannot query field" in msg:
                    if sub == "": out["invalid"][c] = msg[:200]
                    break
    b.close()
Path("data").mkdir(exist_ok=True)
Path("data/probe.json").write_text(json.dumps(out, ensure_ascii=False))
print("valid:", list(out["valid"]))
