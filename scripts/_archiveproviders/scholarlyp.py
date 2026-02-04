from scholarly import scholarly

def get_bibtex_with_fallback(p_full: dict, title: str) -> str:
    """
    get bibtex from scholarly
    """
    try:
        s = scholarly.bibtex(p_full)        # Get bibtext directly
        if s:
            return s
    except Exception:
        pass

    try:
        q = scholarly.search_pubs(title)    # Search by title
        pub2 = next(q, None)
        if not pub2:
            return ""
        pub2 = scholarly.fill(pub2)
        return scholarly.bibtex(pub2) or ""
    except Exception:
        return ""