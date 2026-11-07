#!/usr/bin/env python3
"""Temporär: findet heraus, wie die Favoritenseite Artikeldaten lädt. Ausgabe verschlüsselt."""
import json, sys, re
from pathlib import Path
from playwright.sync_api import sync_playwright
sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_sellpy as F

out = {"net": [], "variants": {}}
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
    w = s.q("query { itemWishlists(where:{selected:{equalTo:true},active:{equalTo:true}}, first: 1000, order: updatedAt_DESC) { edges { node { createdAt item { objectId } } } } }")["data"]["itemWishlists"]["edges"]
    ids = [e["node"]["item"]["objectId"] for e in w]
    out["ids"] = ids
    def on_resp(r):
        u = r.url
        if re.search(r"\.(png|jpe?g|webp|svg|css|js|woff2?|ico|gif|avif)(\?|$)", u): return
        try: body = r.text()
        except Exception: body = ""
        req = r.request.post_data or ""
        hit = any(i in body or i in req or i in u for i in ids[:30])
        if "graphql" in u and not hit: return
        out["net"].append({"url": u[:300], "m": r.request.method, "req": req[:1500], "hit": hit, "resp": body[:1500] if hit else ""})
    page.on("response", on_resp)
    page.goto(F.BASE + "/my-shopping/favorites", wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(9000)
    out["text"] = (page.inner_text("body") or "")[:1500]
    page.remove_listener("response", on_resp)
    i0 = ids[0]
    V = {
      "equalTo": "query($i:ID!){ items(where:{objectId:{equalTo:$i}}, first:1){ edges { node { objectId itemStatus headline localizedMetadata(locale:\"de\") value { amount currency } } } } }",
      "item": "query($i:ID!){ item(id:$i){ objectId itemStatus headline localizedMetadata(locale:\"de\") value { amount currency } } }",
      "node": "query($i:ID!){ node(id:$i){ id ... on Item { objectId itemStatus headline localizedMetadata(locale:\"de\") value { amount currency } } } }",
      "in_nofirst": "query($i:[ID!]){ items(where:{objectId:{in:$i}}){ edges { node { objectId itemStatus headline localizedMetadata(locale:\"de\") value { amount currency } } } } }",
    }
    for k, qq in V.items():
        v = {"i": ids[:5]} if k == "in_nofirst" else {"i": i0}
        r = s.q(qq, v, allow_errors=True)
        out["variants"][k] = json.dumps(r)[:1200]
    b.close()
Path("data").mkdir(exist_ok=True)
Path("data/probe.json").write_text(json.dumps(out, ensure_ascii=False))
print("net:", len(out["net"]), "hits:", sum(1 for n in out["net"] if n["hit"]))
