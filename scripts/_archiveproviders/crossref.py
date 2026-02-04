import re
import html

import requests
from urllib.parse import quote

from scripts._archiveproviders.utils import (normalize_ws, normalize_title, 
                                     seq_ratio, token_set_ratio)

UA_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120 Safari/537.36"
    )
}

def clean_crossref_text(s: str) -> str:
    """
    Convert HTML entities (&lt; etc.) to characters, strip tags (<p>),
    and normalize whitespace.
    """
    if not s:
        return ""
    s = html.unescape(s)
    s = re.sub(r"<[^>]+>", " ", s)
    return normalize_ws(s)

def crossref_lookup_by_doi(doi: str) -> dict:
    if not doi:
        return {}
    
    url = "https://api.crossref.org/works/" + quote(doi, safe="")
    params = {}
    r = requests.get(url, params=params, headers=UA_HEADERS, timeout=25)
    r.raise_for_status()

    return r.json().get("message", {}) or {}

def crossref_bibtex_by_doi(doi: str) -> str:
    """
    Get BibTeX string from Crossref endpoint
    """
    if not doi:
        return ""
    url = "https://api.crossref.org/works/" + quote(doi, safe="") + "/transform/application/x-bibtex"
    r = requests.get(url, headers=UA_HEADERS, timeout=25)
    if r.status_code != 200:
        return ""
    return r.text.strip()

def crossref_best(title: str, year: str, venue: str, rows: int = 5) -> dict:
    """
    Crossref search attempt by title
    """
    title_n = normalize_title(title)
    if not title_n:
        return {}

    url = "https://api.crossref.org/works"
    params = {
        "query.title": title,
        "rows": rows,
    }

    r = requests.get(url, params=params, headers=UA_HEADERS, timeout=25)
    r.raise_for_status()
    data = r.json().get("message", {}) or {}
    items = data.get("items") or []

    best_item = None
    best_score = 0.0

    for it in items:
        it_title = ""
        if isinstance(it.get("title"), list) and it["title"]:
            it_title = it["title"][0]
        it_title_n = normalize_title(it_title)

        tscore = seq_ratio(title_n, it_title_n)
        if tscore < 0.88:   # fuzzy title match
            continue

        # exact year match
        it_year = ""
        issued = it.get("issued") or {}
        parts = issued.get("date-parts") or []
        if parts and isinstance(parts, list) and parts[0] and isinstance(parts[0], list):
            it_year = str(parts[0][0])

        if year and it_year and str(year) != str(it_year):
            continue
        if year and not it_year:
            continue

        # fuzzy venue match
        it_venue = ""
        ct = it.get("container-title") or []
        if ct and isinstance(ct, list) and ct[0]:
            it_venue = ct[0]
        else:
            ev = it.get("event") or {}
            it_venue = ev.get("name") or ""

        vscore = token_set_ratio(venue, it_venue)

        if venue and vscore < 0.45:
            continue

        score = (0.75 * tscore) + (0.25 * vscore)
        if score > best_score:
            best_score = score
            best_item = it

    return best_item or {}