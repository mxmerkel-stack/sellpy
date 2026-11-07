# Sellpy-Dashboard

Privates Dashboard für meine Verkäufe bei Sellpy: Umsatz pro Woche, Top-Marken, Kategorien,
Preise, Zeit bis zum Verkauf, Favoriten, CO₂-Ersparnis und eine durchsuchbare Liste aller Verkäufe.

**Dieses Repository enthält nur Code** – keine Daten und keine Zugangsdaten.

## Stand

Datenquelle ist der eigene Sellpy-Login (Secrets `SELLPY_USER`, `SELLPY_PASS`).
Sellpy hat keine offizielle API. Deshalb läuft zuerst einmalig der Workflow
**„Sellpy erkunden“**: Er meldet sich im Browser an, zeichnet auf, wie Sellpy die
Verkaufsdaten ausliefert, und schreibt das Ergebnis verschlüsselt ins Log
(Passwort, E-Mail, Cookies und Tokens werden vorher entfernt). Darauf baut der
eigentliche Abruf auf, der dann täglich läuft.

Die Seite selbst wird wie beim Comunio-Dashboard mit einem Passwort verschlüsselt
(AES-256-GCM, Schlüssel per PBKDF2 aus `PAGE_PASSWORD`) und auf GitHub Pages veröffentlicht.

## Einrichtung (einmalig)

**Settings → Secrets and variables → Actions → New repository secret:**

| Name | Inhalt |
|---|---|
| `SELLPY_USER` | E-Mail-Adresse des Sellpy-Kontos |
| `SELLPY_PASS` | Sellpy-Passwort |
| `PAGE_PASSWORD` | Neues Passwort für die Dashboard-Seite, mindestens 12 Zeichen |

## Lokal testen (ohne Gmail)

```bash
pip install -r requirements.txt
python tests/make_sample.py && python scripts/build_site.py
# dist/index.html im Browser öffnen
```
