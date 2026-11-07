#!/usr/bin/env python3
"""Verschlüsselt dist/index.html mit dem Seitenpasswort (AES-256-GCM, Schlüssel per PBKDF2-SHA256).

Übrig bleibt eine Seite mit nur einem Passwortfeld; entschlüsselt wird im Browser (WebCrypto).
Ohne Passwort sind keine Daten lesbar – auch nicht im Quelltext. Gleiches Verfahren wie im Comunio-Dashboard.
"""
import base64
import json
import os
import sys
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

sys.path.insert(0, str(Path(__file__).resolve().parent))
import crypto_store  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DIST = Path(os.environ.get("DIST_DIR", ROOT / "dist"))

LOGIN = r"""<!doctype html>
<html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<meta name="theme-color" content="#2a78d6">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="SellDash">
<meta name="application-name" content="SellDash">
<link rel="apple-touch-icon" href="icons/apple-touch-icon.png">
<link rel="icon" type="image/png" sizes="32x32" href="icons/favicon-32.png">
<link rel="icon" type="image/svg+xml" href="icons/icon.svg">
<link rel="manifest" href="manifest.webmanifest">
<title>SellDash</title>
<style>
:root{color-scheme:light dark;--bg:#f4f3f0;--panel:#fcfcfb;--fg:#0b0b0b;--muted:#52514e;--line:#d6d4cf;--accent:#2a78d6;--bad:#d03b3b}
@media (prefers-color-scheme:dark){:root{--bg:#111110;--panel:#1a1a19;--fg:#f0efec;--muted:#c3c2b7;--line:#3a3a37;--accent:#3987e5}}
body{margin:0;min-height:100vh;display:grid;place-items:center;background:var(--bg);color:var(--fg);
 font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;padding:16px;box-sizing:border-box}
form{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:22px;width:100%;max-width:340px;box-sizing:border-box}
h1{font-size:19px;margin:0 0 4px}
p{color:var(--muted);margin:0 0 16px;font-size:13px}
input[type=password]{width:100%;box-sizing:border-box;font:inherit;padding:10px 12px;border:1px solid var(--line);border-radius:9px;background:var(--bg);color:var(--fg)}
label{display:flex;gap:8px;align-items:center;font-size:13px;color:var(--muted);margin:12px 0}
button{width:100%;font:inherit;font-weight:600;padding:10px;border:0;border-radius:9px;background:var(--accent);color:#fff;cursor:pointer}
#err{color:var(--bad);font-size:13px;min-height:18px;margin-top:10px}
</style></head><body>
<form id="f" autocomplete="on">
 <img src="icons/icon-192.png" alt="" width="56" height="56" style="border-radius:13px;display:block;margin-bottom:12px">
 <h1>SellDash</h1><p>Dein Sellpy-Dashboard. Bitte Passwort eingeben.</p>
 <input type="text" name="username" value="selldash" autocomplete="username" hidden>
 <input id="pw" type="password" autocomplete="current-password" placeholder="Passwort" autofocus>
 <label><input id="rm" type="checkbox"> Auf diesem Gerät angemeldet bleiben</label>
 <button>Öffnen</button><div id="err"></div>
</form>
<script>
const P = __PAYLOAD__;
const b64 = s => Uint8Array.from(atob(s), c => c.charCodeAt(0));
const KEY_STORE = "sp-key-" + P.salt.slice(0, 12);
async function derive(pw){
  const base = await crypto.subtle.importKey("raw", new TextEncoder().encode(pw), "PBKDF2", false, ["deriveBits"]);
  const bits = await crypto.subtle.deriveBits({name:"PBKDF2", salt:b64(P.salt), iterations:P.iter, hash:"SHA-256"}, base, 256);
  return new Uint8Array(bits);
}
async function open(raw){
  const key = await crypto.subtle.importKey("raw", raw, "AES-GCM", false, ["decrypt"]);
  const plain = await crypto.subtle.decrypt({name:"AES-GCM", iv:b64(P.iv)}, key, b64(P.data));
  document.open(); document.write(new TextDecoder().decode(plain)); document.close();
}
(async () => {
  try { const k = localStorage.getItem(KEY_STORE); if (k) { await open(b64(k)); return; } }
  catch (e) { try { localStorage.removeItem(KEY_STORE); } catch (_) {} }
})();
document.getElementById("f").addEventListener("submit", async e => {
  e.preventDefault(); const err = document.getElementById("err"); err.textContent = "Entschlüssele …";
  try {
    const raw = await derive(document.getElementById("pw").value);
    if (document.getElementById("rm").checked) { try { localStorage.setItem(KEY_STORE, btoa(String.fromCharCode(...raw))); } catch (_) {} }
    await open(raw);
  } catch (x) { err.textContent = "Falsches Passwort."; }
});
</script></body></html>
"""


def main():
    pw = os.environ.get("PAGE_PASSWORD", "")
    if len(pw) < 12:
        sys.exit("PAGE_PASSWORD fehlt oder ist kürzer als 12 Zeichen.")
    src = DIST / "index.html"
    plain = src.read_bytes()
    # Salz bleibt pro Passwort gleich, damit "angemeldet bleiben" die täglichen Updates übersteht.
    salt, key = crypto_store.page_key(pw)
    iv = os.urandom(12)
    data = AESGCM(key).encrypt(iv, plain, None)
    enc = lambda b: base64.b64encode(b).decode()
    payload = json.dumps({"salt": enc(salt), "iv": enc(iv), "iter": crypto_store.ITERATIONS, "data": enc(data)})
    src.write_text(LOGIN.replace("__PAYLOAD__", payload, 1))
    print(f"ok: dist/index.html verschlüsselt ({len(plain) // 1024} KB)")


if __name__ == "__main__":
    main()
