import argparse
from pathlib import Path

import re
import time
import json
from datetime import datetime, timezone

from scholarly import scholarly

from scripts.utils import (write_to_bibtex,   # Some defaults,
                           normalize_ws, normalize_title, normalize_authors_to_bibtex,   # Normalization stuff
                           strip_html_tags,     # HTML removal
                           seq_ratio, token_set_ratio,       # Fuzzy matching
                           extract_doi, extract_arxiv_id,    # DOI stuff
                           make_bib_key,  # bibtex creation
                           bibtex_to_fields, get_bibtex_with_fallback, cv_family_bibtex_by_url,   # Default grab
                           arxiv_api_query_by_id, arxiv_find_best_by_title,     # Things for arxiv
                           acm_bibtex_by_doi, springer_bibtex_by_doi, crossref_bibtex_by_doi,    # Outer bibtex
                           crossref_bibtex_transform, crossref_search_best,     # Crossref grab
                           build_arxiv_bib_entry, build_other_bib_entry,        # Build entry
                           )

ARXIV_WORD_RE = re.compile(r"\barxiv\b", re.I)

def pick_basics(pub: dict) -> str:
    bib = pub.get("bib", {}) or {}
    title = normalize_ws(bib.get("title") or "")

    authors = normalize_ws(bib.get("author") or "")

    year = bib.get("pub_year") or bib.get("year") or ""
    year = str(year).strip() if year is not None else ""

    link = normalize_ws(pub.get("pub_url") or bib.get("url") or "")

    bib = pub.get("bib", {}) or {}
    cit = normalize_ws(bib.get("citation") or "")

    if cit:
        head = cit.split(",", 1)[0].strip()
        if head and head.lower() != "unknown":
            venue = head

        else:
            venue = re.sub(r"\s*\(?\b(19|20)\d{2}\b\)?\s*$", "", cit).strip()

    else: venue = cit

    return title, authors, venue, year, link

def main(scholar_id:str,
         year_window:int,
         outpath:str,):
    this_year = datetime.now(timezone.utc).year
    allowed_years = {this_year - i for i in range(year_window)}

    author = scholarly.search_author_id(scholar_id)
    author = scholarly.fill(author, sortby="year")

    entries = []

    pubs = author.get("publications") or []
    for idx, p in enumerate(pubs):
        # Fill each pub
        try:
            p_full = scholarly.fill(p)
        except Exception:
            p_full = p

        title, authors, venue, year, link = pick_basics(p_full)
    
        if not title:
            # Too little information to actually do something
            continue

        try:
            if int(year) not in allowed_years:
                break
        except Exception:
            continue

        print(f"Filling bibtex for {idx+1}: {title}")

        # Prefer BibTeX exposed directly on CV-family paper pages.
        cv_family_bibtex = ""
        cv_family_fields = {}
        try:
            cv_family_bibtex = cv_family_bibtex_by_url(link, title=title)
            if cv_family_bibtex:
                cv_family_fields = bibtex_to_fields(cv_family_bibtex)
        except Exception:
            cv_family_bibtex = ""
            cv_family_fields = {}

        # Fall back to scholarly when no conference-page BibTeX is available.
        scholar_bibtex = ""
        scholar_fields = {}
        if not cv_family_bibtex:
            try:
                scholar_bibtex = get_bibtex_with_fallback(p_full, title=title)
                scholar_fields = bibtex_to_fields(scholar_bibtex)
            except Exception:   # If either fails
                scholar_bibtex = ""
                scholar_fields = {}

        is_arxiv = False
        if ARXIV_WORD_RE.search(venue or ""):
            is_arxiv = True
        else:
            bib_cit = normalize_ws((p_full.get("bib", {}) or {}).get("citation") or "")
            if ARXIV_WORD_RE.search(bib_cit) or ARXIV_WORD_RE.search(scholar_bibtex) or ARXIV_WORD_RE.search(link):
                is_arxiv = True

        if is_arxiv:
            # try to get arxiv id directly
            arxiv_id = extract_arxiv_id([link, scholar_bibtex,
                                         (p_full.get("bib", {}) or {}).get("citation") or ""])
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
                base_link=link,
                authors_guess=authors,
                arxiv_meta=arxiv_meta,
            )
            entries.append(entry)
            time.sleep(1.0)
            continue

        entry = {}

        # Try getting DOI
        doi = extract_doi([
            link,
            cv_family_bibtex,
            scholar_bibtex,
            json.dumps(cv_family_fields, ensure_ascii=False),
            json.dumps(scholar_fields, ensure_ascii=False),
        ])

        # ACM
        if doi and doi.startswith("10.1145/"):
            acm_bib = acm_bibtex_by_doi(doi)
            if acm_bib:
                entry = build_other_bib_entry(
                    acm_bib,
                    title_fallback=title,
                    venue_fallback=venue,
                    year_fallback=year,
                    link_fallback=link,
                    abstract_fallback="",
                )

        # Springer
        if not entry and doi and doi.startswith("10.1007/"):
            sp_bib = springer_bibtex_by_doi(doi)
            if sp_bib:
                entry = build_other_bib_entry(
                    sp_bib,
                    title_fallback=title,
                    venue_fallback=venue,
                    year_fallback=year,
                    link_fallback=link,
                    abstract_fallback="",
                )


        crossref_bib = ""
        crossref_msg = {}

        # Crossref by DOI -> MIGHT BE INCORRECT
        if not entry and doi:
            try:
                crossref_msg = crossref_bibtex_by_doi(doi)

                # Cross-check crossref with scholarly
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

        # Crossref by title in case there aint
        if not crossref_bib:
            try:
                best = crossref_search_best(title=title, year=year, venue=venue, rows=5)
                best_doi = (best.get("DOI") or "").strip()
                if best_doi:
                    crossref_bib = crossref_bibtex_transform(best_doi)

                    try:
                        crossref_msg = crossref_bibtex_by_doi(best_doi)
                    except Exception:
                        crossref_msg = {}
            except Exception:
                crossref_bib = ""

        if crossref_bib:
            cr_abs = strip_html_tags(crossref_msg.get("abstract") or "")
            entry = build_other_bib_entry(
                crossref_bib,
                title_fallback=title,
                venue_fallback=venue,
                year_fallback=year,
                link_fallback=link,
                abstract_fallback=cr_abs,
            )

            cr_abs = strip_html_tags(crossref_msg.get("abstract") or "")    # Keep abstract if available
            if cr_abs:
                entry["abstract"] = cr_abs

        if not entry and cv_family_bibtex:
            entry = build_other_bib_entry(
                cv_family_bibtex,
                title_fallback=title,
                venue_fallback=venue,
                year_fallback=year,
                link_fallback=link,
                abstract_fallback="",
            )

        # Fall back to Scholarly bibtex if they have that
        if not entry and scholar_bibtex:
            entry = build_other_bib_entry(
                scholar_bibtex,
                title_fallback=title,
                venue_fallback=venue,
                year_fallback=year,
                link_fallback=link,
                abstract_fallback="",
            )

        # Minimum
        if not entry:
            authors = normalize_authors_to_bibtex(authors)
            entry = {
                "ENTRYTYPE": "misc",
                "ID": make_bib_key(authors, year, title),
                "title": title,
                "author": authors,
                "year": year,
            }
            if venue:
                entry["howpublished"] = venue
            if link:
                entry["url"] = link

        entries.append(entry)
        time.sleep(1.0)

    write_to_bibtex(entries, Path(outpath),
                    ["AUTO-GENERATED FILE. DO NOT EDIT."],
                    bool_dict=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Google Scholar based Bib update")
    parser.add_argument('--scholar_id', type=str, required=True)
    parser.add_argument('--year_window', type=int, default=2)
    parser.add_argument('--outpath', type=str, default="./_data/pub/dynamic.bib")
    args = parser.parse_args()

    main(scholar_id=args.scholar_id,
         year_window=args.year_window,
         outpath=args.outpath)
