"""
Merges static bibs and dynamic bibs
Removes delete bibs and overrides override bibs
Reason: we'll only update dynamic bibs automatically
"""

from pathlib import Path
from datetime import datetime, timezone

import bibtexparser

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "_data/pub/static.bib"
DYNAMIC = ROOT / "_data/pub/dynamic.bib"
OVERRIDE= ROOT / "_data/pub/override.bib"
DELETE = ROOT / "_data/pub/delete.bib"
OUT = ROOT / "publications.bib"

def load(path: Path):
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        db = bibtexparser.load(f)
    return db.entries

def main():
    static_entries = load(STATIC)
    dynamic_entries = load(DYNAMIC)
    delete_entries = load(DELETE)
    override_entries = load(OVERRIDE)

    # List to delete
    list_delete = [e.get("ID") for e in delete_entries]

    # Dictionary for replacements
    dict_override = {}
    for e in override_entries:
        dict_override[e["ID"]] = e

    merged = {}
    for e in dynamic_entries:
        if "ID" in e:
            unique_id = e["ID"]

            if unique_id in list_delete:    # Delete based on user command
                continue
            
            try:    # Override information
                merged[unique_id] = dict_override[unique_id]
            except:
                merged[unique_id] = e
    
    for e in static_entries:
        if "ID" in e:
            merged[e["ID"]] = e

    db = bibtexparser.bibdatabase.BibDatabase()
    db.entries = list(merged.values())

    writer = bibtexparser.bwriter.BibTexWriter()
    writer.indent = "  "
    body = writer.write(db)

    ts = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    header = (
        f"% AUTO-GENERATED FILE — DO NOT EDIT\n"
        f"% Merged {STATIC.name} + {DYNAMIC.name} on {ts}\n\n"
    )

    OUT.write_text(header + body, encoding="utf-8")
    print(f"Wrote {OUT} with {len(db.entries)} entries.")

if __name__ == "__main__":
    main()
