#!/usr/bin/env python3
"""Temporär: Detailseite einer Verkaufstasche mit verkauften, noch nicht abgerechneten Artikeln."""
import json, sys, re
from pathlib import Path
from playwright.sync_api import sync_playwright
sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_sellpy as F

out = {"calls": [], "pages": {}}
with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    ctx = b.new_context(locale="de-DE", timezone_id="Europe/Berlin", viewport={"width": 1280, "height": 900},
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")
    page = ctx.new_page(); sess = {}; cur = {"u": ""}
    def on_req(r):
        t = r.headers.get("x-parse-session-token")
        if t: sess.update(token=t, app=r.headers.get("x-parse-application-id"))
    page.on("request", on_req)
    ids = []
    def on_resp(r):
        if "graphql" not in r.url: return
        try: body = r.text(); req = r.request.post_data or ""
        except Exception: return
        m = re.search(r'"operationName":"(\w+)"', req)
        out["calls"].append({"page": cur["u"], "op": m.group(1) if m else "", "req": req[:2500], "resp": body[:2500]})
    page.on("response", on_resp)
    F.login(page)
    page.goto(F.BASE + "/sales", wait_until="domcontentloaded", timeout=60000)
    for _ in range(20):
        if sess.get("token"): break
        page.wait_for_timeout(500)
    s = F.Sellpy(page, sess["token"], sess["app"])
    uid = s.q("query { currentUser { objectId } }")["data"]["currentUser"]["objectId"]
    r = s.q("""query($u:ID!){ items(where:{itemStatus:{equalTo:"såld"}, user:{have:{objectId:{equalTo:$u}}}}, first: 50){ edges { node { objectId bag { objectId } } } } }""", {"u": uid})
    nodes = [e["node"] for e in r["data"]["items"]["edges"]]
    out["sold"] = nodes
    bags = list(dict.fromkeys(n["bag"]["objectId"] for n in nodes if n.get("bag")))[:2]
    out["calls"].clear()
    for bag in bags:
        for path in (f"/sales/{bag}", f"/sales/{bag}/items", f"/sales/{bag}/sold"):
            cur["u"] = path
            try:
                page.goto(F.BASE + path, wait_until="domcontentloaded", timeout=40000); page.wait_for_timeout(7000)
                out["pages"][path] = [page.url, (page.inner_text("body") or "")[:2500]]
            except Exception as e:
                out["pages"][path] = [str(e)[:100]]
    b.close()
Path("data").mkdir(exist_ok=True)
Path("data/probe.json").write_text(json.dumps(out, ensure_ascii=False))
print("calls:", len(out["calls"]), [c["op"] for c in out["calls"]])
