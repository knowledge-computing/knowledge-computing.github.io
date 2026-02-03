def clean_crossref_text(s: str) -> str:
    """
    Convert HTML entities (&lt; etc.) to characters, strip tags (<p>),
    and normalize whitespace.
    """
    if not s:
        return ""
    s = html.unescape(s)          # &lt;p&gt; -> <p>
    s = re.sub(r"<[^>]+>", " ", s)  # remove tags like <p>
    return normalize_ws(s)
