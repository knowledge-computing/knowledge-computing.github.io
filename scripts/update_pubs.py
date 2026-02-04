import os
import argparse

import re
import time
import json
import html
import string
import requests
from datetime import datetime, timezone
from urllib.parse import quote

from tqdm import tqdm

from scholarly import scholarly
import bibtexparser
from bibtexparser.bwriter import BibTexWriter

from scripts._update_utils import (write_to_bibtex,   # Some defaults,
                                   normalize_ws, normalize_title, normalize_authors_to_bibtex, normalize_doi_url,   # Normalization stuff
                                   strip_html_tags, clean_crossref_text,    # HTML removal
                                   seq_ratio, token_set_ratio       # Fuzzy matching
                                   )

# -----------------------------
# Config
# -----------------------------

DOI_RE = re.compile(r"(10\.\d{4,9}/[-._;()/:A-Z0-9]+)", re.I)

ARXIV_ID_RE = re.compile(
    r"(?:arxiv\.org/(?:abs|pdf)/)(?P<id>(?:\d{4}\.\d{4,5}|[a-z\-]+/\d{7})(?:v\d+)?)",
    re.I,
)

# If you see "arxiv" anywhere in venue/citation, treat as arXiv
ARXIV_WORD_RE = re.compile(r"\barxiv\b", re.I)

UA_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120 Safari/537.36"
    )
}



def extract_doi(text: str) -> str:
    if not text:
        return ""
    m = DOI_RE.search(text)
    return m.group(1) if m else ""


def make_bib_key(authors_bibtex: str, year: str, title: str) -> str:
    """
    Build a stable-ish BibTeX key: firstauthorlastnameYEAR_shorttitle
    """
    y = re.sub(r"\D", "", year or "")
    y = y[:4] if len(y) >= 4 else "nd"

    # First author last name
    first = ""
    if authors_bibtex:
        first = authors_bibtex.split(" and ", 1)[0].strip()
        # handle "Last, First"
        if "," in first:
            first = first.split(",", 1)[0].strip()
        else:
            # "First Last"
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

def prefer_doi_key(entry: dict) -> None:
    doi = (entry.get("doi") or "").strip()
    if doi:
        entry["ID"] = doi


def merge_patch(entry: dict, patch: dict, overwrite: bool = False) -> None:
    """Merge patch fields without dropping anything."""
    for k, v in (patch or {}).items():
        if v is None:
            continue
        kk = k if k in ("ENTRYTYPE", "ID") else k.lower()
        if overwrite or not (entry.get(kk) or "").strip():
            entry[kk] = str(v).strip()


def bibtex_to_fields(bibtex_str: str) -> dict:
    """Parse a single-entry BibTeX string into a normalized dict of fields."""
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



def pick_title(pub: dict) -> str:
    bib = pub.get("bib", {}) or {}
    title = normalize_ws(bib.get("title") or "")
    author = normalize_ws(bib.get("author") or "")
    year = bib.get("pub_year") or bib.get("year") or ""
    year = str(y).strip() if y is not None else ""
    return normalize_ws(bib.get("title") or "")


def pick_authors(pub: dict) -> str:
    bib = pub.get("bib", {}) or {}
    return normalize_ws(bib.get("author") or "")


def pick_year(pub: dict) -> str:
    bib = pub.get("bib", {}) or {}
    y = bib.get("pub_year") or bib.get("year") or ""
    return str(y).strip() if y is not None else ""


def pick_venue(pub: dict) -> str:
    """
    Your previous venue parsing relied on bib['citation'].
    Keep that fallback approach because it tends to exist.
    """
    bib = pub.get("bib", {}) or {}
    cit = normalize_ws(bib.get("citation") or "")
    if not cit:
        return ""
    head = cit.split(",", 1)[0].strip()
    if head and head.lower() != "unknown":
        return head
    # strip trailing year
    cit2 = re.sub(r"\s*\(?\b(19|20)\d{2}\b\)?\s*$", "", cit).strip()
    return cit2


def pick_link(pub: dict) -> str:
    bib = pub.get("bib", {}) or {}
    return normalize_ws(pub.get("pub_url") or bib.get("url") or "")

# Springer
def springer_bibtex_by_doi(doi: str) -> str:
    """
    Fetch BibTeX from Springer's citation export service (for chapters/articles).
    Works great for 10.1007/* DOIs (LNCS chapters, etc.).
    """
    if not doi:
        return ""

    # Springer shows .BIB links like:
    # https://citation-needed.springer.com/v2/references/10.1007/978-3-032-09530-5_26?flavour=citation&format=bibtex
    # (found on the chapter page under "Download citation")  :contentReference[oaicite:2]{index=2}

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

# -----------------------------
# Scholarly BibTeX fetch (fallback)
# -----------------------------
def get_bibtex_with_fallback(p_full: dict, title: str) -> str:
    # 1) Try directly
    try:
        s = scholarly.bibtex(p_full)
        if s:
            return s
    except Exception:
        pass

    # 2) Fallback: search by title
    try:
        q = scholarly.search_pubs(title)
        pub2 = next(q, None)
        if not pub2:
            return ""
        pub2 = scholarly.fill(pub2)
        return scholarly.bibtex(pub2) or ""
    except Exception:
        return ""


# -----------------------------
# arXiv helpers
# -----------------------------
def extract_arxiv_id_from_any(text: str) -> str:
    """Try to find an arXiv id in a URL, bibtex, etc."""
    if not text:
        return ""
    m = ARXIV_ID_RE.search(text)
    if m:
        return m.group("id")
    # Also handle explicit "arXiv:XXXX.XXXXX"
    m2 = re.search(r"\barxiv:\s*([0-9]{4}\.[0-9]{4,5}(?:v\d+)?)\b", text, re.I)
    if m2:
        return m2.group(1)
    return ""


def arxiv_api_query_by_id(arxiv_id: str) -> dict:
    """
    Fetch metadata from arXiv API (Atom).
    Returns dict with: title, authors (bibtex 'and'), year, url, abstract, primary_category
    """
    url = "http://export.arxiv.org/api/query"
    params = {"id_list": arxiv_id}
    r = requests.get(url, params=params, headers=UA_HEADERS, timeout=25)
    r.raise_for_status()
    xml = r.text

    # Very small XML parsing with regexes (keeps deps minimal)
    def xml_text(tag: str) -> str:
        m = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", xml, flags=re.S | re.I)
        return html.unescape(m.group(1)).strip() if m else ""

    title = normalize_ws(xml_text("title"))
    # API includes feed title + entry title; prefer the entry title.
    # Try to capture the *last* <title> which is usually entry title.
    titles = re.findall(r"<title[^>]*>(.*?)</title>", xml, flags=re.S | re.I)
    if titles:
        title = normalize_ws(html.unescape(titles[-1]))

    summary = normalize_ws(xml_text("summary"))
    published = xml_text("published")  # ISO date
    year = published[:4] if published[:4].isdigit() else ""

    # Authors: multiple <name> inside <author>
    names = re.findall(r"<author>\s*<name>(.*?)</name>\s*</author>", xml, flags=re.S | re.I)
    authors = " and ".join(normalize_ws(html.unescape(n)) for n in names if normalize_ws(n))

    # id url
    entry_id = xml_text("id")
    entry_id = normalize_ws(entry_id)

    # primary category
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
    # optionally bias with author
    if first_author:
        fa = first_author.split(",", 1)[0].split()[-1]
        search = f'{search} AND au:{fa}'

    url = "http://export.arxiv.org/api/query"
    params = {"search_query": search, "start": 0, "max_results": 5}
    r = requests.get(url, params=params, headers=UA_HEADERS, timeout=25)
    r.raise_for_status()
    xml = r.text

    # Split entries
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
            # extract id
            mid = re.search(r"<id[^>]*>(.*?)</id>", e, flags=re.S | re.I)
            eid = normalize_ws(html.unescape(mid.group(1))) if mid else ""
            # arxiv id from url
            arxiv_id = extract_arxiv_id_from_any(eid) or ""
            best_score = score
            best = {"arxiv_id": arxiv_id, "entry_url": eid, "matched_title": etitle, "score": score}

    return best or {}

def build_entry_keep_all_fields(
    bibtex_str: str,
    title_fallback: str,
    venue_fallback: str,
    year_fallback: str,
    link_fallback: str,
    abstract_fallback: str = "",
) -> dict:
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


def build_arxiv_bib_entry(base_title: str, base_year: str, base_venue: str, base_link: str, authors_guess: str,
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

    # Add abstract (requested)
    if arxiv_meta.get("abstract"):
        entry["abstract"] = arxiv_meta["abstract"]

    # Bib key
    entry["ID"] = make_bib_key(entry.get("author", ""), entry.get("year", ""), entry.get("title", ""))

    return entry


# -----------------------------
# Crossref helpers
# -----------------------------
def crossref_lookup_by_doi(doi: str) -> dict:
    if not doi:
        return {}
    url = "https://api.crossref.org/works/" + quote(doi, safe="")
    params = {}
    r = requests.get(url, params=params, headers=UA_HEADERS, timeout=25)
    r.raise_for_status()
    return r.json().get("message", {}) or {}


def crossref_search_best(title: str, year: str, venue: str, rows: int = 5) -> dict:
    """
    Search Crossref by title, pick best match that passes:
      - title similarity (case-insensitive)
      - venue fuzzy similarity (container-title or event name)
      - year equality
    Returns message item (includes DOI, etc.) or {}.
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

        # title must be strong match
        tscore = seq_ratio(title_n, it_title_n)
        if tscore < 0.88:
            continue

        # year must match exactly (requested)
        it_year = ""
        issued = it.get("issued") or {}
        parts = issued.get("date-parts") or []
        if parts and isinstance(parts, list) and parts[0] and isinstance(parts[0], list):
            it_year = str(parts[0][0])

        if year and it_year and str(year) != str(it_year):
            continue
        if year and not it_year:
            continue

        # venue fuzzy match
        it_venue = ""
        ct = it.get("container-title") or []
        if ct and isinstance(ct, list) and ct[0]:
            it_venue = ct[0]
        else:
            ev = it.get("event") or {}
            it_venue = ev.get("name") or ""

        vscore = token_set_ratio(venue, it_venue)
        # If you have no venue, don't block; otherwise require some overlap
        if venue and vscore < 0.45:
            continue

        score = (0.75 * tscore) + (0.25 * vscore)
        if score > best_score:
            best_score = score
            best_item = it

    return best_item or {}

def acm_dl_bibtex_by_doi(doi: str) -> str:
    """
    Best-effort attempt to download BibTeX from ACM DL for 10.1145/* DOIs.
    This endpoint sometimes changes / may require access; keep it best-effort.
    """
    if not doi.startswith("10.1145/"):
        return ""
    # Common ACM export endpoint pattern:
    url = "https://dl.acm.org/action/downloadCitation"
    params = {"doi": doi, "format": "bibtex"}
    try:
        r = requests.get(url, params=params, headers=UA_HEADERS, timeout=25)
        if r.status_code == 200 and "@" in r.text:
            return r.text.strip()
    except Exception:
        pass
    return ""


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


def build_crossref_entry_from_bibtex(bibtex_str: str, title_fallback: str, venue_fallback: str,
                                    year_fallback: str, link_fallback: str) -> dict:
    """
    Parse Crossref-provided BibTeX and optionally patch missing fields.
    """
    fields = bibtex_to_fields(bibtex_str)
    if not fields:
        return {}

    entrytype = fields.get("entrytype") or "article"
    bib_id = fields.get("id") or ""

    title = fields.get("title") or title_fallback
    author = normalize_authors_to_bibtex(fields.get("author") or "")
    if not author:
        author = normalize_authors_to_bibtex(fields.get("authors") or "")

    year = fields.get("year") or year_fallback

    # venue can be journal/booktitle
    venue = fields.get("journal") or fields.get("booktitle") or venue_fallback

    url = fields.get("url") or link_fallback
    doi = fields.get("doi") or ""

    out = {
        "ENTRYTYPE": entrytype,
        "title": title,
        "author": author,
        "year": year,
    }
    if venue:
        # Keep as journal if entry looks like article; otherwise booktitle.
        if entrytype.lower() in ("article", "inproceedings", "incollection", "misc"):
            # Prefer booktitle for inproceedings/incollection
            if entrytype.lower() in ("inproceedings", "incollection"):
                out["booktitle"] = venue
            else:
                out["journal"] = venue
        else:
            out["journal"] = venue

    if doi:
        out["doi"] = doi
    if url:
        out["url"] = url

    # Keep Crossref key if present; else compute one.
    out["ID"] = bib_id or make_bib_key(out.get("author", ""), out.get("year", ""), out.get("title", ""))

    # Crossref sometimes carries abstract in the JSON message, but not in BibTeX.
    # If you want it, you can add it later when you have the message dict.
    return out


# -----------------------------
# Main
# -----------------------------
def main(scholar_id:str,
         year_window:int,
         outpath:str,):
    this_year = datetime.now(timezone.utc).year
    allowed_years = {this_year - i for i in range(year_window)}  # e.g., {2026, 2025}

    author = scholarly.search_author_id(scholar_id)
    author = scholarly.fill(author, sortby="year")

    entries = []

    pubs = author.get("publications") or []
    for idx, p in enumerate(pubs):
        # Fill each pub (may fail / rate-limited)
        try:
            p_full = scholarly.fill(p)
        except Exception:
            p_full = p

        title = pick_title(p_full)
        if not title:
            continue

        year = pick_year(p_full)
        try:
            y_int = int(year)
        except Exception:
            continue
        if y_int not in allowed_years:
            break

        print(f"Doing for {idx}")

        authors = pick_authors(p_full)
        venue = pick_venue(p_full)
        link = pick_link(p_full)

        # Pull scholar bibtex (still useful as fallback, DOI extraction, etc.)
        scholar_bibtex = ""
        scholar_fields = {}
        try:
            scholar_bibtex = get_bibtex_with_fallback(p_full, title=title)
            scholar_fields = bibtex_to_fields(scholar_bibtex)
        except Exception:
            scholar_bibtex = ""
            scholar_fields = {}

        # Decide arXiv
        is_arxiv = False
        if ARXIV_WORD_RE.search(venue or ""):
            is_arxiv = True
        else:
            # also look in scholar citation string / bibtex / link
            bib_cit = normalize_ws((p_full.get("bib", {}) or {}).get("citation") or "")
            if ARXIV_WORD_RE.search(bib_cit) or ARXIV_WORD_RE.search(scholar_bibtex) or ARXIV_WORD_RE.search(link):
                is_arxiv = True

        if is_arxiv:
            # try to get arxiv id directly
            arxiv_id = (
                extract_arxiv_id_from_any(link)
                or extract_arxiv_id_from_any(scholar_bibtex)
                or extract_arxiv_id_from_any((p_full.get("bib", {}) or {}).get("citation") or "")
            )
            arxiv_meta = {}
            if arxiv_id:
                try:
                    arxiv_meta = arxiv_api_query_by_id(arxiv_id)
                except Exception:
                    arxiv_meta = {}
            else:
                # search by title
                try:
                    best = arxiv_find_best_by_title(title, first_author=authors)
                    if best.get("arxiv_id"):
                        arxiv_meta = arxiv_api_query_by_id(best["arxiv_id"])
                except Exception:
                    arxiv_meta = {}

            entry = build_arxiv_bib_entry(
                base_title=title,
                base_year=year,
                base_venue=venue,
                base_link=link,
                authors_guess=authors,
                arxiv_meta=arxiv_meta,
            )
            entries.append(entry)
            time.sleep(1.0)
            continue

        # Not arXiv -> prefer Crossref (with validation), else scholarly bibtex, else minimal entry.
        chosen_entry = {}

        # 1) Try Crossref via DOI if we can extract it
        doi = (
            extract_doi(link)
            or extract_doi(scholar_bibtex)
            or extract_doi(json.dumps(scholar_fields, ensure_ascii=False))
        )

        acm_bib = acm_dl_bibtex_by_doi(doi) if doi else ""
        if acm_bib:
            chosen_entry = build_entry_keep_all_fields(
                acm_bib,
                title_fallback=title,
                venue_fallback=venue,
                year_fallback=year,
                link_fallback=link,
                abstract_fallback="",  # ACM BibTeX sometimes includes abstract; if it does, keep_all preserves it
            )

        if not chosen_entry and doi and doi.startswith("10.1007/"):
            sp_bib = springer_bibtex_by_doi(doi)
            if sp_bib:
                chosen_entry = build_entry_keep_all_fields(
                    sp_bib,
                    title_fallback=title,
                    venue_fallback=venue,
                    year_fallback=year,
                    link_fallback=link,
                    abstract_fallback="",  # Springer bibtex usually won’t include abstract
                )

        crossref_bib = ""
        crossref_msg = {}

        if not chosen_entry and doi:
            try:
                # Validate year & venue/title using the Crossref message too (stronger)
                crossref_msg = crossref_lookup_by_doi(doi)
                # Basic checks
                cr_title = ""
                if isinstance(crossref_msg.get("title"), list) and crossref_msg["title"]:
                    cr_title = crossref_msg["title"][0]
                cr_year = ""
                issued = crossref_msg.get("issued") or {}
                parts = issued.get("date-parts") or []
                if parts and parts[0] and isinstance(parts[0], list):
                    cr_year = str(parts[0][0])

                cr_venue = ""
                ct = crossref_msg.get("container-title") or []
                if ct and isinstance(ct, list) and ct[0]:
                    cr_venue = ct[0]
                else:
                    ev = crossref_msg.get("event") or {}
                    cr_venue = ev.get("name") or ""

                title_ok = seq_ratio(normalize_title(title), normalize_title(cr_title)) >= 0.88
                year_ok = (not year) or (cr_year and str(cr_year) == str(year))
                venue_ok = (not venue) or (token_set_ratio(venue, cr_venue) >= 0.45)

                if title_ok and year_ok and venue_ok:
                    crossref_bib = crossref_bibtex_transform(doi)
            except Exception:
                crossref_bib = ""
                crossref_msg = {}

        # 2) If no DOI path worked, search Crossref by title and validate
        if not crossref_bib:
            try:
                best = crossref_search_best(title=title, year=year, venue=venue, rows=5)
                best_doi = (best.get("DOI") or "").strip()
                if best_doi:
                    crossref_bib = crossref_bibtex_transform(best_doi)
                    # also fetch message if you want abstract etc.
                    try:
                        crossref_msg = crossref_lookup_by_doi(best_doi)
                    except Exception:
                        crossref_msg = {}
            except Exception:
                crossref_bib = ""

        # 3) Build entry from Crossref bibtex if available
        if crossref_bib:
            cr_abs = strip_html_tags(crossref_msg.get("abstract") or "")
            chosen_entry = build_entry_keep_all_fields(
                crossref_bib,
                title_fallback=title,
                venue_fallback=venue,
                year_fallback=year,
                link_fallback=link,
                abstract_fallback=cr_abs,
            )
            # If Crossref JSON has abstract, optionally include it (nice-to-have)
            cr_abs = strip_html_tags(crossref_msg.get("abstract") or "")
            if cr_abs:
                chosen_entry["abstract"] = cr_abs

        # 4) Otherwise, fall back to scholarly BibTeX -> parse into entry
        if not chosen_entry and scholar_bibtex:
            chosen_entry = build_entry_keep_all_fields(
                scholar_bibtex,
                title_fallback=title,
                venue_fallback=venue,
                year_fallback=year,
                link_fallback=link,
                abstract_fallback="",  # scholar bibtex usually won't have it
            )

        # 5) Absolute last resort: minimal entry
        if not chosen_entry:
            chosen_entry = {
                "ENTRYTYPE": "misc",
                "ID": make_bib_key(normalize_authors_to_bibtex(authors), year, title),
                "title": title,
                "author": normalize_authors_to_bibtex(authors),
                "year": year,
            }
            if venue:
                chosen_entry["howpublished"] = venue
            if link:
                chosen_entry["url"] = link

        entries.append(chosen_entry)
        time.sleep(1.0)

    write_to_bibtex(entries, outpath,
                    ["AUTO-GENERATED FILE. DO NOT EDIT."],
                    bool_dict=False)

    # # Write .bib
    # db = bibtexparser.bibdatabase.BibDatabase()
    # db.entries = entries

    # writer = BibTexWriter()
    # writer.indent = "  "
    # writer.order_entries_by = None  # keep our ordering

    # out = []
    # out.append("% AUTO-GENERATED FILE. DO NOT EDIT.")
    # out.append("% Updated on " + datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
    # out.append("")
    # out.append(writer.write(db))

    # with open(outpath, "w", encoding="utf-8") as f:
    #     f.write("\n".join(out).strip() + "\n")

    # print(f"Wrote {len(entries)} BibTeX entries -> {outpath}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Google Scholar based Bib update")
    parser.add_argument('--scholar_id', type=str, required=True)
    parser.add_argument('--year_window', type=int, default=2)
    parser.add_argument('--outpath', type=str, default="./_data/pub/dynamic.bib")
    args = parser.parse_args()

    main(scholar_id=args.scholar_id,
         year_window=args.year_window,
         outpath=args.outpath)