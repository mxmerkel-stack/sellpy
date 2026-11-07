#!/usr/bin/env python3
"""Einrichtung (temporär): Wo führt Sellpy Rücksendungen? Schreibt nur Anzahlen, Statuswerte und Feldnamen ins Log."""
import collections, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from playwright.sync_api import sync_playwright
import fetch_sellpy as F

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_context(locale="de-DE").new_page()
    sess = {}
    page.on("request", lambda r: sess.update(token=r.headers["x-parse-session-token"], app=r.headers.get("x-parse-application-id")) if r.headers.get("x-parse-session-token") else None)
    F.login(page)
    page.goto(F.BASE + "/orders", wait_until="domcontentloaded"); page.wait_for_timeout(5000)
    s = F.Sellpy(page, sess["token"], sess["app"])
    uid = s.q("query { currentUser { objectId } }")["data"]["currentUser"]["objectId"]
    def show(name, q, v=None):
        r = s.q(q, v or {}, allow_errors=True)
        if r.get("errors"):
            print(f"{name}: FEHLER {r['errors'][0].get('message','')[:220]}")
        else:
            print(f"{name}: ok {json.dumps(r['data'])[:0]}")
        return r
    ord_q = """query($uid: ID!){ orders(where:{user:{have:{objectId:{equalTo:$uid}}}}, first: 100){ edges{ node{ objectId status
      items{ ... on Item { objectId itemStatus } } } } } }"""
    o = s.q(ord_q, {"uid": uid})["data"]["orders"]["edges"]
    st = collections.Counter(i["itemStatus"] for e in o for i in e["node"]["items"])
    print("Status gekaufter Artikel:", dict(st))
    print("Bestellstatus:", dict(collections.Counter(e["node"]["status"] for e in o)))
    ids = [e["node"]["objectId"] for e in o]
    for name in ["itemReturns", "returns", "orderReturns", "returnRequests", "itemClaims", "returnParcels", "refunds", "orderRefunds", "itemRefunds"]:
        r = show(name, "query($ids:[ID!]){ %s(where:{order:{have:{objectId:{in:$ids}}}}, first: 500){ count edges{ node{ objectId } } } }" % name, {"ids": ids})
        if not r.get("errors"):
            print(f"  {name}: {r['data'][name]['count']} Einträge")
    r = show("returnRateForUser", "query { returnRateForUser }")
    if not r.get("errors"): print("  Rückgabequote laut Sellpy:", r["data"]["returnRateForUser"])
    r = show("lineItemTypes", "query($id: ID!){ fetchLineItemsByOrder(orderId:$id){ type amountIncludingTax{amount} discountAmount{amount} } }", {"id": ids[0]})
    tps = collections.Counter()
    for oid in ids:
        r = s.q("query($id: ID!){ fetchLineItemsByOrder(orderId:$id){ type } }", {"id": oid}, allow_errors=True)
        for li in (r.get("data") or {}).get("fetchLineItemsByOrder") or []: tps[li["type"]] += 1
    print("LineItem-Typen:", dict(tps))
    # Felder an ItemClaim / Return mit Typ-Hinweisen
    for t in ["ItemClaim", "ItemReturn", "Return", "OrderReturn", "Refund"]:
        r = s.q('query { __type(name: "%s") { fields { name } } }' % t, allow_errors=True)
        f = ((r.get("data") or {}).get("__type") or {}).get("fields")
        print(f"Typ {t}:", [x["name"] for x in f] if f else (r.get("errors") or [{}])[0].get("message", "–")[:100])
    b.close()
