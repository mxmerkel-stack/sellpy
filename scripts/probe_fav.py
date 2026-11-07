#!/usr/bin/env python3
"""Temporär: findet heraus, wie Sellpy die Favoritenliste abfragt. Ausgabe verschlüsselt."""
import json, os, re, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright
sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_sellpy as F

out = {"links": [], "calls": [], "introspection": None, "urls": {}}
with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    ctx = b.new_context(locale="de-DE", timezone_id="Europe/Berlin", viewport={"width": 1280, "height": 900},
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")
    page = ctx.new_page()
    sess = {}
    def on_req(r):
        t = r.headers.get("x-parse-session-token")
        if t: sess.update(token=t, app=r.headers.get("x-parse-application-id"))
    page.on("request", on_req)
    cur = {"url": ""}
    def on_resp(r):
        if "graphql" in r.url and r.request.method == "POST":
            try:
                body = r.request.post_data or ""
                txt = r.text()
            except Exception:
                return
            out["calls"].append({"page": cur["url"], "req": body[:2500], "resp": txt[:1800]})
    page.on("response", on_resp)
    F.login(page)
    page.goto(F.BASE + "/", wait_until="domcontentloaded", timeout=60000); page.wait_for_timeout(4000)
    for a in page.locator("a, button").all()[:400]:
        try:
            t = (a.inner_text(timeout=300) or "").strip()[:60]; h = a.get_attribute("href", timeout=300)
        except Exception:
            continue
        if re.search(r"favorit|merk|wunsch|gespeichert|herz|wish|saved|like", f"{t} {h}", re.I):
            out["links"].append([t, h])
    for path in ["/favorites", "/favourites", "/wishlist", "/saved", "/likes", "/account/favorites", "/my-favorites", "/profile/favorites"]:
        cur["url"] = path
        try:
            r = page.goto(F.BASE + path, wait_until="domcontentloaded", timeout=40000)
            page.wait_for_timeout(5000)
            out["urls"][path] = [r.status if r else None, page.url, page.title(), (page.inner_text("body") or "")[:300]]
        except Exception as e:
            out["urls"][path] = [str(e)[:100]]
    s = F.Sellpy(page, sess["token"], sess["app"])
    r = s.q("query { __schema { queryType { fields { name } } mutationType { fields { name } } } }", allow_errors=True)
    if r.get("data") and r["data"].get("__schema"):
        pat = re.compile(r"fav|wish|like|save|heart|bookmark", re.I)
        out["introspection"] = {k: [f["name"] for f in (r["data"]["__schema"][k] or {}).get("fields", []) if pat.search(f["name"])]
                                for k in ("queryType", "mutationType")}
    else:
        out["introspection"] = (r.get("errors") or [{}])[0].get("message", "")[:200]
    b.close()
Path("data").mkdir(exist_ok=True)
Path("data/probe.json").write_text(json.dumps(out, ensure_ascii=False))
