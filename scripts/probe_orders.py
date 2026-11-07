#!/usr/bin/env python3
"""Einrichtung (temporär): zeichnet die Abfragen der Seiten "Meine Bestellungen" auf."""
import json, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from playwright.sync_api import sync_playwright
import fetch_sellpy as F

rec = []
def on_response(resp):
    if "graphql" in resp.url or "/parse/" in resp.url:
        try:
            body = resp.text()[:300000]
        except Exception:
            body = ""
        rec.append({"url": resp.url, "req": (resp.request.post_data or "")[:30000], "body": body})

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    ctx = b.new_context(locale="de-DE", timezone_id="Europe/Berlin", viewport={"width": 1280, "height": 900})
    page = ctx.new_page()
    page.on("response", on_response)
    F.login(page)
    print("Anmeldung ok")
    pages = []
    for url in ("/orders", "/user/orders"):
        page.goto(F.BASE + url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(5000)
        for _ in range(4):
            page.mouse.wheel(0, 4000); page.wait_for_timeout(1000)
        links = page.eval_on_selector_all("a[href]", "els => els.map(e => e.getAttribute('href'))")
        pages.append({"url": page.url, "text": page.inner_text("body")[:20000], "links": links})
    order_links = [h for h in pages[0]["links"] if h and h.startswith("/order/")]
    print(f"Bestell-Links: {len(order_links)}")
    for h in order_links[:2]:
        page.goto(F.BASE + h, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(5000)
        pages.append({"url": page.url, "text": page.inner_text("body")[:20000], "links": []})
    b.close()
out = Path("probe.json")
out.write_text(json.dumps({"rec": [r for r in rec if F.PASS not in r["req"]], "pages": pages}, ensure_ascii=False))
print(f"Aufgezeichnet: {len(rec)}")
