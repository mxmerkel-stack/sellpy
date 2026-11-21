#!/usr/bin/env python3
"""Temporär: Likes und Preissenkungs-Angaben bei eigenen Artikeln suchen."""
import json, sys, re
from pathlib import Path
from playwright.sync_api import sync_playwright
sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_sellpy as F

out = {"ops": {}, "alg": [], "intro": None, "keys": {}}
KEYRE = re.compile(r"drop|reduc|discount|senk|nextPrice|favou?rit|like|schedule|autoPrice|price", re.I)

def walk(o, path, acc):
    if isinstance(o, dict):
        for k, v in o.items():
            p = f"{path}.{k}"
            if KEYRE.search(k): acc[p] = json.dumps(v)[:200]
            walk(v, p, acc)
    elif isinstance(o, list):
        for v in o[:3]: walk(v, path + "[]", acc)

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    ctx = b.new_context(locale="de-DE", timezone_id="Europe/Berlin", viewport={"width": 1280, "height": 900},
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")
    page = ctx.new_page(); session = {}; alg = {}; cur = {"u": ""}
    def on_req(r):
        t = r.headers.get("x-parse-session-token")
        if t and not session: session.update(token=t, app=r.headers.get("x-parse-application-id"))
        if "algolia.net/1/indexes" in r.url and not alg and "favorites" in cur["u"]:
            alg.update(url=r.url, index=(json.loads(r.post_data or "{}").get("requests") or [{}])[0].get("indexName"))
    def on_resp(r):
        if "graphql" not in r.url: return
        try: body = r.text(); req = r.request.post_data or ""
        except Exception: return
        m = re.search(r'"operationName":"(\w+)"', req); op = (m.group(1) if m else "?")
        try: j = json.loads(body)
        except Exception: return
        acc = {}; walk(j, "", acc)
        if acc: out["ops"].setdefault(cur["u"] + " :: " + op, {}).update(acc)
    page.on("request", on_req); page.on("response", on_resp)
    F.login(page)
    for path in ["/sales", "/my-shopping/favorites"]:
        cur["u"] = path
        page.goto(F.BASE + path, wait_until="domcontentloaded", timeout=60000); page.wait_for_timeout(6000)
    # Detailseite eines eigenen Online-Artikels öffnen
    s = F.Sellpy(page, session["token"], session["app"])
    uid = s.q("query { currentUser { objectId } }")["data"]["currentUser"]["objectId"]
    items = s.q("""query I($uid: ID!) { items(where: {user: {have: {objectId: {equalTo: $uid}}}, itemStatus: {equalTo: "utlagd"}}, first: 6, order: [createdAt_ASC]) {
        edges { node { objectId createdAt } } } }""", {"uid": uid}, allow_errors=True)
    ids = [e["node"]["objectId"] for e in ((items.get("data") or {}).get("items") or {}).get("edges", [])]
    out["ids"] = ids
    # Schema-Abfrage zu Item
    try:
        intro = s.q('query { __type(name: "Item") { fields { name } } }', allow_errors=True)
        out["intro"] = [f["name"] for f in (((intro.get("data") or {}).get("__type") or {}).get("fields") or [])]
    except Exception as e:
        out["intro"] = ["fehler " + str(e)[:80]]
    if alg.get("index") and ids:
        flt = "(" + " OR ".join(f"objectID:{x}" for x in ids) + ")"
        r = page.request.post(alg["url"], headers={"content-type": "application/json"}, timeout=60000,
                              data=json.dumps({"requests": [{"indexName": alg["index"], "hitsPerPage": 20, "filters": flt}]}))
        try:
            for h in r.json()["results"][0]["hits"]:
                h.pop("images", None); h.pop("_highlightResult", None)
                out["alg"].append(h)
        except Exception:
            out["keys"]["alg_error"] = f"{r.status} {r.text()[:300]} {alg}"
    for i in ids[:2]:
        cur["u"] = "item"
        try:
            page.goto(F.BASE + f"/sales/{i}", wait_until="domcontentloaded", timeout=40000); page.wait_for_timeout(5000)
            out["keys"]["page_" + i] = (page.inner_text("body") or "")[:1500]
        except Exception as e: out["keys"]["page_" + i] = str(e)[:100]
    b.close()
Path("data").mkdir(exist_ok=True)
Path("data/probe.json").write_text(json.dumps(out, ensure_ascii=False))
print("ids", len(out["ids"]), "alg", len(out["alg"]), "ops", len(out["ops"]), "intro", len(out["intro"] or []))
