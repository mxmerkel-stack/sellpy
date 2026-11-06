#!/usr/bin/env python3
"""Baut dist/index.html aus site/template.html und data/*.json (noch unverschlüsselt)."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("DATA_DIR", ROOT / "data"))
DIST = Path(os.environ.get("DIST_DIR", ROOT / "dist"))


def read(name, default):
    p = DATA / name
    return json.loads(p.read_text()) if p.exists() else default


def main():
    payload = {
        "sales": read("sales.json", []),
        "events": read("events.json", []),
        "meta": read("meta.json", {}),
        "built_at": datetime.now(timezone.utc).isoformat(),
    }
    # "</" im JSON entschärfen, damit nichts das <script>-Tag beendet
    blob = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    html = (ROOT / "site" / "template.html").read_text().replace("__DATA__", blob, 1)
    DIST.mkdir(parents=True, exist_ok=True)
    (DIST / "index.html").write_text(html)
    print(f"ok: dist/index.html gebaut ({len(payload['sales'])} Verkäufe)")


if __name__ == "__main__":
    main()
