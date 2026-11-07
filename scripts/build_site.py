#!/usr/bin/env python3
"""Bereitet data/sellpy.json für das Dashboard auf und baut dist/index.html (noch unverschlüsselt)."""
import json
import os
import re
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
}
SOLD = {"betald", "såld"}
KIDS_SIZES = set(range(62, 177, 6))
CATEGORIES = [
    ("Jacken & Mäntel", ["jacke", "mantel", "weste", "parka", "blazer", "sakko", "anorak", "fleece"]),
    ("Hemden & Blusen", ["hemd", "bluse"]),
    ("Pullover & Strick", ["pullover", "pulli", "strick", "cardigan", "sweat", "hoodie", "kapuzen"]),
    ("Hosen & Jeans", ["hose", "jeans", "chino", "shorts", "leggings"]),
    ("Shirts & Tops", ["shirt", "top", "polo", "longsleeve"]),
    ("Kleider & Röcke", ["kleid", "rock"]),
    ("Schuhe", ["schuh", "sneaker", "stiefel", "sandale", "boots", "pumps", "slipper"]),
    ("Accessoires", ["tasche", "gürtel", "mütze", "schal", "krawatte", "armband", "kette", "uhr", "cap", "hut",
                     "handschuh", "sonnenbrille", "rucksack", "geldbörse"]),
    ("Beauty & Duft", ["parfum", "parfüm", "eau de", "creme", "kosmetik", "pflege"]),
    ("Baby & Kind", ["baby", "kinderwagen", "adapter", "babyschale", "spielzeug", "puzzle", "monitor"]),
    ("Sport & Freizeit", ["sport", "fahrrad", "klimmzug", "hantel", "yoga", "ball", "camping"]),
    ("Haushalt & Technik", ["lampe", "küche", "kabel", "lautsprecher", "kopfhörer", "auto", "werkzeug", "deko", "vase"]),
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
    for name, words in CATEGORIES:
        if any(w in s for w in words):
            return name
    return "Sonstiges"


def is_kids(meta, size):
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
        size = flat(meta.get("size") or meta.get("sizeLabel") or "")
        row = {"id": it["objectId"], "brand": brand, "kind": kind, "size": size, "condition": flat(meta.get("condition")),
               "category": category(flat(meta.get("type"))), "kids": is_kids(meta, size), "price": price,
               "status": STATUS.get(status, status or "Unbekannt"), "bag": (it.get("bag") or {}).get("objectId"),
               "created_at": it.get("createdAt")}
        items.append(row)
        if sold_tx or status in SOLD:
            sold_at = it.get("paidAt") or (sold_tx[0]["createdAt"] if sold_tx else None) or it.get("createdAt")
            start = it.get("publishedAt") or it.get("saleStartedAt") or it.get("putUpForSaleAt") or it.get("createdAt")
            gross = amt("itemSold") or price
            net = sum(t["delta"]["amount"] for t in txs) / 100 if txs else None
            d0, d1 = day(start), day(sold_at)
            sales.append({**row, "price": gross, "net": net, "commission": -amt("itemCommission"), "ad_fee": -amt("itemAdFee"),
                          "sold_at": sold_at, "days_listed": (d1 - d0).days if d0 and d1 else None,
                          "bag_date": bag_dates.get(row["bag"])})

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
    credits = [{"at": c["createdAt"], "type": c["type"], "amount": c["delta"]["amount"] / 100} for c in raw.get("credits", [])]
    return {"items": items, "sales": sorted(sales, key=lambda s: s["sold_at"] or ""), "bags": sorted(bags, key=lambda b: b["created_at"] or ""),
            "payouts": payouts, "credits": credits, "credit_now": raw.get("credit_now"), "other_tx_types": other_types,
            "fetched_at": raw.get("fetched_at")}


def main():
    raw = read("sellpy.json", None)
    payload = transform(raw) if raw else read("sample.json", {})
    payload["built_at"] = datetime.now(timezone.utc).isoformat()
    blob = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    html = (ROOT / "site" / "template.html").read_text().replace("__DATA__", blob, 1)
    DIST.mkdir(parents=True, exist_ok=True)
    (DIST / "index.html").write_text(html)
    print(f"ok: dist/index.html gebaut ({len(payload.get('sales', []))} Verkäufe, {len(payload.get('items', []))} Artikel)")


if __name__ == "__main__":
    main()
