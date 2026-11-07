#!/usr/bin/env python3
"""Temporär: prüft Favoriten-Abfragen und Artikelfelder. Ausgabe verschlüsselt."""
import json, sys, re
from pathlib import Path
from playwright.sync_api import sync_playwright
sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_sellpy as F

out = {"fields": {}, "wish_counts": {}}
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
    # alle Wunschlisten-Einträge, ohne Filter auf aktiv/ausgewählt
    w = s.pages("""query W($uid: ID!, $first: Int, $after: String) {
      itemWishlists(where: {user: {have: {objectId: {equalTo: $uid}}}}, first: $first, after: $after, order: updatedAt_DESC) {
        pageInfo { hasNextPage endCursor }
        edges { node { objectId createdAt updatedAt selected active item { objectId } itemFavoriteLists { ... on ItemFavoriteList { objectId } } } } } }""",
        "itemWishlists", {"uid": uid})
    from collections import Counter
    out["wish_counts"] = dict(Counter(f"selected={x.get('selected')} active={x.get('active')}" for x in w))
    out["wish_n"] = len(w)
    ids = [x["item"]["objectId"] for x in w if x.get("item")]
    out["wishlists"] = w[:400]
    cands = ["itemStatus", "sellerItemStatus", "createdAt", "updatedAt", "value { amount currency }", "price { amount currency }",
             "originalPrice { amount currency }", "headline", "site", "p2p", "shelfId", "localizedMetadata(locale: \"de\")",
             "photos { ... on Element { value } }", "user { objectId }", "bag { objectId }", "putOnShelfAt", "soldAt", "paidAt",
             "listedAt", "publishedAt", "featuredIn { ... on Element { value } }", "marketOffer { objectId pricing }"]
    good = []
    for c in cands:
        r = s.q("query($ids:[ID!]){ items(where:{objectId:{in:$ids}}, first: 5){ edges { node { objectId %s } } } }" % c, {"ids": ids[:5]}, allow_errors=True)
        ok = not r.get("errors")
        out["fields"][c] = "ok" if ok else (r["errors"][0].get("message", "")[:160])
        if ok: good.append(c)
    q = "query($ids:[ID!],$first:Int){ items(where:{objectId:{in:$ids}}, first:$first){ edges { node { objectId %s } } } }" % " ".join(good)
    items = []
    for i in range(0, len(ids), 100):
        r = s.q(q, {"ids": ids[i:i+100], "first": 100}, allow_errors=True)
        items += [e["node"] for e in ((r.get("data") or {}).get("items") or {}).get("edges", [])]
    out["items"] = items; out["n_ids"] = len(ids)
    for name, qq in {"brandGroups": "query { getFavoriteBrandGroups { group { objectId name } brands } }",
                     "lists": "query($u:ID!){ itemFavoriteLists(where:{user:{have:{objectId:{equalTo:$u}}}}, first: 50){ edges { node { objectId name status public } } } }"}.items():
        r = s.q(qq, {"u": uid} if "$u" in qq else None, allow_errors=True)
        out[name] = r.get("data") or r.get("errors")
    b.close()
Path("data").mkdir(exist_ok=True)
Path("data/probe.json").write_text(json.dumps(out, ensure_ascii=False))
print("fields:", json.dumps(out["fields"], ensure_ascii=False))
print("wish_counts:", out["wish_counts"], "items:", len(out["items"]), "of", out["n_ids"])
