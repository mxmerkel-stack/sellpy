"""Verschlüsselter Verlauf (AES-256-GCM, Schlüssel per PBKDF2 aus PAGE_PASSWORD).

Gmail leert den Papierkorb nach 30 Tagen. Damit gelöschte Verkaufsmails nicht aus dem
Dashboard verschwinden, wird jeder gefundene Verkauf im Verlauf gespeichert. Der Verlauf
liegt verschlüsselt im Actions-Cache, nie im Repository.
"""
import base64
import json
import os

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

ITERATIONS = 600_000


def _key(pw, purpose):
    digest = hashes.Hash(hashes.SHA256())
    digest.update(f"sellpy-dashboard:{purpose}:".encode() + pw.encode())
    salt = digest.finalize()[:16]
    return salt, PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ITERATIONS).derive(pw.encode())


def page_key(pw):
    return _key(pw, "page")


def save(path, obj, pw):
    _, key = _key(pw, "history")
    iv = os.urandom(12)
    data = AESGCM(key).encrypt(iv, json.dumps(obj, ensure_ascii=False).encode(), None)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"iv": base64.b64encode(iv).decode(), "data": base64.b64encode(data).decode()}))


def load(path, pw):
    if not path.exists():
        return None
    _, key = _key(pw, "history")
    box = json.loads(path.read_text())
    plain = AESGCM(key).decrypt(base64.b64decode(box["iv"]), base64.b64decode(box["data"]), None)
    return json.loads(plain)
