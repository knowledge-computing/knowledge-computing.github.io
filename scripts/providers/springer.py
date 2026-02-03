import re
import requests
from urllib.parse import quote

UA_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120 Safari/537.36"
    )
}

def springer_bibtex_by_doi(doi: str) -> str:
    if not doi:
        return ""

    base = "https://citation-needed.springer.com/v2/references/"
    params = "?flavour=citation&format=bibtex"

    # Try both raw DOI-in-path and URL-encoded DOI (some servers are picky)
    candidates = [
        base + doi + params,
        base + quote(doi, safe="") + params,
    ]

    for url in candidates:
        try:
            r = requests.get(url, headers=UA_HEADERS, timeout=25)
            if r.status_code == 200 and "@" in r.text:
                return r.text.strip()
        except Exception:
            pass

    return ""