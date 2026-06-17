# FitFindr 🛍️

basically a thrift-shopping stylist agent. you type what you want in normal english
(item + budget + size + your vibe) and it does three things: searches a fake listings
dataset, styles the best match against your closet, and writes a caption you could
actually post. under the hood it's a planning loop calling a few tools and passing
state between them.

example: `vintage graphic tee under $30` → finds the Y2K Baby Tee ($18, Depop, says
it's a great deal) → pairs it with your baggy jeans + chunky sneakers → spits out a
thrift-haul caption. that's the whole thing.

## setup

```bash
pip install -r requirements.txt
```

put your Groq key in a `.env` (free at console.groq.com):
```
GROQ_API_KEY=your_key_here
```

## running it

```bash
python agent.py        # CLI — runs the happy path + the no-results case
python app.py          # the gradio web UI
pytest tests/          # 23 tests, covers every tool + every failure mode
```

heads up: captions sometimes have emoji and Windows' default console chokes on them.
the CLI already forces utf-8, but if you call the tools in your own script do
`PYTHONUTF8=1 python ...`.

## what's where

```
tools.py        the four tools
agent.py        the planning loop (run_agent) + query parser + the session dict
app.py          gradio ui (handle_query)
tests/          pytest
planning.md     the design doc i filled out before coding
FAILURE_MODES.md   proof i actually triggered each failure (milestone 5)
data/ + utils/  the listings, wardrobe schema, and loader helpers
```

---

## the tools

**1. `search_listings(description, size, max_price)` → `list[dict]`**
finds listings that match, ranked best first. the only tool that can stop the whole
thing early (when nothing matches).
- `description` (`str`) — keywords like `"vintage graphic tee"`, matched against each
  listing's title/description/style_tags, case-insensitive.
- `size` (`str | None`) — like `"M"`. it's a substring check, not exact, because the
  sizes in the data are all over the place (`"S/M"`, `"W30 L30"`, `"US 8"`). `None` = skip.
- `max_price` (`float | None`) — ceiling, inclusive. `None` = skip.
- returns the full listing dicts (id, title, description, category, style_tags, size,
  condition, price, colors, brand, platform), sorted by a relevance score (title/tag
  hits count 2×, description hits 1×). empty list if nothing matches.

**2. `suggest_outfit(new_item, wardrobe)` → `str`**
styles the picked item using your closet. this one hits the LLM.
- `new_item` (`dict`) — the listing you're looking at.
- `wardrobe` (`dict`) — `{"items": [...]}`, can be empty.
- returns a 2-3 sentence styling blurb that names your actual pieces. Groq
  `llama-3.3-70b-versatile`, temp 0.7.

**3. `create_fit_card(outfit, new_item)` → `str`**
turns the outfit into a casual caption you'd post. also LLM.
- `outfit` (`str`) — the blurb from suggest_outfit.
- `new_item` (`dict`) — same listing, for the name/price/platform.
- returns a short lowercase OOTD caption. temp cranked to **1.1** so it's different
  every time instead of the same line.

**4. `check_price(item)` → `dict`**  *(extra credit)*
tells you if the price is actually fair vs similar stuff in the data.
- `item` (`dict`) — the picked listing.
- returns a dict: `verdict` (great deal / fair / overpriced / unknown), plus
  `item_price`, `comparable_count`, `median_price`, `min_price`, `max_price`, `message`.
  comparables = same category + at least one shared style tag. verdict is off the median:
  `≤0.85×` deal, `0.85–1.15×` fair, `>1.15×` overpriced.

---

## planning loop

it's just a fixed pipeline — search → suggest → card — where each step's output feeds
the next. the order's fixed, the *branch* is what decides if it keeps going or bails.

1. parse the query into `{description, size, max_price}`.
2. `search_listings(...)`. **this is the one branch.** if it comes back empty, set
   `session["error"]` with actual advice and return right there — suggest_outfit and
   create_fit_card never run on empty input.
3. grab `results[0]` as `selected_item`.
4. `check_price(selected_item)` → `session["price_check"]`. non-blocking, an "unknown"
   verdict doesn't stop anything.
5. `suggest_outfit(selected_item, wardrobe)` → `outfit_suggestion`.
6. `create_fit_card(outfit_suggestion, selected_item)` → `fit_card`.
7. return the session.

the point is it actually behaves differently per input. matching query = all four tools
run. impossible query (`designer ballgown size XXS under $5`) = only search runs and you
get the error, everything else stays `None`. so it's not just a script that always does
the same thing.

## state management

one `session` dict per request, passed through every step. the tools don't talk to each
other — each one reads what it needs out of `session` and the loop writes results back in.
keys: `query`, `parsed`, `search_results`, `selected_item`, `wardrobe`, `price_check`,
`outfit_suggestion`, `fit_card`, `error`.

flow: search writes `search_results` → loop copies `search_results[0]` into
`selected_item` → that **same dict** goes into check_price, suggest_outfit, and
create_fit_card. i checked `selected_item is search_results[0]` and it's `True`, so
nothing's getting re-searched or re-typed between steps.

query parsing is just regex — pulls the price (`under $30`, `$30`, `up to 40`) and size
(`size M`, `size 8.5`) out, then strips those bits from the description so `"$30"` doesn't
accidentally match listing tokens like `"501"` or `"2003"`. whatever's left is the search
keywords.

## error handling

nothing raises — every failure returns something useful instead. there's a little shared
`_is_valid_item()` guard at the top of the tools that take a dict.

| tool | what breaks | what happens | real example from testing |
|------|-------------|--------------|---------------------------|
| `search_listings` | nothing matches | returns `[]`, loop sets an error that names the query/size/price + what to try | `run_agent("designer ballgown size XXS under $5")` → `error = "I couldn't find any listings matching \"designer ballgown\" (size XXS, under $5). Try raising your max price, dropping the size filter, or using broader keywords."`, `fit_card = None` |
| `suggest_outfit` | empty wardrobe | gives general styling instead, never makes up items you don't own | `suggest_outfit(tee, get_empty_wardrobe())` → *"To style this adorable Y2K Baby Tee, try pairing it with a flowy white skirt and sandals…"* |
| `suggest_outfit` | someone passes a non-dict (like the empty list from a failed search) | clean message, no AttributeError | `suggest_outfit([], …)` → *"I couldn't put together an outfit — no valid item was provided…"* |
| `create_fit_card` | empty outfit string | error string *before* it even calls the LLM | `create_fit_card("", item)` → *"Can't create a fit card without an outfit suggestion — run suggest_outfit first."* |
| `check_price` | <3 comparables / no price | `verdict="unknown"` instead of guessing, doesn't block anything | `check_price({…,"style_tags":["nonexistent-tag"]})` → `"unknown"` |

all the exact commands + outputs are in `FAILURE_MODES.md`.

## spec reflection

couple things ended up different from what i wrote in planning.md:

- **size went optional.** my walkthrough had `search_listings(..., size="M", ...)` but the
  example query never actually says a size. since size is a strict substring filter, a
  random `size="M"` would quietly hide good listings — so i let the parser leave it `None`
  unless the user says one.
- **added the input guard after testing.** the plan assumed each tool always gets a valid
  dict (the loop does guarantee that). but when i tested the tools alone, passing the empty
  list from a no-results search blew up with an AttributeError. added `_is_valid_item()` so
  it returns a message instead — which is what the spec said failures should do anyway.
- **check_price stays non-blocking.** decided up front an "unknown" price can't stop the
  chain, and kept it that way so the extra-credit tool didn't become a new way to fail.
- **the utf-8 thing** wasn't in the plan at all — found it when an emoji caption crashed the
  Windows console. logic was fine, just had to fix the CLI's print.

## ai usage

i used **Claude for code generation** — taking the specs + diagram i'd
already written in planning.md and turning them into code. the design, the reviewing, and
the testing were mine; Claude didn't make any of the design calls. two specific times:

**1. search_listings.** gave it the Tool 1 block from planning.md — the param table
(description/size/max_price + the note that sizes are messy free-text), the return spec, and
the failure mode (return `[]`, never raise). it produced a filter thenscore function using
`load_listings()`. i changed it to weight title/style_tag matches higher than description
matches (2× vs 1×) so a real graphic tee beats something that just says "graphic" in its
blurb, added a stopword list, and moved the price/size stripping into the parser so `"$30"`
couldn't match tokens like `"501"`. tested all three filters on real queries before trusting it.

**2. the planning loop (run_agent).** gave it the Planning Loop pseudocode + State Management
section + the ascii architecture diagram (the one showing the single early-exit off
search_listings). it produced the 7-step run_agent writing into the session dict. i reviewed
it for my branch — it *had* to return early on empty results and not call all
three tools unconditionally. i also slotted the check_price call in as a non-blocking step
and rewrote the error message to actually name the size/price instead of a generic "no
results." confirmed `selected_item is search_results[0]` to make sure state passed by
reference and nothing was re-derived.

---

## the data (quick note)

`data/listings.json` — 40 fake listings across tops/bottoms/outerwear/shoes/accessories and
a bunch of styles. fields: id, title, description, category, style_tags, size, condition,
price, colors, brand, platform.

`data/wardrobe_schema.json` — the wardrobe item format, plus `example_wardrobe` (10 items,
`get_example_wardrobe()`) and `empty_wardrobe` (new user, `get_empty_wardrobe()`).
