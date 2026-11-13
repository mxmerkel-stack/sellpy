#!/usr/bin/env python3
"""Temporär: Zahlungsziel ('spätestens am …') verkaufter Artikel finden."""
import json, sys
from pathlib import Path
from playwright.sync_api import sync_playwright
sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_sellpy as F

CANDS = """paymentDueDate paymentDeadline paymentDue buyerPaymentDeadline expectedShareDate shareDate latestShareDate willBeCreditedAt autoCompleteAt completeAt
completedAt finishedAt settleAt deadline dueAt dueDate expiresAt expireAt validUntil lastPaymentDate payBy payUntil shareDeadline
latestPaymentDate expectedPaymentDate paymentExpected awaitingPayment awaitingPaymentUntil reservedUntil soldAt soldDate saleCompletedAt
sellerShareDate shareAvailableAt shareCreditedAt creditDate creditAt payoutAt itemSale sale saleInfo saleStatus shareStatus sellerShare
orderItem orderItems buyerOrder lineItem lineItems itemPayment itemPayments orderPayment latestShareAt""".split()
out = {"valid": {}, "bad": {}, "raw": {}}
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
    r = s.q("""query($u:ID!){ items(where:{itemStatus:{equalTo:"såld"}, user:{have:{objectId:{equalTo:$u}}}}, first: 50){ edges { node { objectId createdAt updatedAt paidAt putOnShelfAt bag { objectId } localizedMetadata(locale:"de") } } } }""", {"u": uid}, allow_errors=True)
    nodes = [e["node"] for e in r["data"]["items"]["edges"]]
    out["sold"] = [{k: v for k, v in n.items() if k != "localizedMetadata"} | {"brand": (n.get("localizedMetadata") or {}).get("brand"), "type": (n.get("localizedMetadata") or {}).get("type")} for n in nodes]
    i0 = nodes[0]["objectId"]
    for c in CANDS:
        for sub in ("", " { objectId }", " { edges { node { objectId } } }"):
            rr = s.q("query($i:ID!){ items(where:{objectId:{equalTo:$i}}, first:1){ edges { node { objectId %s%s } } } }" % (c, sub), {"i": i0}, allow_errors=True)
            e = rr.get("errors")
            if not e:
                out["valid"][c + sub] = json.dumps(rr["data"]["items"]["edges"][0]["node"].get(c) if rr["data"]["items"]["edges"] else None)[:300]; break
            m = e[0].get("message", "")
            if "Cannot query field" in m and sub == "":
                if "Did you mean" in m: out["bad"][c] = m[m.index("Did you mean"):][:120]
                break
    # alle Abfragen der Verkaufsübersicht-Seiten pro Artikel mitschneiden
    b.close()
Path("data").mkdir(exist_ok=True)
Path("data/probe.json").write_text(json.dumps(out, ensure_ascii=False))
print("valid:", list(out["valid"]))
