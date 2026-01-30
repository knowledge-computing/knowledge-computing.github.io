from pathlib import Path
from datetime import datetime, timezone

import bibtexparser

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "_data/pub/static.bib"
DYNAMIC = ROOT / "_data/pub/dynamic.bib"
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

    merged = {}
    for e in static_entries:
        if "ID" in e:
            merged[e["ID"]] = e
    for e in dynamic_entries:
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
