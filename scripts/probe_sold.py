#!/usr/bin/env python3
"""Temporär: reservierte Buchungen (noch nicht abgerechnete Verkäufe)?"""
import json, sys
from pathlib import Path
from playwright.sync_api import sync_playwright
sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_sellpy as F

out = {}
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
    def run(name, q, v=None):
        r = s.q(q, v, allow_errors=True); out[name] = json.dumps(r, ensure_ascii=False)[:3500]
    run("reserved_all", "query($u:ID!){ reservedBalanceTransactions(where:{user:{have:{objectId:{equalTo:$u}}}}, first: 40, order: createdAt_DESC){ count edges{ node{ objectId type createdAt settledAt delta item{objectId} sale{objectId} } } } }", {"u": uid})
    run("reserved_unsettled", "query($u:ID!){ reservedBalanceTransactions(where:{user:{have:{objectId:{equalTo:$u}}}, settledAt:{exists:false}}, first: 40){ count edges{ node{ objectId type createdAt settledAt delta item{objectId} sale{objectId} } } } }", {"u": uid})
    run("reserved_bogus", "query($u:ID!){ reservedBalanceTransactions(where:{user:{have:{objectId:{equalTo:$u}}}}, first: 1){ edges{ node{ objectId settleAt expectedAt payableAt releaseAt dueDate availableAt } } } }", {"u": uid})
    run("bag_balance", "query{ bags(where:{status:{equalTo:2}}, first:3){ edges{ node{ objectId balance{ customerShare{amount} listingFees{amount} availableShare{amount} pendingShare{amount} reservedShare{amount} } } } } }")
    b.close()
Path("data").mkdir(exist_ok=True)
Path("data/probe.json").write_text(json.dumps(out, ensure_ascii=False))
print("ok")
