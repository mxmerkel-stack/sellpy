#!/usr/bin/env python3
"""Liest die Daten aus einer Sellpy-Verkaufsmail ("Juhu, dein Artikel ist verkauft!").

Aufbau der Mail (HTML, react-email):
  <p>Marke</p> <p>Artikeltyp, Größe: X</p> <p>3,50 EUR</p>
  "Durch den Verkauf ... ca. 1 kg CO2 und ca. 552 Liter Wasser zu sparen"
  "Wurde 131 Tage lang in der Sellpy-Community beworben"
  "Wurde 9 mal favorisiert"
  "Konnte in 24 Ländern ... gekauft werden"
  "Wurde zwischen dem 08. Juli - 06. November sicher gelagert"
"""
import email
import html as htmllib
import re
from datetime import datetime, timezone
from email import policy
from email.utils import parsedate_to_datetime

PRICE_RE = re.compile(r"^(\d{1,3}(?:\.\d{3})+|\d+)(?:,(\d{2}))?\s*(?:EUR|€)$")
MONTHS = {"januar": 1, "februar": 2, "märz": 3, "maerz": 3, "april": 4, "mai": 5, "juni": 6,
          "juli": 7, "august": 8, "september": 9, "oktober": 10, "november": 11, "dezember": 12}

# Grobe Kategorien aus dem Artikeltyp (erstes passendes Stichwort gewinnt).
CATEGORIES = [
    ("Jacken & Mäntel", ["jacke", "mantel", "weste", "parka", "blazer", "sakko", "anorak", "fleece"]),
    ("Hemden & Blusen", ["hemd", "bluse"]),
    ("Pullover & Strick", ["pullover", "pulli", "strick", "cardigan", "sweat", "hoodie", "kapuzen"]),
    ("Hosen & Jeans", ["hose", "jeans", "chino", "shorts", "leggings"]),
    ("Shirts & Tops", ["shirt", "top", "polo", "longsleeve"]),
    ("Kleider & Röcke", ["kleid", "rock"]),
    ("Schuhe", ["schuh", "sneaker", "stiefel", "sandale", "boots", "pumps", "slipper"]),
    ("Accessoires", ["tasche", "gürtel", "mütze", "schal", "krawatte", "armband", "kette", "uhr", "cap", "hut",
                     "handschuh", "sonnenbrille", "rucksack", "geldbörse", "portemonnaie"]),
]
# Kindergrößen nach Körpergröße (62, 68, ... 176) – auch als "122/128"
KIDS_SIZES = set(range(62, 177, 6)) | {50, 56}
BABY_WORDS = ("baby", "body", "strampler", "kinder", "kids", "mini ")


def _texts(html):
    """Alle <p>-Texte in Reihenfolge."""
    out = []
    for m in re.findall(r"<p\b[^>]*>(.*?)</p>", html, re.S | re.I):
        t = htmllib.unescape(re.sub(r"<[^>]+>", " ", m))
        t = re.sub(r"\s+", " ", t.replace("\ufeff", "")).strip()
        if t:
            out.append(t)
    return out


def _num(pattern, text, cast=int):
    m = re.search(pattern, text, re.I)
    if not m:
        return None
    try:
        return cast(m.group(1).replace(".", "").replace(",", "."))
    except ValueError:
        return None


def _storage(text, sold):
    """'zwischen dem 08. Juli - 06. November' -> (ISO-Start, ISO-Ende). Jahr aus dem Verkaufsdatum."""
    m = re.search(r"zwischen dem (\d{1,2})\.\s*([A-Za-zäöüÄÖÜ]+)\s*-\s*(\d{1,2})\.\s*([A-Za-zäöüÄÖÜ]+)", text)
    if not m:
        return None, None
    m1, m2 = MONTHS.get(m.group(2).lower()), MONTHS.get(m.group(4).lower())
    if not m1 or not m2:
        return None, None
    y2 = sold.year
    y1 = y2 if m1 <= m2 else y2 - 1
    try:
        return (datetime(y1, m1, int(m.group(1))).date().isoformat(),
                datetime(y2, m2, int(m.group(3))).date().isoformat())
    except ValueError:
        return None, None


def is_kids(brand, kind, size):
    text = f"{brand} {kind}".lower() + " "
    if any(w in text for w in BABY_WORDS):
        return True
    nums = [int(x) for x in re.findall(r"\d+", size or "")]
    if "/" in (size or "") and nums and all(n in KIDS_SIZES for n in nums):
        return True
    # Einzelne Größen nur sicher, wenn sie keine Erwachsenengröße sein können
    return len(nums) == 1 and nums[0] in KIDS_SIZES and nums[0] not in (50, 56, 98, 110) \
        and not re.search(r"[a-z]", (size or "").lower())


def category(kind):
    s = (kind or "").lower()
    for name, words in CATEGORIES:
        if any(w in s for w in words):
            return name
    return "Sonstiges"


def parse_sale_html(html, sold):
    """Gibt eine Liste von Artikeln zurück (meist genau einer)."""
    ps = _texts(html)
    full = " \n".join(ps)
    items = []
    for i, t in enumerate(ps):
        m = PRICE_RE.match(t)
        if not m or i < 1:
            continue
        price = float(m.group(1).replace(".", "") + "." + (m.group(2) or "00"))
        desc = ps[i - 1]
        brand = ps[i - 2] if i >= 2 else ""
        if brand.startswith("Dein Artikel") or brand.startswith("Glückwunsch") or PRICE_RE.match(brand):
            brand = ""
        kind, size = desc, None
        sm = re.search(r",?\s*Größe:\s*(.+)$", desc)
        if sm:
            size = sm.group(1).strip()
            kind = desc[:sm.start()].strip(" ,")
        # Ohne eigene Markenzeile steht die Marke manchmal vorne im Typ ("Marke, Typ")
        if not brand and "," in kind:
            brand, kind = [x.strip() for x in kind.split(",", 1)]
        items.append({"brand": brand or "Ohne Marke", "kind": kind, "size": size, "price": price})
    if not items:
        return []
    days = _num(r"Wurde (\d+) Tage? lang", full)
    favs = _num(r"Wurde (\d+) mal favorisiert", full)
    countries = _num(r"in (\d+) Ländern", full)
    co2 = _num(r"ca\.\s*([\d.,]+)\s*kg CO2", full, float)
    water = _num(r"ca\.\s*([\d.,]+)\s*Liter Wasser", full, float)
    s_from, s_to = _storage(full, sold)
    for it in items:
        it.update({"days_listed": days, "favorites": favs, "countries": countries,
                   "co2_kg": co2, "water_l": water, "stored_from": s_from, "stored_to": s_to,
                   "category": category(it["kind"]),
                   "kids": is_kids(it["brand"], it["kind"], it["size"])})
    return items


def parse_message(raw_bytes):
    """RFC822-Bytes -> (Datum UTC, Message-ID, Betreff, Liste von Artikeln)."""
    msg = email.message_from_bytes(raw_bytes, policy=policy.default)
    try:
        sold = parsedate_to_datetime(msg["Date"]).astimezone(timezone.utc)
    except Exception:
        sold = datetime.now(timezone.utc)
    body = msg.get_body(("html", "plain"))
    html = body.get_content() if body else ""
    if body is not None and body.get_content_type() == "text/plain":
        html = "".join(f"<p>{line}</p>" for line in html.splitlines())
    return sold, (msg["Message-ID"] or "").strip(), str(msg["Subject"] or ""), parse_sale_html(html, sold)
