from typing import List
from pathlib import Path
from datetime import datetime, timezone

import re
import html
import string

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
        db.entires = entries

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
