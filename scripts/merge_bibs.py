"""
Merges static bibs and dynamic bibs
Removes delete bibs and overrides override bibs
Reason: we'll only update dynamic bibs automatically
"""

from pathlib import Path

from scripts.utils import load, write_to_bibtex

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "_data/pub/static.bib"
DYNAMIC = ROOT / "_data/pub/dynamic.bib"
OVERRIDE= ROOT / "_data/pub/override.bib"
DELETE = ROOT / "_data/pub/delete.bib"
OUT = ROOT / "publications.bib"

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

    write_to_bibtex(merged, OUT,
                    ["AUTO-GENERATED FILE — DO NOT EDIT"])

if __name__ == "__main__":
    main()
