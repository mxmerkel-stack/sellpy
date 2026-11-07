#!/usr/bin/env python3
"""Temporär: Algolia-Treffer der Favoriten komplett ansehen. Ausgabe verschlüsselt."""
import json, sys, re
from pathlib import Path
from playwright.sync_api import sync_playwright
sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_sellpy as F

out = {}
with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    ctx = b.new_context(locale="de-DE", timezone_id="Europe/Berlin", viewport={"width": 1280, "height": 900},
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")
    page = ctx.new_page(); sess = {}; alg = {}
    def on_req(r):
        t = r.headers.get("x-parse-session-token")
        if t: sess.update(token=t, app=r.headers.get("x-parse-application-id"))
        if "algolia.net/1/indexes" in r.url and not alg:
            alg.update(url=r.url, headers={k: v for k, v in r.headers.items() if k.lower() in ("content-type", "x-algolia-api-key", "x-algolia-application-id")})
    page.on("request", on_req)
    F.login(page)
    page.goto(F.BASE + "/sales", wait_until="domcontentloaded", timeout=60000)
    for _ in range(20):
        if sess.get("token"): break
        page.wait_for_timeout(500)
    s = F.Sellpy(page, sess["token"], sess["app"])
    w = s.q("query { itemWishlists(where:{selected:{equalTo:true},active:{equalTo:true}}, first: 1000, order: updatedAt_DESC) { edges { node { createdAt item { objectId } } } } }")["data"]["itemWishlists"]["edges"]
    ids = [e["node"]["item"]["objectId"] for e in w]
    page.goto(F.BASE + "/my-shopping/favorites", wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(8000)
    out["alg_url"] = alg.get("url", "")[:400]; out["alg_hdr_keys"] = list(alg.get("headers", {}))
    hits = []
    for i in range(0, len(ids), 40):
        flt = "(" + " OR ".join(f"objectID:{x}" for x in ids[i:i+40]) + ")"
        body = {"requests": [{"indexName": "prod_marketItem_de_relevance", "hitsPerPage": 100, "filters": flt}]}
        r = page.request.post(alg["url"].split("?")[0] + "?" + alg["url"].split("?", 1)[1], headers=alg["headers"], data=json.dumps(body), timeout=60000)
        j = r.json(); hits += j["results"][0]["hits"]
    out["n_ids"] = len(ids); out["n_hits"] = len(hits)
    out["hits"] = hits[:4]
    out["all_keys"] = sorted({k for h in hits for k in h})
    out["found_ids"] = [h["objectID"] for h in hits]
    b.close()
Path("data").mkdir(exist_ok=True)
Path("data/probe.json").write_text(json.dumps(out, ensure_ascii=False))
print("ids", out["n_ids"], "hits", out["n_hits"])
