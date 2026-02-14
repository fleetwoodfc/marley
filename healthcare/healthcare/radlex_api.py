import json
import requests
from bs4 import BeautifulSoup

RADLEX_SEARCH_URL = "https://playbook.radlex.org/playbook/SearchRadlexAction"
RADLEX_WEBSERVICE_CANDIDATES = [
    "https://radlex.org/playbook_webservicesv2/get_termsV2.cfm",
    "https://www.radlex.org/playbook_webservicesv2/get_termsV2.cfm",
    "http://www.radlex.org/playbook_webservicesv2/get_termsV2.cfm",
]


def _score_and_limit(items, query, top_n=20):
    q = (query or "").strip().lower()
    q_tokens = [t for t in q.split() if t]
    scored = []

    for it in items:
        name = (it.get("name") or "").strip()
        description = (it.get("description") or "").strip()
        combined = f"{name} {description}".lower()

        score = 0.0
        if q and q in combined:
            score = 3.0
        else:
            if q_tokens and all(tok in combined for tok in q_tokens):
                score = 2.0
            elif q_tokens and any(tok in combined for tok in q_tokens):
                score = 1.0

        if score > 0:
            scored.append((score, {"rpid": it.get("rpid"), "name": name, "description": description}))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored[:top_n]]


def _parse_webservice_response(resp_text):
    """Attempt to parse a webservice response into a list of dicts.
    Accepts XML, JSON, or HTML and tries to extract rpid/name/description.
    Returns list of dicts or empty list if parsing fails.
    """
    txt = (resp_text or "").strip()
    if not txt:
        return []

    # Try JSON first
    try:
        parsed = json.loads(txt)
        # Expecting list of objects or a dict with a list under some key
        if isinstance(parsed, list):
            results = []
            for obj in parsed:
                if isinstance(obj, dict):
                    results.append({
                        "rpid": obj.get("rpid") or obj.get("id") or obj.get("code"),
                        "name": obj.get("name") or obj.get("term") or obj.get("label"),
                        "description": obj.get("description") or obj.get("def") or "",
                    })
            return results
        elif isinstance(parsed, dict):
            # find first list value
            for v in parsed.values():
                if isinstance(v, list):
                    return _parse_webservice_response(json.dumps(v))
    except Exception:
        pass

    # Try XML parsing for <term> elements
    try:
        soup = BeautifulSoup(txt, "xml")
        terms = soup.find_all("term")
        results = []
        for t in terms:
            rpid = t.find("rpid") or t.get("rpid")
            name = t.find("name") or t.find("term") or t.get("name")
            desc = t.find("description") or t.get("description")
            results.append({
                "rpid": rpid.get_text(strip=True) if getattr(rpid, "get_text", None) else (rpid or ""),
                "name": name.get_text(strip=True) if getattr(name, "get_text", None) else (name or ""),
                "description": desc.get_text(strip=True) if getattr(desc, "get_text", None) else (desc or ""),
            })
        if results:
            return results
    except Exception:
        pass

    # Last resort: parse as HTML table rows (similar to scraping fallback)
    try:
        soup = BeautifulSoup(txt, "html.parser")
        rows = soup.select("tr.tr_data") or soup.select("table tr")
        results = []
        for row in rows:
            cols = row.find_all("td")
            if len(cols) >= 4:
                rpid = cols[0].get_text(strip=True)
                name = cols[2].get_text(strip=True)
                description = cols[3].get_text(strip=True)
                results.append({"rpid": rpid, "name": name, "description": description})
        return results
    except Exception:
        return []


def _try_webservice(query, timeout=5):
    headers = {"User-Agent": "Frappe-Radlex/1.0"}
    for base in RADLEX_WEBSERVICE_CANDIDATES:
        try:
            resp = requests.get(base, params={"term": query}, timeout=timeout, headers=headers)
        except Exception:
            continue
        if resp is None:
            continue
        if resp.status_code != 200:
            continue

        parsed = _parse_webservice_response(resp.text)
        if parsed:
            return parsed
    return []


def search_radlex(query):
    """Search RadLex Playbook for a given query string.
    Try the Playbook webservice first; if unavailable or returns no results,
    fall back to HTML scraping + scoring.
    Returns a list of dicts: {rpid, name, description}
    """
    # 1) Try webservice endpoints
    try:
        ws_results = _try_webservice(query)
        if ws_results:
            return _score_and_limit(ws_results, query)
    except Exception:
        # be tolerant — fall back to scraping
        pass

    # 2) Fallback: existing HTML scraping logic against the SearchRadlexAction
    try:
        resp = requests.post(RADLEX_SEARCH_URL, data={"searchString": query}, timeout=10)
        resp.raise_for_status()
    except Exception:
        return []

    soup = BeautifulSoup(resp.text, "html.parser")

    rows = soup.select("tr.tr_data")
    if not rows:
        rows = soup.select("table tr")

    items = []
    for row in rows:
        cols = row.find_all("td")
        if len(cols) >= 4:
            rpid = cols[0].get_text(strip=True)
            name = cols[2].get_text(strip=True)
            description = cols[3].get_text(strip=True)
            items.append({"rpid": rpid, "name": name, "description": description})

    return _score_and_limit(items, query)


if __name__ == "__main__":
    for result in search_radlex("CT Chest"):
        print(result)
