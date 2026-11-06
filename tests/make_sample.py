#!/usr/bin/env python3
"""Erzeugt erfundene Beispieldaten in data/, um die Seite ohne Gmail zu testen."""
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
random.seed(7)

BRANDS = ["Hugo Boss", "Lacoste", "Tommy Hilfiger", "Esprit", "H&M", "Mini Boden", "s.Oliver", "Levi's",
          "Olymp", "Eton", "The North Face", "Zara", "Ohne Marke", "Marc O'Polo", "Jack & Jones"]
KINDS = [("Hemd", "Hemden & Blusen", ["L", "XL", "42", "41"]), ("Jeans", "Hosen & Jeans", ["32/32", "W33"]),
         ("Kapuzenpullover", "Pullover & Strick", ["M", "L"]), ("T-Shirt", "Shirts & Tops", ["M", "L"]),
         ("Softshelljacke", "Jacken & Mäntel", ["L"]), ("Cordhose", "Hosen & Jeans", ["74", "86", "104"]),
         ("Body", "Sonstiges", ["62", "68"]), ("Krawatte", "Accessoires", [None]), ("Blazer", "Jacken & Mäntel", ["50", "102"])]


def main():
    now = datetime.now(timezone.utc)
    sales = []
    for _ in range(64):
        kind, cat, sizes = random.choice(KINDS)
        size = random.choice(sizes)
        kids = size in ("62", "68", "74", "86", "104")
        sold = now - timedelta(days=random.betavariate(1.3, 1.1) * 105, hours=random.random() * 24)
        days = random.randint(2, 170)
        sales.append({"brand": random.choice(BRANDS), "kind": kind, "size": size, "category": cat, "kids": kids,
                      "price": round(random.choice([2.5, 3.5, 4, 5, 6.5, 8, 9.5, 12, 15, 19, 24, 39]) * (0.6 if kids else 1), 2),
                      "days_listed": days, "favorites": random.randint(0, 25), "countries": 24,
                      "co2_kg": random.choice([0.5, 1, 2, 4]), "water_l": random.choice([200, 552, 1100, 2700]),
                      "stored_from": (sold - timedelta(days=days)).date().isoformat(), "stored_to": sold.date().isoformat(),
                      "sold_at": sold.isoformat()})
    events = []
    for kind, n in [("bag_ordered", 7), ("bag_arrived", 6), ("sale_started", 5), ("new_listings", 14),
                    ("last_chance", 2), ("sale_ended", 1), ("bag_sent", 3), ("purchase", 4)]:
        for _ in range(n):
            events.append({"type": kind, "at": (now - timedelta(days=random.random() * 110)).isoformat()})
    DATA.mkdir(exist_ok=True)
    (DATA / "sales.json").write_text(json.dumps(sorted(sales, key=lambda s: s["sold_at"]), ensure_ascii=False))
    (DATA / "events.json").write_text(json.dumps(sorted(events, key=lambda e: e["at"])))
    (DATA / "meta.json").write_text(json.dumps({"parse_failed": 0}))
    print(f"ok: {len(sales)} erfundene Verkäufe in data/")


if __name__ == "__main__":
    main()
