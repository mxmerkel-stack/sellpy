#!/usr/bin/env python3
"""Temporär: Sellpy-First-Abo im Profil (Stichtag für kostenlose Taschen)."""
import json, sys, re
from pathlib import Path
from playwright.sync_api import sync_playwright
sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_sellpy as F

out = {"pages": {}, "calls": [], "links": []}
with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    ctx = b.new_context(locale="de-DE", timezone_id="Europe/Berlin", viewport={"width": 1280, "height": 900},
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")
    page = ctx.new_page(); cur = {"u": ""}
    def on_resp(r):
        if "graphql" not in r.url: return
        try: body = r.text(); req = r.request.post_data or ""
        except Exception: return
        if re.search(r"subscri|membership|sellpyFirst|first|freeBag|free_bag|bagOrder", body + req, re.I):
            m = re.search(r'"operationName":"(\w+)"', req)
            out["calls"].append({"page": cur["u"], "op": m.group(1) if m else "", "req": req[:1200], "resp": body[:2500]})
    page.on("response", on_resp)
    F.login(page)
    page.goto(F.BASE + "/", wait_until="domcontentloaded", timeout=60000); page.wait_for_timeout(4000)
    for a in page.locator("a").all()[:300]:
        try: t = (a.inner_text(timeout=300) or "").strip()[:50].replace("\n", " "); h = a.get_attribute("href", timeout=300)
        except Exception: continue
        if re.search(r"first|profil|konto|account|abo|mitglied|einstell|settings|subscr", f"{t} {h}", re.I): out["links"].append([t, h])
    for path in ["/profile", "/my-profile", "/account", "/my-account", "/settings", "/sellpy-first", "/first", "/my-pages", "/profile/subscription", "/subscription"]:
        cur["u"] = path
        try:
            r = page.goto(F.BASE + path, wait_until="domcontentloaded", timeout=40000); page.wait_for_timeout(5000)
            txt = page.inner_text("body") or ""
            if re.search(r"first|abo|mitglied", txt, re.I) and "Seite nicht gefunden" not in txt[:400]:
                out["pages"][path] = [page.url, txt[:3500]]
            else: out["pages"][path] = [page.url, "(nichts Passendes)"]
        except Exception as e: out["pages"][path] = [str(e)[:80]]
    b.close()
Path("data").mkdir(exist_ok=True)
Path("data/probe.json").write_text(json.dumps(out, ensure_ascii=False))
print("calls:", len(out["calls"]))
