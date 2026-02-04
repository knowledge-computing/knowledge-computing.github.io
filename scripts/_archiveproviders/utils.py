import re
import string

import bibtexparser

def normalize_ws(s: str) -> str:
    """
    Remove whitespace
    """
    return re.sub(r"\s+", " ", (s or "")).strip()

def normalize_title(s: str) -> str:
    """
    Title normalization
    """
    s = (s or "").strip().lower()
    s = s.replace("’", "'")
    s = "".join(ch for ch in s if ch not in string.punctuation)
    s = normalize_ws(s)
    return s

def seq_ratio(a: str, b: str) -> float:
    from difflib import SequenceMatcher
    return SequenceMatcher(None, a, b).ratio()

def token_set_ratio(a: str, b: str) -> float:
    a = normalize_ws((a or "").lower())
    b = normalize_ws((b or "").lower())
    if not a or not b:
        return 0.0
    ta = set(a.split())
    tb = set(b.split())
    inter = ta & tb
    if not inter:
        return 0.0
    return len(inter) / max(1, len(ta | tb))

def prefer_doi_key(entry: dict) -> None:
    doi = (entry.get("doi") or "").strip()
    if doi:
        entry["ID"] = doi

def normalize_doi_url(entry: dict) -> None:
    doi = (entry.get("doi") or "").strip()
    if doi:
        entry["url"] = f"https://doi.org/{doi}"

def normalize_authors_to_bibtex(author_str: str) -> str:
    """
    Author list normalization to bibtext format
    """
    s = normalize_ws(author_str)
    if not s:
        return ""
    
    if re.search(r"\s+and\s+", s):  # Just and case - normal
        return s

    last_first_hits = len(re.findall(r"\b\w+,\s*\w+", s))
    if last_first_hits == 0 and "," in s:
        parts = [p.strip() for p in s.split(",") if p.strip()]
        if len(parts) >= 2:
            return " and ".join(parts)
    return s

def make_bib_key(authors_bibtex: str, year: str, title: str) -> str:
    """
    firstauthorlastnameYEAR_shorttitle
    """
    y = re.sub(r"\D", "", year or "")
    y = y[:4] if len(y) >= 4 else "nd"

    first = ""
    if authors_bibtex:
        first = authors_bibtex.split(" and ", 1)[0].strip()
        if "," in first:
            first = first.split(",", 1)[0].strip()
        else:
            toks = first.split()
            if toks:
                first = toks[-1]
    first = re.sub(r"[^A-Za-z0-9]+", "", first) or "anon"

    t = normalize_title(title)
    t = re.sub(r"[^a-z0-9 ]+", "", t)
    t = "_".join(t.split()[:6]) if t else "untitled"

    return f"{first}{y}_{t}"

def parse_first_bibtex_entry(bibtex_str: str) -> dict:
    if not bibtex_str:
        return {}
    try:
        db = bibtexparser.loads(bibtex_str)
    except Exception:
        return {}
    if not getattr(db, "entries", None):
        return {}
    e = db.entries[0]

    out = {}
    for k, v in e.items():
        if v is None:
            continue
        kk = str(k).strip()
        vv = str(v).strip()
        if kk.lower() in ("entrytype", "id"):
            out[kk.upper()] = vv
        else:
            out[kk.lower()] = vv
    return out

def merge_patch(entry: dict, patch: dict, overwrite: bool = False) -> None:
    for k, v in (patch or {}).items():
        if v is None:
            continue
        kk = k if k in ("ENTRYTYPE", "ID") else k.lower()
        if overwrite or not (entry.get(kk) or "").strip():
            entry[kk] = str(v).strip()

def build_entry_bibtex(bibtex_str: str,
                       title_fallback: str,
                       venue_fallback: str,
                       year_fallback: str,
                       link_fallback: str,
                       abstract_fallback: str = "",) -> dict:
    entry = parse_first_bibtex_entry(bibtex_str)
    if not entry:
        return {}

    merge_patch(entry, {
        "title": title_fallback,
        "year": year_fallback,
        "url": link_fallback,
    }, overwrite=False)

    if not (entry.get("journal") or entry.get("booktitle")):
        et = (entry.get("ENTRYTYPE") or "").lower()
        if et in ("inproceedings", "incollection"):
            merge_patch(entry, {"booktitle": venue_fallback}, overwrite=False)
        else:
            merge_patch(entry, {"journal": venue_fallback}, overwrite=False)

    if abstract_fallback:
        merge_patch(entry, {"abstract": abstract_fallback}, overwrite=False)

    # Prefer DOI key & DOI URL if doi exists
    prefer_doi_key(entry)
    normalize_doi_url(entry)
    return entry