#!/usr/bin/env python3
"""Nur für die Einrichtung: verschlüsselt eine Datei mit explore/pubkey.pem und schreibt sie ins Log.
Lesbar nur mit dem privaten Schlüssel aus der Claude-Sitzung (nicht im Repo)."""
import base64
import gzip
import json
import os
import sys
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ROOT = Path(__file__).resolve().parent.parent
blob = gzip.compress(Path(sys.argv[1]).read_bytes())
pub = serialization.load_pem_public_key((ROOT / "explore" / "pubkey.pem").read_bytes())
key, iv = AESGCM.generate_key(256), os.urandom(12)
wrapped = pub.encrypt(key, padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None))
box = base64.b64encode(json.dumps({"k": base64.b64encode(wrapped).decode(), "iv": base64.b64encode(iv).decode(),
                                   "d": base64.b64encode(AESGCM(key).encrypt(iv, blob, None)).decode()}).encode()).decode()
print("-----BEGIN EXPLORE-----")
for i in range(0, len(box), 4000):
    print(box[i:i + 4000])
print("-----END EXPLORE-----")
