#!/usr/bin/env python3
"""Holt die eigenen Verkaufsdaten von Sellpy und schreibt data/sellpy.json.

Ablauf:
  1. Anmeldung im Browser (Playwright, headless) mit SELLPY_USER / SELLPY_PASS – genau wie von Hand.
  2. Mit der Sitzung des Browsers werden die Sellpy-GraphQL-Abfragen gestellt, die auch die
     Seite "Meine Verkäufe" nutzt: Artikel, Buchungen je Artikel (Verkauf, Provision, Gebühren),
     Taschen, Sellpy-Credits und eigene Bestellungen (Käufe).
  3. Alles landet in data/sellpy.json (wird im Workflow nicht gespeichert) und im verschlüsselten
     Verlauf data/history.enc.

Es wird nur gelesen, nichts verändert. In den Logs stehen nur Anzahlen und Feldnamen.
"""
import json
import os
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
import crypto_store  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("DATA_DIR", ROOT / "data"))
BASE = "https://www.sellpy.de"
GQL = "https://sellpy-parse-prod.herokuapp.com/graphql"
USER = os.environ.get("SELLPY_USER", "")
PASS = os.environ.get("SELLPY_PASS", "")
PAGE = 200

# Felder, die es nicht bei jedem Artikel geben muss; fehlende werden beim ersten Lauf erkannt und ausgelassen.
OPTIONAL_ITEM_FIELDS = ["paidAt", "putOnShelfAt", "assortedAt", "donateAfter"]


class Sellpy:
    def __init__(self, page, token, app):
        self.page, self.hdr = page, {"content-type": "application/json", "x-parse-application-id": app,
                                     "x-parse-session-token": token}

    def q(self, query, variables=None, allow_errors=False):
        for attempt in range(3):
            r = self.page.request.post(GQL, headers=self.hdr, data=json.dumps({"query": query, "variables": variables or {}}),
                                       timeout=60000)
            if r.status >= 500 and attempt < 2:
                time.sleep(3 * (attempt + 1))
                continue
            body = r.json()
            if body.get("errors") and not allow_errors:
                raise RuntimeError("; ".join(e.get("message", "")[:200] for e in body["errors"]))
            return body
        raise RuntimeError(f"HTTP {r.status}")

    def pages(self, query, key, variables=None):
        out, cursor = [], None
        while True:
            data = self.q(query, {**(variables or {}), "first": PAGE, "after": cursor})["data"][key]
            out += [e["node"] for e in data["edges"]]
            if not data["pageInfo"]["hasNextPage"]:
                return out
            cursor = data["pageInfo"]["endCursor"]


def trim_hit(h):
    """Nur die Felder behalten, die das Dashboard braucht (keine Bilder, Schlagworte, Rankingwerte)."""
    meta = {k: v for k, v in (h.get("metadata") or {}).items() if k != "defects"}
    cats = h.get("categories") or {}
    return {"objectId": h.get("objectID"), "created": h.get("createdAt"), "sale_started": h.get("saleStartedAt"), "metadata": meta,
            "cat": (cats.get("lvl2") or cats.get("lvl1") or cats.get("lvl0") or [""])[0], "pricing": h.get("pricing"),
            "price_drop": h.get("priceDrop_DE"), "fav_count": h.get("favouriteCount"), "p2p": h.get("p2p"),
            "reserved": h.get("isReserved"), "for_sale": h.get("isForSale"), "last_chance": h.get("lastChance"),
            "seller": h.get("user"), "segment": h.get("segment")}


def fetch_fav_items(page, ids):
    """Fragt die Suche (Algolia) mit denselben Zugangsdaten ab, die die Favoritenseite im Browser benutzt."""
    if not ids:
        return [], []
    alg = {}

    def on_req(r):
        if "algolia.net/1/indexes" in r.url and not alg:
            alg.update(url=r.url, index=(json.loads(r.post_data or "{}").get("requests") or [{}])[0].get("indexName"))

    page.on("request", on_req)
    page.goto(BASE + "/my-shopping/favorites", wait_until="domcontentloaded", timeout=60000)
    for _ in range(40):
        if alg.get("index"):
            break
        page.wait_for_timeout(500)
    page.remove_listener("request", on_req)
    if not alg.get("index"):
        raise RuntimeError("Suchzugang der Favoritenseite nicht gefunden")
    hits = []
    for i in range(0, len(ids), 40):
        flt = "(" + " OR ".join(f"objectID:{x}" for x in ids[i:i + 40]) + ")"
        r = page.request.post(alg["url"], headers={"content-type": "application/json"}, timeout=60000,
                              data=json.dumps({"requests": [{"indexName": alg["index"], "hitsPerPage": 100, "filters": flt}]}))
        hits += r.json()["results"][0]["hits"]
    drops = [h for h in hits if h.get("priceDrop_DE")]
    print(f"Favoriten-Details: {len(hits)} von {len(ids)} Artikeln gefunden, {len(drops)} mit Preissenkung"
          + (f" (Beispiel-Felder: {sorted(drops[0]['priceDrop_DE']) if isinstance(drops[0]['priceDrop_DE'], dict) else drops[0]['priceDrop_DE']})" if drops else ""))
    return [trim_hit(h) for h in hits], [h["objectID"] for h in hits]


def login(page):
    page.goto(BASE + "/login", wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(2500)
    for sel in ("button:has-text('Alle Cookies akzeptieren')", "button:has-text('Nur erforderliche Cookies')"):
        try:
            b = page.locator(sel).first
            if b.is_visible(timeout=2000):
                b.click()
                break
        except Exception:
            pass
    page.locator("input[type=email]").first.fill(USER, timeout=15000)
    page.get_by_role("button", name="Fortfahren", exact=True).first.click(timeout=10000)
    pw = page.locator("input[type=password]").first
    pw.wait_for(state="visible", timeout=20000)
    pw.fill(PASS)
    pw.press("Enter")  # nie den Knopf "Mit E-Mail-Link einloggen" erwischen
    page.wait_for_url(lambda u: "/login" not in u, timeout=40000)


def main():
    pw_page = os.environ.get("PAGE_PASSWORD", "")
    if not USER or not PASS:
        sys.exit("SELLPY_USER und SELLPY_PASS fehlen (Repo-Secrets).")
    if len(pw_page) < 12:
        sys.exit("PAGE_PASSWORD fehlt oder ist kürzer als 12 Zeichen.")

    session = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(locale="de-DE", timezone_id="Europe/Berlin", viewport={"width": 1280, "height": 900},
                                  user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                                             "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")
        page = ctx.new_page()

        def on_request(req):
            tok = req.headers.get("x-parse-session-token")
            if tok:
                session.update(token=tok, app=req.headers.get("x-parse-application-id"))

        page.on("request", on_request)
        try:
            login(page)
        except Exception as e:  # noqa: BLE001
            sys.exit(f"Anmeldung bei Sellpy fehlgeschlagen ({type(e).__name__}). Zugangsdaten prüfen.")
        page.goto(BASE + "/sales", wait_until="domcontentloaded", timeout=60000)
        for _ in range(20):
            if session.get("token"):
                break
            page.wait_for_timeout(500)
        if not session.get("token"):
            sys.exit("Angemeldet, aber keine Sitzung gefunden – Sellpy hat vermutlich etwas umgebaut.")
        print("Anmeldung ok")
        s = Sellpy(page, session["token"], session["app"])

        uid = s.q("query { currentUser { objectId } }")["data"]["currentUser"]["objectId"]

        # Welche optionalen Artikelfelder gibt es?
        fields = []
        for f in OPTIONAL_ITEM_FIELDS:
            r = s.q("query { items(first: 1) { edges { node { objectId %s } } } }" % f, allow_errors=True)
            if r.get("errors"):
                hint = r["errors"][0].get("message", "")
                print(f"Feld {f} gibt es nicht ({hint[hint.find('Did you mean'):][:120] if 'Did you mean' in hint else '–'})")
            else:
                fields.append(f)
        print(f"Optionale Artikelfelder: {', '.join(fields) or 'keine'}")

        items = s.pages("""query I($uid: ID!, $first: Int, $after: String) {
          items(where: {user: {have: {objectId: {equalTo: $uid}}}}, first: $first, after: $after, order: [createdAt_DESC]) {
            pageInfo { hasNextPage endCursor }
            edges { node { objectId createdAt itemStatus sellerItemStatus
              value { amount currency } localizedMetadata(locale: "de") bag { objectId } %s } }
          } }""" % " ".join(fields), "items", {"uid": uid})
        print(f"Artikel: {len(items)}")

        balance = s.pages("""query B($first: Int, $after: String) {
          balanceTransactions(first: $first, after: $after, order: [createdAt_DESC]) {
            pageInfo { hasNextPage endCursor }
            edges { node { objectId type delta createdAt item { objectId } sale { objectId } } }
          } }""", "balanceTransactions")
        print(f"Buchungen: {len(balance)}")

        bags = s.pages("""query G($uid: ID!, $first: Int, $after: String) {
          bags(where: {user: {have: {objectId: {equalTo: $uid}}}}, first: $first, after: $after, order: createdAt_DESC) {
            pageInfo { hasNextPage endCursor }
            edges { node { objectId createdAt status region } }
          } }""", "bags", {"uid": uid})
        print(f"Taschen: {len(bags)}")

        credits = s.pages("""query C($uid: ID!, $first: Int, $after: String) {
          creditTransactions(where: {user: {have: {objectId: {equalTo: $uid}}}}, order: [createdAt_DESC], first: $first, after: $after) {
            pageInfo { hasNextPage endCursor }
            edges { node { objectId type delta createdAt } }
          } }""", "creditTransactions", {"uid": uid})
        orders = s.pages("""query O($uid: ID!, $first: Int, $after: String) {
          orders(where: {user: {have: {objectId: {equalTo: $uid}}}}, first: $first, after: $after, order: createdAt_DESC) {
            pageInfo { hasNextPage endCursor }
            edges { node { objectId createdAt status orderPayment freightPayment isFastHandling datePaid dateDelivered dateCanceled
              creditPaymentCapture { amount currency }
              itemPayments { ... on Element { value } }
              items { ... on Item { objectId itemStatus localizedMetadata(locale: "de") } } } }
          } }""", "orders", {"uid": uid})
        print(f"Bestellungen: {len(orders)}")
        ids = [o["objectId"] for o in orders]
        claims = s.pages("""query R($ids: [ID!], $first: Int, $after: String) {
          itemClaims(where: {order: {have: {objectId: {in: $ids}}}}, first: $first, after: $after) {
            pageInfo { hasNextPage endCursor }
            edges { node { objectId createdAt status type offer paidAt item { objectId } order { objectId } } }
          } }""", "itemClaims", {"ids": ids}) if ids else []
        from collections import Counter
        print(f"Rücksendungen/Reklamationen: {len(claims)} {dict(Counter((c.get('type'), c.get('status')) for c in claims))}")
        for o in orders:
            r = s.q("query L($id: ID!) { fetchLineItemsByOrder(orderId: $id) { type amountIncludingTax discountAmount } }",
                    {"id": o["objectId"]}, allow_errors=True)
            o["lineItems"] = (r.get("data") or {}).get("fetchLineItemsByOrder") or []
        # Favoriten: Einträge kommen per GraphQL, Artikeldetails (Marke, Preis …) aus der Suche, die auch die Favoritenseite nutzt
        wish, fav_items, fav_avail = [], [], []
        try:
            wish = s.pages("""query W($uid: ID!, $first: Int, $after: String) {
              itemWishlists(where: {user: {have: {objectId: {equalTo: $uid}}}}, first: $first, after: $after, order: updatedAt_DESC) {
                pageInfo { hasNextPage endCursor }
                edges { node { objectId createdAt updatedAt selected active item { objectId } } }
              } }""", "itemWishlists", {"uid": uid})
            cur_ids = [w["item"]["objectId"] for w in wish if w.get("selected") and w.get("active") and w.get("item")]
            print(f"Favoriten-Einträge: {len(wish)}, davon aktiv: {len(cur_ids)}")
            fav_items, fav_avail = fetch_fav_items(page, cur_ids)
        except Exception as e:  # noqa: BLE001
            print(f"Favoriten übersprungen ({type(e).__name__}: {str(e)[:120]})")
        credit_now = s.q('query { currentUserCredit(currency: "EUR") }', allow_errors=True).get("data", {}).get("currentUserCredit")
        print(f"Credit-Buchungen: {len(credits)}")
        browser.close()

    meta_keys = sorted({k for it in items for k in (it.get("localizedMetadata") or {})})
    print(f"Artikel-Merkmale: {', '.join(meta_keys)}")

    snapshot = {"fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "items": items, "balance": balance,
                "bags": bags, "credits": credits, "orders": orders, "claims": claims, "credit_now": credit_now, "item_fields": fields,
                "wishlist": wish, "fav_items": fav_items, "fav_available": fav_avail}

    # Verlauf: Artikel und Buchungen werden zusammengeführt, damit nichts verloren geht
    hist_path = DATA / "history.enc"
    try:
        hist = crypto_store.load(hist_path, pw_page) or {}
    except Exception:
        print("Verlauf nicht lesbar (anderes Seitenpasswort?) – starte neu.")
        hist = {}
    for key in ("items", "balance", "bags", "credits", "orders", "claims", "wishlist", "fav_items"):
        merged = {x["objectId"]: x for x in hist.get(key, [])}
        merged.update({x["objectId"]: x for x in snapshot[key]})
        snapshot[key] = list(merged.values())
    crypto_store.save(hist_path, snapshot, pw_page)
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "sellpy.json").write_text(json.dumps(snapshot, ensure_ascii=False))
    print("ok: Daten gespeichert")


if __name__ == "__main__":
    main()
