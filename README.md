# Sellpy-Dashboard

Privates Dashboard für meine Verkäufe bei Sellpy: Umsatz pro Woche, Top-Marken, Kategorien,
Preise, Zeit bis zum Verkauf, Favoriten, CO₂-Ersparnis und eine durchsuchbare Liste aller Verkäufe.

**Dieses Repository enthält nur Code** – keine Daten und keine Zugangsdaten.

## So funktioniert es

1. GitHub Actions läuft zweimal täglich, außerdem auf Knopfdruck (**Actions → Dashboard aktualisieren → Run workflow**).
2. `scripts/fetch_sellpy.py` meldet sich mit den Secrets in einem Browser bei sellpy.de an – genau wie von Hand –
   und liest mit dieser Sitzung die Daten, die auch „Meine Verkäufe“ zeigt: Artikel, Buchungen je Artikel
   (Verkaufspreis, Provision, Anzeigengebühr), Taschen und Sellpy-Credits. Es wird nur gelesen, nichts verändert.
3. Alles wird in einem Verlauf gespeichert, verschlüsselt im Actions-Cache.
4. `scripts/build_site.py` bereitet die Zahlen auf, `scripts/encrypt_page.py` verschlüsselt die Seite
   (AES-256-GCM, Schlüssel per PBKDF2 aus dem Seitenpasswort).
5. Die verschlüsselte Seite wird auf GitHub Pages veröffentlicht. Ohne Passwort sieht man nur ein Eingabefeld.
   In den Actions-Logs stehen nur Anzahlen und Feldnamen.

Sellpy hat keine offizielle API. Wenn Sellpy die Seite umbaut, kann der Abruf ausfallen – dann zeigt die Seite
weiter den letzten Stand.

## Einrichtung (einmalig)

**Settings → Secrets and variables → Actions → New repository secret:**

| Name | Inhalt |
|---|---|
| `SELLPY_USER` | E-Mail-Adresse des Sellpy-Kontos |
| `SELLPY_PASS` | Sellpy-Passwort |
| `PAGE_PASSWORD` | Neues Passwort für die Dashboard-Seite, mindestens 12 Zeichen |

**Settings → Pages → Build and deployment → Source:** „GitHub Actions“
(GitHub Pages braucht ein öffentliches Repo oder GitHub Pro.)

Danach unter **Actions → Dashboard aktualisieren → Run workflow** den ersten Lauf starten.

## Lokal testen

```bash
pip install -r requirements.txt
python scripts/build_site.py   # ohne data/sellpy.json mit leerer Seite
# dist/index.html im Browser öffnen
```
