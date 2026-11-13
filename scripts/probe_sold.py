#!/usr/bin/env python3
"""Temporär: findet heraus, woher Sellpy Zahlungsdatum/Anteil verkaufter, noch nicht abgerechneter Artikel nimmt."""
import json, sys, re
from pathlib import Path
from playwright.sync_api import sync_playwright
sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_sellpy as F

IDS = ["TDZeqS1uyZ", "4LHc5mdFpr", "t3VRH31P7C", "ZTryuVK5vg", "1LOSQcerGH", "pjHYDLfUsa"]
out = {"calls": [], "pages": {}}
with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    ctx = b.new_context(locale="de-DE", timezone_id="Europe/Berlin", viewport={"width": 1280, "height": 900},
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")
    page = ctx.new_page(); cur = {"u": ""}
    def on_resp(r):
        if "graphql" not in r.url: return
        try: body = r.text(); req = r.request.post_data or ""
        except Exception: return
        if any(i in body for i in IDS) or re.search(r"payout|Payout|expected|sold", req):
            out["calls"].append({"page": cur["u"], "req": req[:3000], "resp": body[:4000]})
    page.on("response", on_resp)
    F.login(page)
    for path in ["/sales", "/my-sales", "/sales/sold", "/my-items", "/account/balance", "/balance"]:
        cur["u"] = path
        try:
            page.goto(F.BASE + path, wait_until="domcontentloaded", timeout=40000); page.wait_for_timeout(6000)
            out["pages"][path] = [page.url, page.title(), (page.inner_text("body") or "")[:900]]
        except Exception as e:
            out["pages"][path] = [str(e)[:100]]
    b.close()
Path("data").mkdir(exist_ok=True)
Path("data/probe.json").write_text(json.dumps(out, ensure_ascii=False))
print("calls:", len(out["calls"]))
