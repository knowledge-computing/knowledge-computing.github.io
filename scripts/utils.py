from typing import List
from pathlib import Path
from datetime import datetime, timezone

import re
import html
import string

import html
import requests
from urllib.parse import quote

from scholarly import scholarly
import bibtexparser

# Basic bibtex stuff
def load(path: Path):
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        db = bibtexparser.load(f)
    return db.entries

def write_to_bibtex(entries,
                    file_path: Path,
                    auto_message: List[str],
                    bool_dict: bool=True) -> None:
    """
    Write dictionary to file_path with auto_message and date
    """
    
    db = bibtexparser.bibdatabase.BibDatabase()
    if bool_dict:
        db.entries = list(entries.values())
    else:
        db.entries = entries

    writer = bibtexparser.bwriter.BibTexWriter()
    writer.indent = "  "
    body = writer.write(db)

    ts = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    header = (
        "".join(f"% {line}\n" for line in auto_message) + 
        f"% Updated on {ts}\n\n"
    )

    file_path.write_text(header + body, encoding="utf-8")
    print(f"Wrote {file_path} with {len(db.entries)} entries.")


# Normalization stuff
def normalize_ws(s: str) -> str:
    """
    Normalizing white space
    """
    return re.sub(r"\s+", " ", (s or "")).strip()

def normalize_title(s: str) -> str:
    s = (s or "").strip().lower()
    s = s.replace("’", "'")
    s = "".join(ch for ch in s if ch not in string.punctuation)
    s = normalize_ws(s)
    return s

def normalize_authors_to_bibtex(author_str: str) -> str:
    """
    Change comma separated authors to and style
    """
    s = normalize_ws(author_str)
    if not s:
        return ""
    
    if re.search(r"\s+and\s+", s):
        return s

    last_first_hits = len(re.findall(r"\b\w+,\s*\w+", s))
    if last_first_hits == 0 and "," in s:
        parts = [p.strip() for p in s.split(",") if p.strip()]
        if len(parts) >= 2:
            return " and ".join(parts)
    return s

def normalize_doi_url(entry: dict) -> None:
    """
    dx.doi to doi
    """
    doi = (entry.get("doi") or "").strip()
    if doi:
        entry["url"] = f"https://doi.org/{doi}"

# HTML tag removal
def strip_html_tags(s: str) -> str:
    if not s:
        return ""
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    return normalize_ws(s)

def clean_crossref_text(s: str) -> str:
    """
    Converts HTML entities in Crossref text to not include them
    Only applied to Crossref
    """
    if not s:
        return ""
    s = html.unescape(s)
    s = re.sub(r"<[^>]+>", " ", s)
    return normalize_ws(s)

# Fuzzy matchers
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

# Fill in missing
def merge_patch(entry: dict, patch: dict, overwrite: bool = False) -> None:
    for k, v in (patch or {}).items():
        if v is None:
            continue
        kk = k if k in ("ENTRYTYPE", "ID") else k.lower()
        if overwrite or not (entry.get(kk) or "").strip():
            entry[kk] = str(v).strip()


# DOI stuff
DOI_RE = re.compile(r"(10\.\d{4,9}/[-._;()/:A-Z0-9]+)", re.I)
ARXIV_ID_RE = re.compile(
    r"(?:arxiv\.org/(?:abs|pdf)/)(?P<id>(?:\d{4}\.\d{4,5}|[a-z\-]+/\d{7})(?:v\d+)?)",
    re.I,
)

def extract_doi(list_text: List[str]) -> str:
    """
    Regex pattern match for DOI
    """
    for text in list_text:
        if not text:
            continue
        m = DOI_RE.search(text)

        if m:
            return m.group(1)
        
    return ""

def extract_arxiv_id(list_text: List[str]) -> str:
    """
    Regex pattern match for ArXiV
    """
    for text in list_text:
        if not text:
            continue

        m = ARXIV_ID_RE.search(text)
        if m:
            return m.group("id")

        m2 = re.search(r"\barxiv:\s*([0-9]{4}\.[0-9]{4,5}(?:v\d+)?)\b", text, re.I)
        if m2:
            return m2.group(1)
    
    return ""

def prefer_doi_key(entry: dict) -> None:
    doi = (entry.get("doi") or "").strip()
    if doi:
        entry["ID"] = doi

# Build bibtex stuff
def make_bib_key(authors_bibtex: str, year: str, title: str) -> str:
    """
    firstauthorlastnameYEAR_shorttitle
    """
    y = re.sub(r"\D", "", year or "")
    y = y[:4] if len(y) >= 4 else "nd"

    first = ""
    if authors_bibtex:
        first = authors_bibtex.split(" and ", 1)[0].strip()
        # Last, First
        if "," in first:
            first = first.split(",", 1)[0].strip()
        else:
            # First Last
            toks = first.split()
            if toks:
                first = toks[-1]
    first = re.sub(r"[^A-Za-z0-9]+", "", first) or "anon"

    t = normalize_title(title)
    t = re.sub(r"[^a-z0-9 ]+", "", t)
    t = "_".join(t.split()[:6]) if t else "untitled"

    return f"{first}{y}_{t}"

def parse_first_bibtex_entry(bibtex_str: str) -> dict:
    """
    Parses bibtex string to entry
    """
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

# Request based bibtex gets
UA_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120 Safari/537.36"
    )
}

CV_FAMILY_HOST_RE = re.compile(
    r"^https?://(?:www\.)?(?:openaccess\.thecvf\.com|thecvf\.com|ecva\.net)/",
    re.I,
)
CV_FAMILY_CONF_RE = re.compile(r"(?:CVPR|ICCV|ECCV|WACV)", re.I)
BIBTEX_ENTRY_START_RE = re.compile(
    r"@(?:article|book|booklet|conference|inbook|incollection|inproceedings|manual|"
    r"mastersthesis|misc|phdthesis|proceedings|techreport|unpublished)\s*\{",
    re.I,
)

def is_cv_family_url(url: str) -> bool:
    url = normalize_ws(url)
    return bool(url and CV_FAMILY_HOST_RE.search(url) and CV_FAMILY_CONF_RE.search(url))

def cv_family_candidate_urls(url: str) -> List[str]:
    url = normalize_ws(url)
    if not url or not is_cv_family_url(url):
        return []

    candidates = [url]

    # CVF PDF links map cleanly to paper HTML pages, which expose the BibTeX block.
    if re.search(r"/papers/.+_paper\.pdf(?:\?.*)?$", url, re.I):
        html_url = re.sub(r"/papers/", "/html/", url, flags=re.I)
        html_url = re.sub(r"_paper\.pdf(?:\?.*)?$", "_paper.html", html_url, flags=re.I)
        if html_url not in candidates:
            candidates.append(html_url)

    return candidates

def extract_bibtex_entries(text: str) -> List[str]:
    text = html.unescape(text or "")
    entries = []

    for match in BIBTEX_ENTRY_START_RE.finditer(text):
        start = match.start()
        pos = match.end() - 1
        depth = 0

        while pos < len(text):
            ch = text[pos]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    entry = text[start:pos + 1].strip()
                    if entry:
                        entries.append(entry)
                    break
            pos += 1

    return entries

def cv_family_bibtex_by_url(url: str, title: str = "") -> str:
    candidates = cv_family_candidate_urls(url)
    if not candidates:
        return ""

    expected_title = normalize_title(title)

    for candidate in candidates:
        try:
            r = requests.get(candidate, headers=UA_HEADERS, timeout=25)
            if r.status_code != 200:
                continue
            if "pdf" in (r.headers.get("Content-Type") or "").lower():
                continue
        except Exception:
            continue

        entries = extract_bibtex_entries(r.text)
        if not entries:
            continue

        if len(entries) == 1 and not expected_title:
            return entries[0]

        best_entry = ""
        best_score = 0.0
        for entry in entries:
            fields = bibtex_to_fields(entry)
            entry_title = normalize_title(fields.get("title") or "")
            if not entry_title:
                continue
            score = seq_ratio(expected_title, entry_title) if expected_title else 0.0
            if score > best_score:
                best_score = score
                best_entry = entry

        if best_entry and best_score >= 0.88:
            return best_entry

        if len(entries) == 1:
            return entries[0]

    return ""

# ACM
def acm_bibtex_by_doi(doi: str) -> str:
    """
    Build from ACM
    """
    url = "https://dl.acm.org/action/downloadCitation"
    params = {"doi": doi, "format": "bibtex"}
    try:
        r = requests.get(url, params=params, headers=UA_HEADERS, timeout=25)
        if r.status_code == 200 and "@" in r.text:
            return r.text.strip()
    except Exception:
        pass
    return ""

# Springer
def springer_bibtex_by_doi(doi: str) -> str:
    """
    Build from springer
    """
    if not doi:
        return ""

    base = "https://citation-needed.springer.com/v2/references/"
    params = "?flavour=citation&format=bibtex"

    # Try raw DOI-in-path and URL-encoded DOI
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

def crossref_bibtex_by_doi(doi: str) -> dict:
    if not doi:
        return {}
    url = "https://api.crossref.org/works/" + quote(doi, safe="")
    params = {}
    r = requests.get(url, params=params, headers=UA_HEADERS, timeout=25)
    r.raise_for_status()
    return r.json().get("message", {}) or {}

# Build entry
def build_arxiv_bib_entry(base_title: str, 
                          base_year: str, 
                          base_link: str, 
                          authors_guess: str,
                          arxiv_meta: dict) -> dict:
    """
    Build a BibTeX entry dict for arXiv including abstract.
    """
    title = arxiv_meta.get("title") or base_title
    authors = arxiv_meta.get("authors") or normalize_authors_to_bibtex(authors_guess)
    year = arxiv_meta.get("year") or base_year
    url = arxiv_meta.get("url") or base_link

    # Use @misc for arXiv
    entry = {
        "ENTRYTYPE": "misc",
        "title": title,
        "author": normalize_authors_to_bibtex(authors),
        "year": year,
        "howpublished": "arXiv",
        "url": url,
    }
    if arxiv_meta.get("primary_category"):
        entry["primaryclass"] = arxiv_meta["primary_category"]

    # Add abstract
    if arxiv_meta.get("abstract"):
        entry["abstract"] = arxiv_meta["abstract"]

    entry["ID"] = make_bib_key(entry.get("author", ""), entry.get("year", ""), entry.get("title", ""))

    return entry

def build_other_bib_entry(bibtex_str: str,
                          title_fallback: str,
                          venue_fallback: str,
                          year_fallback: str,
                          link_fallback: str,
                          abstract_fallback: str = "",) -> dict:
    entry = parse_first_bibtex_entry(bibtex_str)
    if not entry:
        return {}

    # Patch in missing basics (but do NOT remove any existing fields)
    merge_patch(entry, {
        "title": title_fallback,
        "year": year_fallback,
        "url": link_fallback,
    }, overwrite=False)

    # Killing html elements
    if entry.get("title"):
        entry["title"] = clean_crossref_text(entry["title"])

    # Venue: only patch if missing in BOTH journal/booktitle
    if not (entry.get("journal") or entry.get("booktitle")):
        # choose booktitle for inproceedings, otherwise journal
        et = (entry.get("ENTRYTYPE") or "").lower()
        if et in ("inproceedings", "incollection"):
            merge_patch(entry, {"booktitle": venue_fallback}, overwrite=False)
        else:
            merge_patch(entry, {"journal": venue_fallback}, overwrite=False)

    # Add abstract if we have it and it's not already there
    if abstract_fallback:
        merge_patch(entry, {"abstract": abstract_fallback}, overwrite=False)

    # Prefer DOI key & DOI URL if doi exists
    prefer_doi_key(entry)
    normalize_doi_url(entry)
    return entry


    
# Arxiv fetch
def arxiv_api_query_by_id(arxiv_id: str) -> dict:
    """
    Get meta from arxiv
    """
    url = "http://export.arxiv.org/api/query"
    params = {"id_list": arxiv_id}
    r = requests.get(url, params=params, headers=UA_HEADERS, timeout=25)
    r.raise_for_status()
    xml = r.text

    def xml_text(tag: str) -> str:
        m = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", xml, flags=re.S | re.I)
        return html.unescape(m.group(1)).strip() if m else ""

    title = normalize_ws(xml_text("title"))
    titles = re.findall(r"<title[^>]*>(.*?)</title>", xml, flags=re.S | re.I)
    if titles:
        title = normalize_ws(html.unescape(titles[-1]))

    summary = normalize_ws(xml_text("summary"))
    published = xml_text("published")
    year = published[:4] if published[:4].isdigit() else ""

    names = re.findall(r"<author>\s*<name>(.*?)</name>\s*</author>", xml, flags=re.S | re.I)
    authors = " and ".join(normalize_ws(html.unescape(n)) for n in names if normalize_ws(n))

    entry_id = xml_text("id")
    entry_id = normalize_ws(entry_id)

    mcat = re.search(r'<arxiv:primary_category[^>]+term="([^"]+)"', xml, flags=re.I)
    primary_cat = mcat.group(1).strip() if mcat else ""

    return {
        "title": title,
        "authors": authors,
        "year": year,
        "url": entry_id,
        "abstract": summary,
        "primary_category": primary_cat,
    }


def arxiv_find_best_by_title(title: str, first_author: str = "") -> dict:
    """
    Search arXiv API by title and pick best match.
    """
    qtitle = title.replace('"', "")
    search = f'ti:"{qtitle}"'

    if first_author:
        fa = first_author.split(",", 1)[0].split()[-1]
        search = f'{search} AND au:{fa}'

    url = "http://export.arxiv.org/api/query"
    params = {"search_query": search, "start": 0, "max_results": 5}
    r = requests.get(url, params=params, headers=UA_HEADERS, timeout=25)
    r.raise_for_status()
    xml = r.text

    entries = re.split(r"</entry>\s*", xml, flags=re.I)
    best = None
    best_score = 0.0

    for e in entries:
        if "<entry" not in e.lower():
            continue

        titles = re.findall(r"<title[^>]*>(.*?)</title>", e, flags=re.S | re.I)
        if not titles:
            continue
        etitle = normalize_ws(html.unescape(titles[-1]))

        score = seq_ratio(normalize_title(title), normalize_title(etitle))
        if score > best_score:

            mid = re.search(r"<id[^>]*>(.*?)</id>", e, flags=re.S | re.I)
            eid = normalize_ws(html.unescape(mid.group(1))) if mid else ""

            arxiv_id = extract_arxiv_id(eid) or ""
            best_score = score
            best = {"arxiv_id": arxiv_id, "entry_url": eid, "matched_title": etitle, "score": score}

    return best or {}

# Crossref fetch
def crossref_search_best(title: str, year: str, venue: str, rows: int = 5) -> dict:
    """
    Search Crossref by title, pick best match
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

        # Strong match title and year
        tscore = seq_ratio(title_n, it_title_n)
        if tscore < 0.88:
            continue

        it_year = ""
        issued = it.get("issued") or {}
        parts = issued.get("date-parts") or []
        if parts and isinstance(parts, list) and parts[0] and isinstance(parts[0], list):
            it_year = str(parts[0][0])

        if year and it_year and str(year) != str(it_year):
            continue
        if year and not it_year:
            continue

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

def crossref_bibtex_transform(doi: str) -> str:
    """
    Get BibTeX string from Crossref transform endpoint.
    """
    if not doi:
        return ""
    url = "https://api.crossref.org/works/" + quote(doi, safe="") + "/transform/application/x-bibtex"
    r = requests.get(url, headers=UA_HEADERS, timeout=25)
    if r.status_code != 200:
        return ""
    return r.text.strip()

# Scholarly fetch
def bibtex_to_fields(bibtex_str: str) -> dict:
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
        out[str(k).lower().strip()] = str(v).strip()
    return out

def get_bibtex_with_fallback(p_full: dict, title: str) -> str:
    try:    # Directly get from scholarly
        s = scholarly.bibtex(p_full)
        if s:
            return s
    except Exception:
        pass

    try:
        # Search by title
        q = scholarly.search_pubs(title)
        pub2 = next(q, None)
        if not pub2:
            return ""
        pub2 = scholarly.fill(pub2)
        return scholarly.bibtex(pub2) or ""
    except Exception:
        return ""
    
