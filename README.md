# Sellpy-Dashboard

Privates Dashboard für meine Verkäufe bei Sellpy: Umsatz pro Woche, Top-Marken, Kategorien,
Preise, Zeit bis zum Verkauf, Favoriten, CO₂-Ersparnis und eine durchsuchbare Liste aller Verkäufe.

**Dieses Repository enthält nur Code** – keine Daten und keine Zugangsdaten.

## So funktioniert es

1. GitHub Actions läuft automatisch zweimal täglich, außerdem auf Knopfdruck.
2. `scripts/fetch_gmail.py` meldet sich per IMAP mit einem App-Passwort bei Gmail an und liest
   die Sellpy-Mails, auch die im Papierkorb. Es wird nur gelesen, nichts verändert.
   Ausgewertet werden vor allem die Mails „Juhu, dein Artikel ist verkauft!“ (`scripts/parse_sellpy.py`).
3. Jeder Verkauf wird in einem Verlauf gespeichert, damit er nicht verloren geht, wenn Gmail den
   Papierkorb leert. Der Verlauf liegt verschlüsselt im Actions-Cache.
4. `scripts/build_site.py` baut die Seite, `scripts/encrypt_page.py` verschlüsselt sie
   (AES-256-GCM, Schlüssel per PBKDF2 aus dem Seitenpasswort).
5. Die verschlüsselte Seite wird auf GitHub Pages veröffentlicht. Ohne Passwort sieht man nur ein Eingabefeld.
   In den Actions-Logs stehen nur Anzahlen, keine Artikel.

Hinweis: Die Mails nennen den Verkaufspreis, nicht den Erlös nach Sellpy-Provision.

## Einrichtung (einmalig)

**Settings → Secrets and variables → Actions → New repository secret:**

| Name | Inhalt |
|---|---|
| `MAIL_USERNAME` | Gmail-Adresse, an die Sellpy schreibt |
| `MAIL_APP_PASSWORD` | App-Passwort dieses Gmail-Kontos (Google-Konto → Sicherheit → App-Passwörter); dasselbe wie im Comunio-Dashboard geht auch |
| `PAGE_PASSWORD` | Neues Passwort für die Seite, mindestens 12 Zeichen |

**Settings → Pages → Build and deployment → Source:** „GitHub Actions“

Danach unter **Actions → Dashboard aktualisieren → Run workflow** den ersten Lauf starten.

## Lokal testen (ohne Gmail)

```bash
pip install -r requirements.txt
python tests/make_sample.py && python scripts/build_site.py
# dist/index.html im Browser öffnen
```
