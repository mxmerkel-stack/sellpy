#!/usr/bin/env python3
"""Bereitet data/sellpy.json für das Dashboard auf und baut dist/index.html (noch unverschlüsselt)."""
import json
import os
import re
import shutil
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("DATA_DIR", ROOT / "data"))
DIST = Path(os.environ.get("DIST_DIR", ROOT / "dist"))

STATUS = {
    "utlagd": "Online", "betald": "Verkauft", "såld": "Verkauft", "vilande": "Pausiert", "skänkt": "Gespendet",
    "awaitingApproval": "Wartet auf Freigabe", "awaitingChangeRequestReview": "Prüfung läuft",
    "returnerad": "Zurückgeschickt", "återlämnad": "Zurückgeschickt", "sentBack": "Zurückgeschickt",
    "rejected": "Abgelehnt", "nekad": "Abgelehnt", "lost": "Verloren", "processing": "In Bearbeitung",
    "skänktDirekt": "Gespendet", "registrerad": "In Bearbeitung", "tillbakaskickadDirekt": "Zurückgeschickt",
    "tillbakaskickad": "Zurückgeschickt", "borttagen": "Entfernt",
}
SOLD = {"betald", "såld"}
REJECTED_CLAIMS = {"rejected", "denied", "declined", "canceled", "cancelled", "nekad", "avslagen"}
KIDS_SIZES = set(range(62, 177, 6))
CATEGORIES = [
    ("Bodys & Strampler", ["body", "strampler", "overall", "jumpsuit", "spucktuch", "lätzchen", "tragetuch"]),
    ("Jacken & Mäntel", ["jacke", "mantel", "weste", "parka", "blazer", "sakko", "anorak", "fleece", "anzug"]),
    ("Hemden & Blusen", ["hemd", "bluse"]),
    ("Pullover & Strick", ["pullover", "pulli", "strick", "cardigan", "sweat", "hoodie", "kapuzen"]),
    ("Hosen & Jeans", ["hose", "jeans", "chino", "shorts", "leggings", "jeggings"]),
    ("Shirts & Tops", ["shirt", "top", "polo", "longsleeve"]),
    ("Kleider & Röcke", ["kleid", "rock"]),
    ("Schuhe", ["schuh", "sneaker", "stiefel", "sandale", "boots", "pumps", "slipper", "schnürer", "espadrilles"]),
    ("Accessoires", ["tasche", "gürtel", "mütze", "schal", "krawatte", "armband", "armbänder", "kette", "uhr", "cap",
                     "hut", "handschuh", "fäustling", "sonnenbrille", "rucksack", "geldbörse", "haarband", "beutel", "helm"]),
    ("Beauty & Duft", ["parfum", "parfüm", "eau de", "creme", "kosmetik", "pflege", "duft"]),
    ("Baby & Kind", ["baby", "kinderwagen", "adapter", "babyschale", "spielzeug", "puzzle", "monitor"]),
    ("Sport & Freizeit", ["sport", "fahrrad", "klimmzug", "hantel", "yoga", "ball", "camping", "training"]),
    ("Haushalt & Technik", ["lampe", "küche", "kabel", "lautsprecher", "kopfhörer", "auto", "werkzeug", "deko", "vase",
                            "radio", "maus", "vorhang", "kissen", "decke", "bürste", "fontäne", "screen"]),
]


def read(name, default):
    p = DATA / name
    return json.loads(p.read_text()) if p.exists() else default


def flat(v):
    if isinstance(v, list):
        return ", ".join(str(x) for x in v)
    if isinstance(v, dict):
        return ", ".join(f"{x}" for x in v.values())
    return "" if v is None else str(v)


def category(kind):
    s = (kind or "").lower()
    if s.strip() == "set":
        return "Bodys & Strampler"
    for name, words in CATEGORIES:
        if any(w in s for w in words):
            return name
    return "Sonstiges"


def nice_size(raw):
    """'CHILD-CM-86/92' -> '86/92', 'SHOES-EU-23' -> 'EU 23', 'ADULT-INT-L' -> 'L'."""
    if not raw:
        return ""
    parts = raw.split("-")
    if len(parts) >= 3 and parts[0].isupper():
        val = "-".join(parts[2:])
        return f"EU {val}" if parts[0] == "SHOES" else val
    return raw


def is_kids(meta, size):
    demo = flat(meta.get("demography")).lower()
    if demo:
        return any(w in demo for w in ("kinder", "mädchen", "jungen", "baby"))
    if str(size).startswith("CHILD"):
        return True
    text = " ".join(flat(v) for v in meta.values()).lower()
    if re.search(r"\b(kinder|kind|baby|kids|mädchen|jungen)\b", text):
        return True
    nums = [int(x) for x in re.findall(r"\d+", size or "")]
    return bool(nums) and all(n in KIDS_SIZES for n in nums) and ("/" in (size or "") or nums[0] not in (98, 110))


def day(iso):
    return datetime.fromisoformat(iso.replace("Z", "+00:00")) if iso else None


def transform(raw):
    tx_by_item = defaultdict(list)
    for t in raw.get("balance", []):
        if t.get("item"):
            tx_by_item[t["item"]["objectId"]].append(t)
    bag_dates = {b["objectId"]: b.get("createdAt") for b in raw.get("bags", [])}

    items, sales = [], []
    for it in raw.get("items", []):
        meta = it.get("localizedMetadata") or {}
        txs = tx_by_item.get(it["objectId"], [])
        amt = lambda typ: sum(t["delta"]["amount"] for t in txs if t["type"] == typ) / 100  # noqa: E731
        sold_tx = [t for t in txs if t["type"] == "itemSold"]
        status = it.get("itemStatus") or it.get("sellerItemStatus") or ""
        price = (it.get("value") or {}).get("amount", 0) / 100
        brand = flat(meta.get("brand")) or "Ohne Marke"
        kind = flat(meta.get("type")) or "Artikel"
        if meta.get("model"):
            kind = f"{kind}, {flat(meta['model'])}"
        raw_size = flat(meta.get("size") or meta.get("sizeBottom") or meta.get("sizeEstimated") or "")
        size = nice_size(raw_size)
        row = {"id": it["objectId"], "brand": brand, "kind": kind, "size": size, "condition": flat(meta.get("condition")),
               "category": category(flat(meta.get("type"))), "kids": is_kids(meta, raw_size), "demography": flat(meta.get("demography")), "price": price,
               "status": STATUS.get(status, status or "Unbekannt"), "bag": (it.get("bag") or {}).get("objectId"),
               "created_at": it.get("createdAt")}
        items.append(row)
        if sold_tx or status in SOLD:
            sold_at = it.get("paidAt") or (sold_tx[0]["createdAt"] if sold_tx else None)
            if not sold_at:  # gerade verkauft, noch nicht gebucht
                sold_at = raw.get("fetched_at")
            start = it.get("putOnShelfAt") or it.get("assortedAt") or it.get("createdAt")
            gross = amt("itemSold") or price
            net = sum(t["delta"]["amount"] for t in txs) / 100 if txs else None
            d0, d1 = day(start), day(sold_at)
            sales.append({**row, "price": gross, "net": net, "commission": -amt("itemCommission"), "ad_fee": -amt("itemAdFee"),
                          "sold_at": sold_at, "days_listed": (d1 - d0).days if d0 and d1 else None,
                          "bag_date": bag_dates.get(row["bag"])})

    sold_ids = {s["id"] for s in sales}
    unsold_fees = [{"at": t["createdAt"], "amount": t["delta"]["amount"] / 100,
                    "kids": next((i["kids"] for i in items if i["id"] == t["item"]["objectId"]), False)}
                   for t in raw.get("balance", []) if t.get("item") and t["item"]["objectId"] not in sold_ids]
    payouts = [{"at": t["createdAt"], "amount": -t["delta"]["amount"] / 100}
               for t in raw.get("balance", []) if t["type"] == "salePayout"]
    other_types = sorted({t["type"] for t in raw.get("balance", [])} - {"itemSold", "itemCommission", "itemAdFee", "salePayout"})
    bags = []
    for b in raw.get("bags", []):
        bi = [i for i in items if i["bag"] == b["objectId"]]
        bs = [s for s in sales if s["bag"] == b["objectId"]]
        bags.append({"id": b["objectId"], "created_at": b.get("createdAt"), "items": len(bi), "sold": len(bs),
                     "online": sum(1 for i in bi if i["status"] == "Online"),
                     "gross": sum(s["price"] for s in bs), "net": sum(s["net"] or 0 for s in bs)})
    purchases, orders = [], []
    # Rücksendungen: Sellpy führt sie als "itemClaims"; abgelehnte zählen nicht
    claim_type = {c["item"]["objectId"]: c.get("type") for c in raw.get("claims", [])
                  if c.get("item") and str(c.get("status", "")).lower() not in REJECTED_CLAIMS}
    for o in raw.get("orders", []):
        pay = {}
        for el in o.get("itemPayments") or []:
            v = el.get("value") or {}
            pay[v.get("itemId")] = (v.get("payment") or {}).get("amount")
        canceled = bool(o.get("dateCanceled")) or o.get("status") in ("canceled", "cancelled")
        total = (o.get("orderPayment") or {}).get("amount") or 0
        li = o.get("lineItems") or []
        cents = lambda x: ((x or {}).get("amount") or 0) / 100  # noqa: E731
        # Sellpy bucht Erstattungen negativ, Rücksendekosten (CLAIM_FREIGHT) positiv
        refunded = -sum(cents(l.get("amountIncludingTax")) for l in li if l.get("type") in ("ITEM_REFUND", "FREIGHT_REFUND"))
        return_fees = sum(cents(l.get("amountIncludingTax")) for l in li if l.get("type") == "CLAIM_FREIGHT")
        o_items = []
        for it in o.get("items") or []:
            meta = it.get("localizedMetadata") or {}
            raw_size = flat(meta.get("size") or "")
            kind = flat(meta.get("type")) or "Artikel"
            if meta.get("title"):
                kind = f"{kind}: {flat(meta['title'])}"
            ct = claim_type.get(it["objectId"])
            row = {"order": o["objectId"], "item": it["objectId"], "at": o.get("datePaid") or o.get("createdAt"),
                   "brand": flat(meta.get("brand")) or "Ohne Marke", "kind": kind, "size": nice_size(raw_size),
                   "condition": flat(meta.get("condition")), "category": category(flat(meta.get("type"))),
                   "kids": is_kids(meta, raw_size), "price": pay.get(it["objectId"]) or 0,
                   "status": "Storniert" if canceled else ("Behalten" if not ct else ("Reklamiert" if ct == "claim" else "Zurückgeschickt"))}
            o_items.append(row)
            purchases.append(row)
        kept = [r for r in o_items if r["status"] == "Behalten"]
        back = [r for r in o_items if r["status"] in ("Zurückgeschickt", "Reklamiert")]
        orders.append({"id": o["objectId"], "at": o.get("datePaid") or o.get("createdAt"), "total": 0 if canceled else total,
                       "freight": (o.get("freightPayment") or {}).get("amount") or 0, "fast": bool(o.get("isFastHandling")),
                       "credits": ((o.get("creditPaymentCapture") or {}).get("amount") or 0) / 100,
                       "items": len(o_items), "kept": len(kept), "kept_value": sum(r["price"] for r in kept),
                       "returned": len(back), "claimed": sum(1 for r in o_items if r["status"] == "Reklamiert"), "returned_value": sum(r["price"] for r in back),
                       "refunded": refunded if li else sum(r["price"] for r in back), "return_fees": return_fees,
                       "effective": (0 if canceled else total) - (refunded if li else sum(r["price"] for r in back)) + return_fees,
                       "status": "Storniert" if canceled else ("Geliefert" if o.get("dateDelivered") else "Unterwegs"),
                       "kids": bool(o_items) and all(r["kids"] for r in o_items)})
    # Favoriten: Einträge (auch entfernte) und Details der aktuell aktiven
    bought = {p["item"]: p["status"] for p in purchases if p["status"] != "Storniert"}
    hits = {h["objectId"]: h for h in raw.get("fav_items", [])}
    avail = set(raw.get("fav_available") or [])
    wish_events, favs = [], []
    for w in raw.get("wishlist", []):
        iid = (w.get("item") or {}).get("objectId")
        cur = bool(w.get("selected") and w.get("active"))
        h = hits.get(iid)
        meta = (h or {}).get("metadata") or {}
        raw_size = flat(meta.get("size") or (meta.get("sizes") or ""))
        kids = is_kids(meta, raw_size) if h else None
        wish_events.append({"at": w.get("createdAt"), "cur": cur, "bought": bought.get(iid), "kids": kids})
        if cur and iid:
            amount = ((h or {}).get("pricing") or {}).get("amount")
            kind = flat(meta.get("type")) or "Artikel"
            if meta.get("model"):
                kind = f"{kind}, {flat(meta['model'])}"
            favs.append({"id": iid, "at": w.get("createdAt"), "known": bool(h), "avail": iid in avail and bool((h or {}).get("for_sale", True)),
                         "brand": flat(meta.get("brand")) or ("Ohne Marke" if h else "Unbekannt"), "kind": kind if h else "nicht mehr gelistet",
                         "size": nice_size(raw_size), "condition": flat(meta.get("condition")), "category": category(flat(meta.get("type"))) if h else "Unbekannt",
                         "demography": flat(meta.get("demography")), "kids": bool(kids), "price": amount, "dropped": bool((h or {}).get("price_drop")),
                         "likes": (h or {}).get("fav_count"), "reserved": bool((h or {}).get("reserved")), "p2p": bool((h or {}).get("p2p")),
                         "listed_at": ((h or {}).get("sale_started") or 0) / 1000 or None, "bought": bought.get(iid)})
    credits = [{"at": c["createdAt"], "type": c["type"], "amount": c["delta"]["amount"] / 100} for c in raw.get("credits", [])]
    return {"items": items, "sales": sorted(sales, key=lambda s: s["sold_at"] or ""), "bags": sorted(bags, key=lambda b: b["created_at"] or ""),
            "payouts": payouts, "unsold_fees": unsold_fees, "credits": credits, "credit_now": raw.get("credit_now"), "other_tx_types": other_types, "purchases": sorted(purchases, key=lambda r: r["at"] or ""),
            "orders": sorted(orders, key=lambda r: r["at"] or ""),
            "wish": sorted(wish_events, key=lambda e: e["at"] or ""), "favs": sorted(favs, key=lambda e: e["at"] or ""),
            "fetched_at": raw.get("fetched_at")}


def main():
    raw = read("sellpy.json", None)
    payload = transform(raw) if raw else transform({})
    payload["built_at"] = datetime.now(timezone.utc).isoformat()
    blob = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    html = (ROOT / "site" / "template.html").read_text().replace("__DATA__", blob, 1)
    DIST.mkdir(parents=True, exist_ok=True)
    (DIST / "index.html").write_text(html)
    shutil.copytree(ROOT / "site" / "icons", DIST / "icons", dirs_exist_ok=True)
    (DIST / "manifest.webmanifest").write_text(json.dumps({
        "name": "SellDash", "short_name": "SellDash", "start_url": "./", "scope": "./", "display": "standalone",
        "background_color": "#2a78d6", "theme_color": "#2a78d6", "lang": "de",
        "icons": [{"src": "icons/icon-192.png", "sizes": "192x192", "type": "image/png"},
                  {"src": "icons/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"}]}))
    print(f"ok: dist/index.html gebaut ({len(payload.get('sales', []))} Verkäufe, {len(payload.get('items', []))} Artikel)")


if __name__ == "__main__":
    main()
