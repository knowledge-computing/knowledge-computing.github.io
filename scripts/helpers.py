from typing import List

import re

import bibtexparser

# Regex patterns
DOI_RE = re.compile(r"(10\.\d{4,9}/[-._;()/:A-Z0-9]+)", re.I)
ARXIV_WORD_RE = re.compile(r"\barxiv\b", re.I)

def extract_doi_any(list_text: List[str]) -> str:
    """
    Extract DOI from any type of input string
    """

    for text in list_text:
        if not text:
            continue

        m = DOI_RE.search(text)
        if m:
            return m.group(1)
        
    return ""

def citation_type(venue:str=None,
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

def bibtex_to_fields(bibtex_str: str) -> dict:
    """
    Parse bibtex to dictionary
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
        out[str(k).lower().strip()] = str(v).strip()
    return out