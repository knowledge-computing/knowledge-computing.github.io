from typing import List

import re

import html
import requests

from .utils import *

ARXIV_ID_RE = re.compile(
    r"(?:arxiv\.org/(?:abs|pdf)/)(?P<id>(?:\d{4}\.\d{4,5}|[a-z\-]+/\d{7})(?:v\d+)?)",
    re.I,
)

UA_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120 Safari/537.36"
    )
}

def extract_arxiv_any(list_text: List[str]) -> str:
    """
    Extract ArXiV ID from any type of input string
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

def xml_text(tag: str,
             xml: str) -> str:
    m = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", xml, flags=re.S | re.I)
    return html.unescape(m.group(1)).strip() if m else ""

def arxiv_meta_by_id(arxiv_id: str) -> dict:
    """
    Meta search by ArXiv ID

    """
    url = "http://export.arxiv.org/api/query"
    params = {"id_list": arxiv_id}
    r = requests.get(url, params=params, headers=UA_HEADERS, timeout=25)
    r.raise_for_status()
    xml = r.text

    title = normalize_ws(xml_text("title", xml))
    titles = re.findall(r"<title[^>]*>(.*?)</title>", xml, flags=re.S | re.I)
    if titles:
        title = normalize_ws(html.unescape(titles[-1]))

    summary = normalize_ws(xml_text("summary", xml))
    published = xml_text("publishedm", xml)
    year = published[:4] if published[:4].isdigit() else ""

    names = re.findall(r"<author>\s*<name>(.*?)</name>\s*</author>", xml, flags=re.S | re.I)
    authors = " and ".join(normalize_ws(html.unescape(n)) for n in names if normalize_ws(n))

    entry_id = xml_text("id", xml)
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

def arxiv_meta_by_title(title: str, 
                        first_author: str = "") -> dict:
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
            # extract id
            mid = re.search(r"<id[^>]*>(.*?)</id>", e, flags=re.S | re.I)
            eid = normalize_ws(html.unescape(mid.group(1))) if mid else ""
            # arxiv id from url
            arxiv_id = extract_arxiv_any([eid]) or ""
            best_score = score
            best = {"arxiv_id": arxiv_id, "entry_url": eid, "matched_title": etitle, "score": score}

    return best or {}



def _build_arxiv_meta(arxiv_id:str=None,
                      title:str=None,
                      authors_guess:str=None) -> None:
    if not arxiv_id:
        best_guess = arxiv_meta_by_title(title, 
                                         first_author=authors_guess)
        if best_guess.get("arxiv_id"):
            arxiv_id = best_guess.get("arxiv_id")

    try: 
        return arxiv_meta_by_id(arxiv_id)
    except Exception:
        return {}

def arxiv_entry(base_title: str, 
                base_year: str, 
                base_venue: str, 
                base_link: str, 
                authors_guess: str,
                scholar_bibtex: str,
                citation:str, ) -> dict:
    """
    Build Bibtex from arXiv
    """

    arxiv_id = extract_arxiv_any([base_link, scholar_bibtex, citation])
    arxiv_meta = _build_arxiv_meta(arxiv_id)

    title = arxiv_meta.get("title") or base_title
    authors = arxiv_meta.get("authors") or normalize_authors_to_bibtex(authors_guess)
    year = arxiv_meta.get("year") or base_year
    url = arxiv_meta.get("url") or base_link

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