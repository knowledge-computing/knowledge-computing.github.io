import requests

UA_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120 Safari/537.36"
    )
}

def acm_bibtex_by_doi(doi: str) -> str:
    """
    Bibtex from ACM
    """
    if not doi.startswith("10.1145/"):
        return ""

    url = "https://dl.acm.org/action/downloadCitation"
    params = {"doi": doi, "format": "bibtex"}
    try:
        r = requests.get(url, params=params, headers=UA_HEADERS, timeout=25)
        if r.status_code == 200 and "@" in r.text:
            return r.text.strip()
    except Exception:
        pass

    return ""