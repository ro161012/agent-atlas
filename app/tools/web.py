"""Web research tools: live search + page fetching.

``web_search`` uses the SerpAPI Google endpoint when SERPAPI_KEY is configured,
and otherwise returns an honest note so the agent can fall back to structured
reasoning or the user-supplied documents. ``fetch_url`` works with no API keys.
"""

from __future__ import annotations

import httpx

from ..config import get


def web_search(query: str, num: int = 5) -> dict:
    """Search the public web and return the top results for `query`.

    Args:
        query: The natural-language or keyword search query.
        num: How many results to return (default 5, max 10).

    Returns a dict with `status`, an optional `results` list (title, link,
    snippet) and an `error_message` when a search backend isn't available.
    """
    key = get("serpapi_key")
    if not key:
        return {
            "status": "unavailable",
            "error_message": (
                "Live web search is not configured (SERPAPI_KEY missing). "
                "Proceed using the documents already ingested and your "
                "structured reasoning, or ask the user to supply sources."
            ),
        }
    params = {
        "engine": "google",
        "q": query,
        "api_key": key,
        "num": min(int(num), 10),
    }
    try:
        r = httpx.get("https://serpapi.com/search.json", params=params, timeout=30)
        r.raise_for_status()
        organic = r.json().get("organic_results", [])[: int(num)]
        results = [
            {"title": x.get("title"), "link": x.get("link"), "snippet": x.get("snippet")}
            for x in organic
        ]
        return {"status": "success", "query": query, "results": results}
    except Exception as exc:  # noqa: BLE001 - surface a readable error to the LLM
        return {"status": "error", "error_message": f"Search failed: {exc}"}


def fetch_url(url: str, max_chars: int = 20000) -> dict:
    """Fetch and extract readable text from a public URL.

    Args:
        url: The fully-qualified http(s) URL to read.
        max_chars: Maximum characters of text to return (default 20000).

    Returns the page text (lightly cleaned) plus the final URL and status.
    """
    try:
        r = httpx.get(url, follow_redirects=True, timeout=30)
        r.raise_for_status()
        text = _to_text(r.text)
        return {
            "status": "success",
            "url": str(r.url),
            "http_status": r.status_code,
            "text": text[: max_chars],
        }
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error_message": f"Could not fetch URL: {exc}"}


def _to_text(html: str) -> str:
    """Crude HTML->text: strip tags/scripts/styles/extra whitespace."""
    import re

    html = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", html)
    html = re.sub(r"(?i)<br\\s*/?>", "\\n", html)
    html = re.sub(r"</(p|div|li|h[1-6]|tr)>", "\\n", html)
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\\s+", " ", text)
    return text.strip()