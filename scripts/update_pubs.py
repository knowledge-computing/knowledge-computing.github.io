"""
Code to create bib list of current and past year based on Google Scholars
Argparse input scholar_id == Google Scholar ID
"""
import argparse

import os
import re
import time
from datetime import datetime, timezone 

from scholarly import scholarly

import bibtexparser
from bibtexparser.bwriter import BibTexWriter

from scripts.providers import *

# Basic configurations
OUT_BIB_PATH = "./_data/pub/dynamic.bib"

# Regex
DOI_RE = re.compile(r"(10\.\d{4,9}/[-._;()/:A-Z0-9]+)", re.I)
ARXIV_ID_RE = re.compile(
    r"(?:arxiv\.org/(?:abs|pdf)/)(?P<id>(?:\d{4}\.\d{4,5}|[a-z\-]+/\d{7})(?:v\d+)?)",
    re.I,
)
ARXIV_WORD_RE = re.compile(r"\barxiv\b", re.I)

# Request headers
UA_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120 Safari/537.36"
    )
}

def normalize_ws(s: str) -> str:
    """
    Remove whitespace
    """
    return re.sub(r"\s+", " ", (s or "")).strip()

def _return_basics(pub: dict):
    bib_tmp = pub.get("bib", {}) or {}

    title = normalize_ws(bib_tmp.get("title") or "")
    authors = normalize_ws(bib_tmp.get("author") or "")
    link = normalize_ws(pub.get("pub_url") or bib_tmp.get("url") or "")
    citation = normalize_ws(pub.get("citation") or "")

    year = str(bib_tmp.get("pub_year") or bib_tmp.get("year") or "")
    venue = ""

    return title, year, authors, venue, link, citation

def _citation_type(venue:str=None,
                   citation:str=None,
                   scholar_bibtex:str=None,
                   link:str=None,
                   doi:str=None) -> str:
    """
    Determine citation type to pass determine which website for bib extraction to use
    """
    if ARXIV_WORD_RE.search(venue or "") or \
       ARXIV_WORD_RE.search(citation) or \
       ARXIV_WORD_RE.search(scholar_bibtex) or \
       ARXIV_WORD_RE.search(link):
         return 'arxiv'
    elif doi.startswith("10.1145/"):
        return 'acm'
    elif doi.startswith("10.1007/"):
        return 'springer'
    
    return 'fallback'

def main(scholar_id:str,
         year_window:int) -> None:
    current_year = datetime.now(timezone.utc).year
    allowed_years = {current_year - i for i in range(year_window)}

    # Publication drag through scholarly
    author = scholarly.search_author_id(scholar_id)
    author = scholarly.fill(author, sortby="year")  # Recent year to less recent
    pubs = author.get("publications") or []

    entries = []

    for idx, p in enumerate(pubs):
        print(f"[INFO] Processing {idx+1}")

        try: p_full = scholarly.fill(p)
        except Exception: p_full = p

        title, year, authors, venue, link, citation = _return_basics(p_full)

        if (not title) or (not year):   # Too many information is missing
            continue

        if int(year) not in allowed_years:
            # Publication is older than within acceptable year range
            break

        # Clean
        scholar_bibtex = ""
        scholar_fields = {}
        try:
            scholar_bibtex = get_bibtex_with_fallback(p_full, title=title)
            scholar_fields = bibtex_to_fields(scholar_bibtex)
        except Exception:
            scholar_bibtex = ""
            scholar_fields = {}

        doi = (
            _extract_doi(link)
            or _extract_doi(scholar_bibtex)
            or _extract_doi(json.dumps(scholar_fields, ensure_ascii=False))
        )

        ##

        # Determine citation type
        cit_type = _citation_type(venue=venue,
                                  citation=citation,
                                  doi=doi)

        if cit_type == 'arxiv':
            entry = {}
            entries.append(entry)
            time.sleep(1.0)
            continue

        elif cit_type == 'acm':
            entry = {}
            entries.append(entry)
            time.sleep(1.0)
            continue

        elif cit_type == 'springer':
            entry = {}
            entries.append(entry)
            time.sleep(1.0)
            continue

        elif cit_type == 'fallback':
            entry = {}
            entries.append(entry)
            time.sleep(1.0)
            continue

        # Identify if on ACM

        # Identify if on Springer

        # Fallback Crossref

        # Fallback just regular scholarly

    # Write to bib
    db = bibtexparser.bibdatabase.BibDatabase()
    db.entries = entries

    writer = BibTexWriter()
    writer.indent = "  "
    writer.order_entries_by = None  # Maintain ordering

    out = []
    # Just to note time and basic info stuff
    out.append("% AUTO-GENERATED FILE. DO NOT EDIT.")
    out.append("% Updated on: " + datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
    out.append("")
    out.append(writer.write(db))

    with open(OUT_BIB_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(out).strip() + "\n")

    print(f"[INFO] Wrote {len(entries)} BibTeX entries -> {OUT_BIB_PATH}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Google Scholar based Bib update")
    parser.add_argument('--scholar_id', type=str, required=True)
    parser.add_argument('--year_window', type=int, default=2)
    args = parser.parse_args()

    main(scholar_id=args.scholar_id,
         year_window=args.year_window)