"""
Migrates two years ago data in dynamic bib to static bib
    with consideration for override and delete
"""
import re

from pathlib import Path
from datetime import datetime, timezone

from scripts.utils import load, write_to_bibtex

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "_data/pub/static.bib"
DYNAMIC = ROOT / "_data/pub/dynamic.bib"
OVERRIDE= ROOT / "_data/pub/override.bib"
DELETE = ROOT / "_data/pub/delete.bib"

def still_current(static_year:int,
                  current_year:int) -> bool:
    """
    Compare current year with static.bib file year
    """
    if static_year == current_year:
        return True
    
    return False

def get_static_year(path: Path) -> int:
    """
    Read the comment header of the static file
    Extract the year portion
    """
    with path.open("r", encoding="utf-8") as f:
        list_lines = f.readlines()

    line_date = list_lines[2]
    m = re.search(r"on\s+(\d{4})-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", line_date)
    year = m.group(1) if m else None

    return int(year)

def main():
    current_year = datetime.now(timezone.utc).year
    static_year = get_static_year(STATIC)

    if still_current(static_year, current_year):
        print("No changes to make yet")
        return

    static_entries = load(STATIC)
    dynamic_entries = load(DYNAMIC)
    delete_entries = load(DELETE)
    override_entries = load(OVERRIDE)

    # Create delete list for those that are more than 2 years ago
    list_delete = []
    remain_delete = {}
    for e in delete_entries:
        if "ID" in e:
            if e["year"] <= str(current_year - 2):
                list_delete.append(e["ID"])
                continue
            remain_delete[e["ID"]] = e
    write_to_bibtex(remain_delete, DELETE,
                    ["Publications that should not be visible on the lab webpage",
                     "PLEASE COPY AND PASTE IT FROM THE DYNAMIC.BIB FILE",
                     "If changes need to made for files in static.bib DO DIRECTLY IN STATIC.BIB"])

    merged = {}
    for e in static_entries:
        if "ID" in e:
            merged[e["ID"]] = e

    remain_override = {}
    dict_override = {}
    for e in override_entries:
        if "ID" in e:
            if e["year"] <= str(current_year - 2):
                dict_override[e["ID"]] = e
                continue
            else:
                remain_override[e["ID"]] = e
    write_to_bibtex(remain_override, OVERRIDE,
                    ["PLEASE use the same reference ID when overriding information"])


    # Identify dynamic items that are over year
    remain_dynamic = {}
    for e in dynamic_entries:
        if "ID" in e:
            unique_id = e["ID"]

            if unique_id in list_delete:
                continue

            if e["year"] <= str(current_year - 2):
                try:    # Override information
                    merged[unique_id] = dict_override[unique_id]
                except:
                    merged[unique_id] = e

                continue
            else:
                remain_dynamic[unique_id] = e

    write_to_bibtex(remain_dynamic, DYNAMIC,
                    ["AUTO-GENERATED FILE. DO NOT EDIT."])
    
    write_to_bibtex(merged, STATIC,
                    ["STATIC BIBS - FEEL FREE TO EDIT",
                     "DO NOT CHANGE ANY OF THE COMMENTS"])

if __name__ == "__main__":
    main()
