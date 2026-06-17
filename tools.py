"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Complete and test each tool before moving to agent.py.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
"""

import os
import statistics

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


# ── Shared input guard ────────────────────────────────────────────────────────

def _is_valid_item(item) -> bool:
    """
    A listing must be a non-empty dict to be usable by the tools that consume one.

    Tools call this at the top before touching .get() or hitting the LLM, so bad
    input (e.g. an empty list from a no-results search passed in by mistake)
    produces a clear, tool-appropriate message instead of an AttributeError.
    """
    return isinstance(item, dict) and bool(item)


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for
                     (e.g., "vintage graphic tee").
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive (e.g., "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts, sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.

    Each listing dict has the following fields:
        id, title, description, category, style_tags (list), size,
        condition, price (float), colors (list), brand, platform

    TODO:
        1. Load all listings with load_listings().
        2. Filter by max_price and size (if provided).
        3. Score each remaining listing by keyword overlap with `description`.
        4. Drop any listings with a score of 0 (no relevant matches).
        5. Sort by score, highest first, and return the listing dicts.

    Before writing code, fill in the Tool 1 section of planning.md.
    """
    listings = load_listings()

    # 1. Apply the hard filters first (price, then size).
    candidates = []
    for lst in listings:
        if max_price is not None and lst.get("price", float("inf")) > max_price:
            continue
        if size is not None:
            listing_size = (lst.get("size") or "").lower()
            if size.strip().lower() not in listing_size:
                continue
        candidates.append(lst)

    # 2. Score the survivors by keyword overlap with the description.
    query_tokens = _tokenize(description)
    scored = []
    for lst in candidates:
        score = _relevance_score(query_tokens, lst)
        if score > 0:
            scored.append((score, lst))

    # 3. Sort by score (highest first) and return just the listing dicts.
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [lst for _, lst in scored]


# Common filler words that shouldn't count toward relevance.
_STOPWORDS = {
    "a", "an", "the", "for", "under", "with", "and", "or", "of", "in", "on",
    "to", "my", "i", "im", "size", "looking", "want", "need", "some", "that",
}


def _tokenize(text: str) -> set[str]:
    """Lowercase, split on non-alphanumeric chars, and drop stopwords/short tokens."""
    raw = "".join(c if c.isalnum() else " " for c in (text or "").lower()).split()
    return {tok for tok in raw if len(tok) > 1 and tok not in _STOPWORDS}


def _relevance_score(query_tokens: set[str], listing: dict) -> int:
    """
    Score a listing against the query tokens. Matches in the title or style_tags
    count for more than matches buried in the free-text description.
    """
    title = (listing.get("title") or "").lower()
    tags = " ".join(listing.get("style_tags") or []).lower()
    desc = (listing.get("description") or "").lower()

    score = 0
    for tok in query_tokens:
        if tok in title or tok in tags:
            score += 2
        elif tok in desc:
            score += 1
    return score


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key containing a list of
                  wardrobe item dicts. May be empty — handle this gracefully.

    Returns:
        A non-empty string with outfit suggestions.
        If the wardrobe is empty, offer general styling advice for the item
        rather than raising an exception or returning an empty string.

    TODO:
        1. Check whether wardrobe['items'] is empty.
        2. If empty: call the LLM with a prompt for general styling ideas
           (what kinds of items pair well, what vibe it suits, etc.).
        3. If not empty: format the wardrobe items into a prompt and ask
           the LLM to suggest specific outfit combinations using the new item
           and named pieces from the wardrobe.
        4. Return the LLM's response as a string.

    Before writing code, fill in the Tool 2 section of planning.md.
    """
    # Guard: the contract is a single listing dict. If we're handed something
    # else (e.g. an empty list from a no-results search), return a clear message
    # instead of crashing on .get(). The planning loop should never reach here
    # with bad input, but the tool stays safe when called in isolation.
    if not _is_valid_item(new_item):
        return (
            "I couldn't put together an outfit — no valid item was provided. "
            "Run search_listings first and pass a single matching listing."
        )

    client = _get_groq_client()

    item_desc = (
        f"{new_item.get('title', 'an item')} "
        f"(category: {new_item.get('category', 'unknown')}, "
        f"colors: {', '.join(new_item.get('colors') or []) or 'n/a'}, "
        f"style: {', '.join(new_item.get('style_tags') or []) or 'n/a'})"
    )

    items = (wardrobe or {}).get("items") or []

    if not items:
        # Empty-wardrobe fallback: style the piece on its own, no owned items.
        user_prompt = (
            f"A shopper is considering this secondhand item:\n{item_desc}\n\n"
            "They haven't added any wardrobe yet. Suggest how to style this piece "
            "on its own — describe 1-2 complete outfits using general, easy-to-find "
            "complementary pieces (don't reference items they own, since you don't "
            "know them). Keep it to 2-3 sentences, friendly and concrete."
        )
    else:
        wardrobe_lines = "\n".join(
            f"- {it.get('name', 'item')} "
            f"({it.get('category', '?')}; "
            f"{', '.join(it.get('colors') or []) or 'n/a'}; "
            f"{', '.join(it.get('style_tags') or []) or 'n/a'})"
            for it in items
        )
        user_prompt = (
            f"A shopper is considering this secondhand item:\n{item_desc}\n\n"
            f"Here is their existing wardrobe:\n{wardrobe_lines}\n\n"
            "Suggest 1-2 complete outfits that pair the new item with specific pieces "
            "from their wardrobe. Reference the wardrobe pieces by name. Keep it to "
            "2-3 sentences, friendly and concrete, and add one quick styling tip."
        )

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are FitFindr, a warm, knowledgeable secondhand-fashion "
                    "stylist. You give specific, wearable outfit suggestions."
                ),
            },
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.7,
    )
    return response.choices[0].message.content.strip()


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence string usable as an Instagram/TikTok caption.
        If outfit is empty or missing, return a descriptive error message
        string — do NOT raise an exception.

    The caption should:
    - Feel casual and authentic (like a real OOTD post, not a product description)
    - Mention the item name, price, and platform naturally (once each)
    - Capture the outfit vibe in specific terms
    - Sound different each time for different inputs (use higher LLM temperature)

    TODO:
        1. Guard against an empty or whitespace-only outfit string.
        2. Build a prompt that gives the LLM the item details and the outfit,
           and asks for a caption matching the style guidelines above.
        3. Call the LLM and return the response.

    Before writing code, fill in the Tool 3 section of planning.md.
    """
    # Guard: no outfit to caption → return an error string, do NOT call the LLM.
    if not outfit or not outfit.strip():
        return (
            "Can't create a fit card without an outfit suggestion — "
            "run suggest_outfit first."
        )

    # Tolerate a missing/invalid item: coerce to {} so the .get() defaults below
    # fill in gracefully (caption degrades to just the outfit vibe) rather than
    # crashing on a non-dict.
    if not _is_valid_item(new_item):
        new_item = {}

    client = _get_groq_client()

    title = new_item.get("title", "this piece")
    price = new_item.get("price")
    platform = new_item.get("platform")

    details = [f"item: {title}"]
    if price is not None:
        details.append(f"price: ${price:.0f}")
    if platform:
        details.append(f"platform: {platform}")
    detail_str = ", ".join(details)

    user_prompt = (
        f"Thrifted find — {detail_str}.\n"
        f"Outfit it's styled in: {outfit}\n\n"
        "Write a short, casual social-media caption (2-4 sentences) for posting "
        "this outfit, like a real OOTD/thrift-haul post — not a product "
        "description. Mention the item name, its price, and the platform naturally "
        "(once each). Capture the outfit's vibe in specific terms. Lowercase, "
        "authentic voice, an emoji or two is fine."
    )

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {
                "role": "system",
                "content": (
                    "You write fun, authentic secondhand-fashion captions for social "
                    "media. Each caption should feel fresh and a little different."
                ),
            },
            {"role": "user", "content": user_prompt},
        ],
        temperature=1.1,  # high temp → captions vary across runs on the same input
    )
    return response.choices[0].message.content.strip()


# ── Tool 4: check_price (extra credit — price comparison) ───────────────────────

# Verdict thresholds, expressed as a fraction of the comparable median price.
_DEAL_RATIO = 0.85       # price at or below 85% of median  → great deal
_OVERPRICED_RATIO = 1.15  # price above 115% of median       → overpriced
_MIN_COMPARABLES = 3      # need at least this many comps to give a verdict


def check_price(item: dict) -> dict:
    """
    Estimate whether `item`'s price is fair by comparing it against comparable
    listings in the dataset (same category, at least one shared style tag).

    Args:
        item: A listing dict (normally the selected search result). Uses its
              id, category, style_tags, price, and title.

    Returns:
        A dict describing the assessment:
            verdict          one of "great deal", "fair", "overpriced", "unknown"
            item_price       float — the item's own price
            comparable_count int   — how many comparable listings were found
            median_price     float | None
            min_price        float | None
            max_price        float | None
            message          str   — human-readable one-liner

        Never raises. If there are fewer than _MIN_COMPARABLES comparables (or the
        item has no usable price), returns verdict="unknown".
    """
    # Coerce any non-dict input (None, list, etc.) to {} so the .get() calls
    # below stay safe; the no-price branch then returns a clean "unknown".
    if not _is_valid_item(item):
        item = {}
    item_price = item.get("price")
    title = item.get("title", "this item")
    category = item.get("category")
    style_tags = set(item.get("style_tags") or [])
    item_id = item.get("id")

    def _unknown(msg: str, count: int = 0) -> dict:
        return {
            "verdict": "unknown",
            "item_price": item_price,
            "comparable_count": count,
            "median_price": None,
            "min_price": None,
            "max_price": None,
            "message": msg,
        }

    # Guard: we can't judge a price we don't have, or with no category to match on.
    if not isinstance(item_price, (int, float)):
        return _unknown("No price available, so I can't assess whether it's fair.")
    if not category:
        return _unknown("Not enough item detail to find comparable listings.")

    # Find comparables: same category, ≥1 shared style tag, excluding the item itself.
    comps = [
        lst
        for lst in load_listings()
        if lst.get("id") != item_id
        and lst.get("category") == category
        and style_tags.intersection(lst.get("style_tags") or [])
        and isinstance(lst.get("price"), (int, float))
    ]

    if len(comps) < _MIN_COMPARABLES:
        return _unknown(
            f"Only found {len(comps)} comparable listing(s) — not enough to judge "
            f"this price confidently.",
            count=len(comps),
        )

    prices = [lst["price"] for lst in comps]
    median_price = statistics.median(prices)
    min_price, max_price = min(prices), max(prices)

    if item_price <= median_price * _DEAL_RATIO:
        verdict = "great deal"
        lede = f"At ${item_price:.0f}, {title} is a great deal"
    elif item_price > median_price * _OVERPRICED_RATIO:
        verdict = "overpriced"
        lede = f"At ${item_price:.0f}, {title} runs a bit high"
    else:
        verdict = "fair"
        lede = f"At ${item_price:.0f}, {title} is fairly priced"

    message = (
        f"{lede} — {len(comps)} comparable items run "
        f"${min_price:.0f}–${max_price:.0f} (median ${median_price:.0f})."
    )

    return {
        "verdict": verdict,
        "item_price": float(item_price),
        "comparable_count": len(comps),
        "median_price": float(median_price),
        "min_price": float(min_price),
        "max_price": float(max_price),
        "message": message,
    }
