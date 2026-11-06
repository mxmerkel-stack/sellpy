#!/usr/bin/env python3
"""Holt Sellpy-Mails per IMAP aus Gmail und schreibt data/sales.json und data/events.json.

Umgebungsvariablen:
  MAIL_USERNAME      Gmail-Adresse
  MAIL_APP_PASSWORD  App-Passwort dieses Gmail-Kontos (IMAP muss aktiv sein, ist bei Gmail Standard)
  PAGE_PASSWORD      Seitenpasswort, verschlüsselt auch den Verlauf (data/history.enc)

Gelesen wird nur, nichts wird verändert (Ordner werden schreibgeschützt geöffnet, Mails bleiben ungelesen).
Durchsucht werden "Alle Nachrichten" und der Papierkorb, weil viele Verkaufsmails gelöscht sind.

Lokaler Test ohne Gmail:  python scripts/fetch_gmail.py --eml-dir pfad/zu/eml-dateien
In den Logs stehen nur Anzahlen, keine Artikel – die Actions-Logs eines öffentlichen Repos sind öffentlich.
"""
import email
import imaplib
import json
import os
import re
import sys
from datetime import timezone
from email import policy
from email.utils import parsedate_to_datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import crypto_store  # noqa: E402
from parse_sellpy import parse_message  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("DATA_DIR", ROOT / "data"))
SALE_SUBJECT = "artikel ist verkauft"

# Betreff -> Ereignis für die Zeitleiste
EVENTS = [
    ("bag_ordered", ["quittung für sellpy-taschenbestellung"]),
    ("bag_sent", ["sellpy-taschen sind auf dem weg"]),
    ("bag_arrived", ["in unserem lager angekommen"]),
    ("sale_started", ["der verkauf geht los"]),
    ("new_listings", ["bereit für den verkauf"]),
    ("last_chance", ["letzte chance"]),
    ("sale_ended", ["dein verkauf ist beendet"]),
    ("purchase", ["bestellbestätigung"]),
]


def classify(subject):
    s = subject.lower()
    if SALE_SUBJECT in s:
        return "sold"
    for name, words in EVENTS:
        if any(w in s for w in words):
            return name
    return None


def special_folders(M):
    """Findet 'Alle Nachrichten' und 'Papierkorb' unabhängig von der Sprache über die IMAP-Flags."""
    found = {}
    typ, lines = M.list()
    for raw in lines or []:
        line = raw.decode(errors="replace")
        m = re.match(r'\((?P<flags>[^)]*)\) "(?P<sep>[^"]*)" (?P<name>.+)$', line)
        if not m:
            continue
        name = m.group("name").strip()
        for flag, key in (("\\All", "all"), ("\\Trash", "trash")):
            if flag in m.group("flags"):
                found[key] = name
    return found


def fetch_imap(user, pw):
    M = imaplib.IMAP4_SSL("imap.gmail.com")
    M.login(user, pw)
    folders = special_folders(M)
    if "all" not in folders:
        folders["all"] = '"[Gmail]/All Mail"'
    raws, headers = [], []
    for key, folder in folders.items():
        typ, _ = M.select(folder, readonly=True)
        if typ != "OK":
            print(f"Ordner {key}: nicht lesbar, übersprungen")
            continue
        typ, data = M.uid("SEARCH", "X-GM-RAW", '"from:sellpy"')
        uids = data[0].split() if typ == "OK" and data and data[0] else []
        print(f"Ordner {key}: {len(uids)} Sellpy-Mails")
        for i in range(0, len(uids), 100):
            chunk = b",".join(uids[i:i + 100])
            typ, resp = M.uid("FETCH", chunk, "(BODY.PEEK[HEADER.FIELDS (SUBJECT DATE MESSAGE-ID)])")
            want = []
            for part in resp or []:
                if not isinstance(part, tuple):
                    continue
                uid = re.search(rb"UID (\d+)", part[0])
                msg = email.message_from_bytes(part[1], policy=policy.default)
                subj = str(msg["Subject"] or "")
                headers.append((subj, msg["Date"], (msg["Message-ID"] or "").strip()))
                if classify(subj) == "sold" and uid:
                    want.append(uid.group(1))
            for j in range(0, len(want), 25):
                typ, resp = M.uid("FETCH", b",".join(want[j:j + 25]), "(BODY.PEEK[])")
                raws += [p[1] for p in resp or [] if isinstance(p, tuple)]
    M.logout()
    return raws, headers


def fetch_dir(path):
    raws, headers = [], []
    for f in sorted(Path(path).glob("*.eml")):
        raw = f.read_bytes()
        msg = email.message_from_bytes(raw, policy=policy.default)
        headers.append((str(msg["Subject"] or ""), msg["Date"], (msg["Message-ID"] or "").strip()))
        if classify(str(msg["Subject"] or "")) == "sold":
            raws.append(raw)
    return raws, headers


def main():
    pw = os.environ.get("PAGE_PASSWORD", "")
    if len(pw) < 12:
        sys.exit("PAGE_PASSWORD fehlt oder ist kürzer als 12 Zeichen.")
    if "--eml-dir" in sys.argv:
        raws, headers = fetch_dir(sys.argv[sys.argv.index("--eml-dir") + 1])
    else:
        user, app_pw = os.environ.get("MAIL_USERNAME", ""), os.environ.get("MAIL_APP_PASSWORD", "")
        if not user or not app_pw:
            sys.exit("MAIL_USERNAME und MAIL_APP_PASSWORD fehlen (Repo-Secrets).")
        raws, headers = fetch_imap(user, app_pw.replace(" ", ""))

    hist_path = DATA / "history.enc"
    try:
        history = crypto_store.load(hist_path, pw) or {}
    except Exception:
        print("Verlauf nicht lesbar (anderes Seitenpasswort?) – starte neu.")
        history = {}
    sales = history.get("sales", {})
    events = history.get("events", {})
    failed = history.get("failed", {})

    new = 0
    for raw in raws:
        sold, mid, _, items = parse_message(raw)
        if not mid:
            continue
        if not items:
            failed[mid] = sold.isoformat()
            continue
        failed.pop(mid, None)
        for n, it in enumerate(items):
            key = f"{mid}#{n}"
            if key not in sales:
                new += 1
            sales[key] = {**it, "sold_at": sold.isoformat()}

    for subj, date, mid in headers:
        kind = classify(subj)
        if not kind or kind == "sold" or not mid:
            continue
        try:
            when = parsedate_to_datetime(date).astimezone(timezone.utc).isoformat()
        except Exception:
            continue
        events[mid] = {"type": kind, "at": when}

    history = {"sales": sales, "events": events, "failed": failed}
    crypto_store.save(hist_path, history, pw)
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "sales.json").write_text(json.dumps(sorted(sales.values(), key=lambda s: s["sold_at"]), ensure_ascii=False))
    (DATA / "events.json").write_text(json.dumps(sorted(events.values(), key=lambda e: e["at"]), ensure_ascii=False))
    (DATA / "meta.json").write_text(json.dumps({"parse_failed": len(failed), "mails_seen": len(headers)}))
    print(f"ok: {len(sales)} Verkäufe im Verlauf ({new} neu), {len(events)} weitere Ereignisse, "
          f"{len(failed)} Verkaufsmails nicht lesbar")


if __name__ == "__main__":
    main()
