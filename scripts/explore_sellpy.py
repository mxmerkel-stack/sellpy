#!/usr/bin/env python3
"""Einmalige Erkundung: Wie liefert Sellpy die Verkaufsdaten aus?

Meldet sich mit SELLPY_USER / SELLPY_PASS im Browser (Playwright, headless) bei sellpy.de an,
öffnet die Profil- und Verkaufsseiten und zeichnet alle JSON-Antworten und Seitentexte auf.

Das Ergebnis wird mit explore/pubkey.pem verschlüsselt (RSA-OAEP + AES-256-GCM) und als
Base64-Block ins Log geschrieben. Lesbar nur mit dem privaten Schlüssel, den Claude in der
Sitzung hält – nicht im Repo. Passwort, E-Mail, Cookies und Tokens werden vorher entfernt.
Es wird nichts verändert, nur gelesen.
"""
import base64
import gzip
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
BASE = os.environ.get("SELLPY_BASE", "https://www.sellpy.de")
USER = os.environ.get("SELLPY_USER", "")
PASS = os.environ.get("SELLPY_PASS", "")
SECRET_KEYS = re.compile(r"(token|session|password|passwort|cookie|authorization|secret|jwt|bearer)", re.I)
MAX_BODY = 400_000

log = {"steps": [], "responses": [], "pages": []}


def step(msg):
    print(msg, flush=True)
    log["steps"].append(f"{time.strftime('%H:%M:%S')} {msg}")


def scrub(text):
    if not isinstance(text, str):
        return text
    for s in (PASS, USER):
        if s:
            text = text.replace(s, "<entfernt>")
    text = re.sub(r'("(?:[^"]*(?:token|session|password|jwt)[^"]*)"\s*:\s*)"[^"]*"', r'\1"<entfernt>"', text, flags=re.I)
    text = re.sub(r"(Bearer\s+)[A-Za-z0-9._\-]+", r"\1<entfernt>", text)
    return text


def headers_clean(h):
    return {k: v for k, v in (h or {}).items() if not SECRET_KEYS.search(k)}


def on_response(resp):
    try:
        ct = resp.headers.get("content-type", "")
        url = resp.url
        if not any(x in ct for x in ("json", "graphql")) and "graphql" not in url and "/parse/" not in url:
            return
        req = resp.request
        try:
            body = resp.text()
        except Exception as e:  # noqa: BLE001
            body = f"<nicht lesbar: {e}>"
        log["responses"].append({
            "t": time.time(), "url": url, "method": req.method, "status": resp.status,
            "req_headers": headers_clean(req.headers), "req_body": scrub((req.post_data or "")[:20000]),
            "resp_headers": headers_clean(resp.headers), "body": scrub(body[:MAX_BODY]), "len": len(body),
        })
    except Exception as e:  # noqa: BLE001
        step(f"Antwort nicht aufgezeichnet: {e}")


def snap(page, label):
    try:
        text = page.inner_text("body")[:60000]
    except Exception:
        text = ""
    links = []
    try:
        links = page.eval_on_selector_all("a[href]", "els => els.map(e => [e.innerText.trim().slice(0,80), e.getAttribute('href')])")
    except Exception:
        pass
    forms = []
    try:
        forms = page.eval_on_selector_all("input,button", "els => els.map(e => [e.tagName, e.type||'', e.name||'', e.id||'', (e.placeholder||e.innerText||'').slice(0,60)])")
    except Exception:
        pass
    log["pages"].append({"label": label, "url": page.url, "title": page.title(), "text": scrub(text),
                         "links": links[:400], "inputs": forms[:200]})
    step(f"Seite '{label}': {page.url}")


def click_first(page, selectors, timeout=2500):
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=timeout):
                loc.click(timeout=timeout)
                return sel
        except Exception:
            continue
    return None


def main():
    if not USER or not PASS:
        sys.exit("SELLPY_USER und SELLPY_PASS fehlen (Repo-Secrets).")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(locale="de-DE", timezone_id="Europe/Berlin", viewport={"width": 1280, "height": 900},
                                  user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                                             "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")
        page = ctx.new_page()
        page.on("response", on_response)

        page.goto(BASE, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)
        c = click_first(page, ["button:has-text('Alle akzeptieren')", "button:has-text('Akzeptieren')",
                               "button:has-text('Alle Cookies akzeptieren')", "#onetrust-accept-btn-handler",
                               "button:has-text('Accept all')"])
        step(f"Cookie-Banner: {c}")
        snap(page, "start")

        # Login-Seite finden
        for path in ("/login", "/signin", "/sign-in", "/anmelden"):
            page.goto(urljoin(BASE, path), wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(2500)
            if page.locator("input[type=password]").count() or page.locator("input[type=email]").count():
                break
        snap(page, "login-seite")

        email_sel = "input[type=email], input[name*=mail i], input[autocomplete=username], input[name=username]"
        try:
            page.locator(email_sel).first.fill(USER, timeout=8000)
            step("E-Mail eingetragen")
            if not page.locator("input[type=password]").first.is_visible(timeout=1500):
                click_first(page, ["button[type=submit]", "button:has-text('Weiter')", "button:has-text('Fortfahren')"])
                page.wait_for_timeout(2500)
            page.locator("input[type=password]").first.fill(PASS, timeout=8000)
            step("Passwort eingetragen")
            used = click_first(page, ["button[type=submit]", "button:has-text('Anmelden')", "button:has-text('Einloggen')",
                                      "button:has-text('Log in')"])
            if not used:
                page.keyboard.press("Enter")
            step(f"Absenden: {used or 'Enter'}")
            page.wait_for_load_state("networkidle", timeout=30000)
        except Exception as e:  # noqa: BLE001
            step(f"Login-Formular: {type(e).__name__}: {str(e)[:200]}")
        page.wait_for_timeout(4000)
        snap(page, "nach-login")

        # Profil- und Verkaufsseiten besuchen
        candidates = ["/profile", "/my-pages", "/my-sales", "/profile/sales", "/sales", "/myitems", "/my-items",
                      "/profil", "/meine-verkaeufe", "/account"]
        seen = set()
        for _, href in log["pages"][-1]["links"]:
            if href and re.search(r"(profil|profile|sale|verkauf|sell|my|mein|account|konto|item|artikel|balance|guthaben|payout|auszahl)", href, re.I):
                candidates.append(href)
        for href in candidates:
            url = urljoin(BASE, href)
            if urlparse(url).netloc != urlparse(BASE).netloc or url in seen or len(seen) >= 18:
                continue
            seen.add(url)
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(3500)
                for _ in range(3):
                    page.mouse.wheel(0, 4000)
                    page.wait_for_timeout(900)
                snap(page, href)
                # Unterseiten der Verkaufsseiten einmal mitnehmen
                for _, sub in log["pages"][-1]["links"]:
                    if sub and re.search(r"(sale|verkauf|sold|verkauft|item)", sub, re.I):
                        candidates.append(sub)
            except Exception as e:  # noqa: BLE001
                step(f"{href}: {type(e).__name__}")
        browser.close()

    blob = gzip.compress(json.dumps(log, ensure_ascii=False).encode())
    pub = serialization.load_pem_public_key((ROOT / "explore" / "pubkey.pem").read_bytes())
    key, iv = AESGCM.generate_key(256), os.urandom(12)
    wrapped = pub.encrypt(key, padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None))
    box = base64.b64encode(json.dumps({"k": base64.b64encode(wrapped).decode(), "iv": base64.b64encode(iv).decode(),
                                       "d": base64.b64encode(AESGCM(key).encrypt(iv, blob, None)).decode()}).encode()).decode()
    print(f"Aufgezeichnet: {len(log['responses'])} JSON-Antworten, {len(log['pages'])} Seiten, {len(blob)//1024} KB")
    print("-----BEGIN EXPLORE-----")
    for i in range(0, len(box), 4000):
        print(box[i:i + 4000])
    print("-----END EXPLORE-----")


if __name__ == "__main__":
    main()
