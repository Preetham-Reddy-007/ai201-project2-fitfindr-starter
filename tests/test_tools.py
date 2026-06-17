"""
tests/test_tools.py

Unit tests for the four FitFindr tools, with at least one test per failure mode.

Run with:  pytest tests/

Tests that hit the Groq LLM (suggest_outfit, create_fit_card happy paths) are
skipped automatically when GROQ_API_KEY is not set, so the data-only tests and
every failure-mode test still run in any environment.
"""

import os
import sys

import pytest
from dotenv import load_dotenv

# Make the project root importable when pytest is run from the repo root.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tools import search_listings, suggest_outfit, create_fit_card, check_price
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

load_dotenv()

_HAS_GROQ = bool(os.environ.get("GROQ_API_KEY"))
requires_groq = pytest.mark.skipif(not _HAS_GROQ, reason="GROQ_API_KEY not set")


# ── search_listings ───────────────────────────────────────────────────────────

def test_search_returns_results():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert isinstance(results, list)
    assert len(results) > 0
    # Every result is a full listing dict with the expected fields.
    assert all("title" in item and "price" in item for item in results)


def test_search_empty_results():
    # Failure mode: nothing matches → empty list, never an exception.
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []


def test_search_price_filter():
    results = search_listings("jacket", size=None, max_price=40)
    assert all(item["price"] <= 40 for item in results)


def test_search_size_filter():
    # Size matching is a case-insensitive substring check ("m" matches "S/M", "M").
    results = search_listings("tee", size="M", max_price=None)
    assert all("m" in item["size"].lower() for item in results)


def test_search_sorted_by_relevance():
    # A tighter query should rank a true graphic/band tee at the top.
    results = search_listings("vintage band tee", size=None, max_price=None)
    assert len(results) > 0
    top = results[0]
    assert "tee" in top["title"].lower() or "band tee" in " ".join(top["style_tags"])


# ── suggest_outfit ─────────────────────────────────────────────────────────────

@requires_groq
def test_suggest_outfit_with_wardrobe():
    item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
    suggestion = suggest_outfit(item, get_example_wardrobe())
    assert isinstance(suggestion, str)
    assert suggestion.strip() != ""


@requires_groq
def test_suggest_outfit_empty_wardrobe_does_not_crash():
    # Failure mode: empty wardrobe → still returns a non-empty styling string.
    item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
    suggestion = suggest_outfit(item, get_empty_wardrobe())
    assert isinstance(suggestion, str)
    assert suggestion.strip() != ""


# ── create_fit_card ────────────────────────────────────────────────────────────

def test_create_fit_card_empty_outfit_returns_message():
    # Failure mode: empty outfit → informative string, NOT an exception, no LLM call.
    item = {"title": "Faded Band Tee", "price": 22.0, "platform": "depop"}
    result = create_fit_card("", item)
    assert isinstance(result, str)
    assert result.strip() != ""
    assert "outfit" in result.lower()  # explains what went wrong


def test_create_fit_card_whitespace_outfit_returns_message():
    result = create_fit_card("   \n  ", {"title": "Faded Band Tee"})
    assert isinstance(result, str)
    assert "suggest_outfit" in result or "outfit" in result.lower()


@requires_groq
def test_create_fit_card_happy_path():
    item = {"title": "Faded Band Tee", "price": 22.0, "platform": "depop"}
    outfit = "Pair with wide-leg jeans and chunky boots for a 90s grunge look."
    caption = create_fit_card(outfit, item)
    assert isinstance(caption, str)
    assert caption.strip() != ""


@requires_groq
def test_create_fit_card_outputs_vary():
    # High temperature should produce different captions on identical input.
    item = {"title": "Faded Band Tee", "price": 22.0, "platform": "depop"}
    outfit = "Pair with wide-leg jeans and chunky boots for a 90s grunge look."
    a = create_fit_card(outfit, item)
    b = create_fit_card(outfit, item)
    assert a != b


# ── check_price (extra credit) ─────────────────────────────────────────────────

def test_check_price_returns_verdict():
    item = search_listings("vintage band tee", size=None, max_price=None)[0]
    result = check_price(item)
    assert result["verdict"] in {"great deal", "fair", "overpriced", "unknown"}
    assert "message" in result and result["message"].strip() != ""


def test_check_price_unknown_when_too_few_comparables():
    # Failure mode: not enough comparables → "unknown", never a misleading verdict.
    lonely_item = {
        "id": "x_999",
        "title": "One-of-a-kind cape",
        "category": "outerwear",
        "style_tags": ["nonexistent-tag-xyz"],
        "price": 40.0,
    }
    result = check_price(lonely_item)
    assert result["verdict"] == "unknown"


def test_check_price_no_price_does_not_crash():
    result = check_price({"id": "x", "category": "tops", "style_tags": ["vintage"]})
    assert result["verdict"] == "unknown"
    assert result["item_price"] is None


# ── bad-type item input (shared guard) ─────────────────────────────────────────
# Passing a non-dict (e.g. the empty list from a no-results search) must NOT raise
# AttributeError — each tool degrades to its own informative response. No LLM call
# is reached, so these run without GROQ_API_KEY.

@pytest.mark.parametrize("bad_item", [[], None, "not a dict", 42])
def test_suggest_outfit_rejects_non_dict_item(bad_item):
    result = suggest_outfit(bad_item, get_example_wardrobe())
    assert isinstance(result, str)
    assert "no valid item" in result.lower()


@pytest.mark.parametrize("bad_item", [[], None, "not a dict", 42])
def test_check_price_handles_non_dict_item(bad_item):
    result = check_price(bad_item)
    assert result["verdict"] == "unknown"
    assert result["item_price"] is None


def test_create_fit_card_tolerates_non_dict_item():
    # Empty outfit is still caught first; with a real outfit + bad item, it should
    # not crash — it degrades to a caption built from defaults.
    result = create_fit_card("", [])  # empty outfit guard fires first
    assert isinstance(result, str) and result.strip() != ""
