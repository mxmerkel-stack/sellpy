#!/usr/bin/env python3
"""Temporär: Taschen vollständig erfassen?"""
import json, sys, re
from pathlib import Path
from collections import Counter
from playwright.sync_api import sync_playwright
sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_sellpy as F

out = {"ops": {}, "variants": {}}
with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    ctx = b.new_context(locale="de-DE", timezone_id="Europe/Berlin", viewport={"width": 1280, "height": 900},
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")
    page = ctx.new_page(); session = {}; cur = {"u": ""}
    def on_req(r):
        t = r.headers.get("x-parse-session-token")
        if t and not session: session.update(token=t, app=r.headers.get("x-parse-application-id"))
    def on_resp(r):
        if "graphql" not in r.url: return
        try: body = r.text(); req = r.request.post_data or ""
        except Exception: return
        m = re.search(r'"operationName":"(\w+)"', req); op = m.group(1) if m else "?"
        if re.search(r"bag|dropoff|parcel|container", body + req, re.I):
            out["ops"][cur["u"] + " :: " + op] = {"req": req[:600], "resp": body[:1800]}
    page.on("request", on_req); page.on("response", on_resp)
    F.login(page)
    for path in ["/sales", "/sales/bags", "/my-sales", "/profile"]:
        cur["u"] = path
        try: page.goto(F.BASE + path, wait_until="domcontentloaded", timeout=40000); page.wait_for_timeout(5000)
        except Exception as e: out["ops"][path] = str(e)[:80]
    s = F.Sellpy(page, session["token"], session["app"])
    uid = s.q("query { currentUser { objectId } }")["data"]["currentUser"]["objectId"]
    bags = s.pages("""query G($uid: ID!, $first: Int, $after: String) {
      bags(where: {user: {have: {objectId: {equalTo: $uid}}}}, first: $first, after: $after, order: createdAt_DESC) {
        pageInfo { hasNextPage endCursor } edges { node { objectId createdAt status region } } } }""", "bags", {"uid": uid})
    items = s.pages("""query I($uid: ID!, $first: Int, $after: String) {
      items(where: {user: {have: {objectId: {equalTo: $uid}}}}, first: $first, after: $after, order: [createdAt_DESC]) {
        pageInfo { hasNextPage endCursor } edges { node { objectId createdAt itemStatus bag { objectId } } } } }""", "items", {"uid": uid})
    ic = Counter((i.get("bag") or {}).get("objectId") for i in items)
    out["bags"] = [[b_["objectId"], b_["createdAt"][:10], b_["status"], b_.get("region"), ic.get(b_["objectId"], 0)] for b_ in bags]
    out["items_without_bag"] = ic.get(None, 0)
    out["bag_ids_in_items_not_in_bags"] = [k for k in ic if k and k not in {x["objectId"] for x in bags}]
    # Varianten
    for name, q in {
        "bags_all_first50": 'query { bags(first: 50, order: createdAt_DESC) { count edges { node { objectId createdAt status user { objectId } } } } }',
        "me_bags": 'query { currentUser { objectId bags { count } } }',
        "containerDropoffs": 'query { containerDropoffs(first: 30) { count edges { node { objectId createdAt status } } } }',
        "sellerBags": 'query { sellerBags(first: 30) { count edges { node { objectId createdAt status } } } }',
    }.items():
        try:
            r = s.q(q, allow_errors=True); out["variants"][name] = json.dumps(r)[:1500]
        except Exception as e: out["variants"][name] = "fehler " + str(e)[:80]
    b.close()
Path("data").mkdir(exist_ok=True)
Path("data/probe.json").write_text(json.dumps(out, ensure_ascii=False))
print("bags", len(out["bags"]), "ops", len(out["ops"]))
