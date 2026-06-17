"""
agent.py

The FitFindr planning loop. Orchestrates the three tools in response to a
natural language user query, passing state between them via a session dict.

Complete tools.py and test each tool in isolation before implementing this file.

Usage (once implemented):
    from agent import run_agent
    from utils.data_loader import get_example_wardrobe

    result = run_agent(
        query="vintage graphic tee under $30, size M",
        wardrobe=get_example_wardrobe(),
    )
    print(result["fit_card"])
    print(result["error"])   # None on success
"""

import re

from tools import search_listings, suggest_outfit, create_fit_card, check_price


# ── query parsing ─────────────────────────────────────────────────────────────

def _parse_query(query: str) -> dict:
    """
    Pull a description, size, and max_price out of a free-text query.

    Examples:
        "vintage graphic tee under $30"     -> desc="vintage graphic tee", max_price=30
        "90s track jacket in size M"        -> desc="90s track jacket", size="M"
        "black combat boots size 8 under 60"-> desc="black combat boots", size="8", max_price=60

    Returns a dict: {"description": str, "size": str | None, "max_price": float | None}
    The size/price phrases are stripped from the description so they don't leak
    into keyword relevance scoring (e.g. "$30" matching "501" or "2003").
    """
    text = query or ""

    # max_price: "under/below/less than/up to/max $30", else a bare "$30".
    max_price = None
    m = re.search(
        r"(?:under|below|less than|up to|max|<)\s*\$?\s*(\d+(?:\.\d+)?)", text, re.I
    )
    if not m:
        m = re.search(r"\$\s*(\d+(?:\.\d+)?)", text)
    if m:
        max_price = float(m.group(1))

    # size: "size M", "size 8", "size 8.5".
    size = None
    s = re.search(r"\bsize\s+([a-z0-9.]+)", text, re.I)
    if s:
        size = s.group(1).upper()

    # description: the query with the price/size phrases removed.
    desc = re.sub(
        r"(?:under|below|less than|up to|max)\s*\$?\s*\d+(?:\.\d+)?(?:\s*dollars?)?",
        " ", text, flags=re.I,
    )
    desc = re.sub(r"\$\s*\d+(?:\.\d+)?", " ", desc)
    desc = re.sub(r"\bsize\s+[a-z0-9.]+", " ", desc, flags=re.I)
    desc = re.sub(r"\s+", " ", desc).strip()

    return {"description": desc, "size": size, "max_price": max_price}


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    """
    Initialize and return a fresh session dict for one user interaction.

    The session dict is the single source of truth for everything that happens
    during a run — it stores the original query, parsed parameters, tool results,
    and any error that caused early termination.

    You may add fields to this dict as needed for your implementation.
    """
    return {
        "query": query,              # original user query
        "parsed": {},                # extracted description / size / max_price
        "search_results": [],        # list of matching listing dicts
        "selected_item": None,       # top result, passed into suggest_outfit
        "wardrobe": wardrobe,        # user's wardrobe dict
        "price_check": None,         # dict returned by check_price (extra credit)
        "outfit_suggestion": None,   # string returned by suggest_outfit
        "fit_card": None,            # string returned by create_fit_card
        "error": None,               # set if the interaction ended early
    }


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop for a single
    user interaction and returns the completed session dict.

    Args:
        query:    Natural language user request
                  (e.g., "vintage graphic tee under $30, size M")
        wardrobe: User's wardrobe dict — use get_example_wardrobe() or
                  get_empty_wardrobe() from utils/data_loader.py

    Returns:
        The session dict after the interaction completes. Check session["error"]
        first — if it is not None, the interaction ended early and the other
        output fields (outfit_suggestion, fit_card) will be None.

    TODO — implement this function using the planning loop you designed in planning.md:

        Step 1: Initialize the session with _new_session().

        Step 2: Parse the user's query to extract a description, size, and
                max_price. You can use regex, string splitting, or ask the LLM
                to parse it — document your choice in planning.md.
                Store the result in session["parsed"].

        Step 3: Call search_listings() with the parsed parameters.
                Store results in session["search_results"].
                If no results: set session["error"] to a helpful message and
                return the session early. Do NOT proceed to suggest_outfit
                with empty input.

        Step 4: Select the item to use (e.g., the top result).
                Store it in session["selected_item"].

        Step 5: Call suggest_outfit() with the selected item and wardrobe.
                Store the result in session["outfit_suggestion"].

        Step 6: Call create_fit_card() with the outfit suggestion and selected item.
                Store the result in session["fit_card"].

        Step 7: Return the session.

    Before writing code, complete the Planning Loop and State Management sections
    of planning.md — your implementation should match what you described there.
    """
    # Step 1: fresh session — single source of truth for this interaction.
    session = _new_session(query, wardrobe)

    # Step 2: parse the query into search parameters.
    session["parsed"] = _parse_query(query)
    parsed = session["parsed"]

    # Step 3: search. This is the ONLY branch that can end the interaction early.
    session["search_results"] = search_listings(
        parsed["description"], parsed["size"], parsed["max_price"]
    )
    if not session["search_results"]:
        bits = []
        if parsed["size"]:
            bits.append(f"size {parsed['size']}")
        if parsed["max_price"] is not None:
            bits.append(f"under ${parsed['max_price']:.0f}")
        qualifier = f" ({', '.join(bits)})" if bits else ""
        session["error"] = (
            f'I couldn\'t find any listings matching "{parsed["description"] or query}"'
            f"{qualifier}. Try raising your max price, dropping the size filter, "
            f"or using broader keywords."
        )
        # Do NOT call suggest_outfit / create_fit_card with empty input.
        return session

    # Step 4: select the top-ranked match. This exact dict is reused downstream —
    # no re-searching, no hardcoded values.
    session["selected_item"] = session["search_results"][0]

    # Step 4b (extra credit): price check — non-blocking, never ends the chain.
    session["price_check"] = check_price(session["selected_item"])

    # Step 5: style the selected item against the user's wardrobe.
    session["outfit_suggestion"] = suggest_outfit(
        session["selected_item"], session["wardrobe"]
    )

    # Step 6: turn that suggestion + the same item into a shareable caption.
    session["fit_card"] = create_fit_card(
        session["outfit_suggestion"], session["selected_item"]
    )

    # Step 7: hand back the completed session.
    return session


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

    # LLM captions can contain emoji; force UTF-8 so printing doesn't crash on
    # the default Windows console code page (cp1252).
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    print("=== Happy path: graphic tee ===\n")
    session = run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    )
    if session["error"]:
        print(f"Error: {session['error']}")
    else:
        print(f"Found: {session['selected_item']['title']}")
        print(f"\nOutfit: {session['outfit_suggestion']}")
        print(f"\nFit card: {session['fit_card']}")

    print("\n\n=== No-results path ===\n")
    session2 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    print(f"Error message: {session2['error']}")
