# FitFindr — planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Your planning.md will be reviewed as part of your submission.
> Update it before starting any stretch features.

---

## Tools

List every tool your agent will use. For each tool, fill in all four fields.
You must have at least 3 tools. The three required tools are listed — add any additional tools below them.

### Tool 1: search_listings

**What it does:**
<!-- Describe what this tool does in 1–2 sentences -->
Searches the mock listings dataset (loaded via `load_listings()`) and returns the items that match the user's request. It scores each listing on how well it matches the keyword description, then drops anything outside the size or price filters, and returns what's left sorted best-match-first.

**Input parameters:**
<!-- List each parameter, its type, and what it represents -->
- `description` (str): free-text keywords pulled from the user's request, e.g. `"vintage graphic tee"`. Tokenized and matched (case-insensitive) against each listing's `title`, `description`, and `style_tags`.
- `size` (str, optional, default `None`): the size the user wants, e.g. `"M"`. Listing sizes are messy free-text (`"M"`, `"S/M"`, `"W30 L30"`, `"US 8"`), so this is a case-insensitive substring check rather than an exact match. `None` skips the size filter entirely.
- `max_price` (float, optional, default `None`): inclusive upper price bound. A listing passes if `price <= max_price`. `None` skips the price filter.

**What it returns:**
<!-- Describe the return value -->
A `list[dict]`, sorted by descending relevance score. Each element is the full original listing dict — `id`, `title`, `description`, `category`, `style_tags`, `size`, `condition`, `price`, `colors`, `brand`, `platform` — so downstream tools have everything they need. Returns an empty list `[]` when nothing matches.

**What happens if it fails or returns nothing:**
<!-- What should the agent do if the wardrobe is empty or no outfit can be suggested? -->
Returns `[]`. The planning loop treats an empty list as a hard stop: it does **not** call `suggest_outfit`, it writes an error message into the session telling the user how to loosen the search (raise `max_price`, drop the `size` filter, or use broader keywords), and returns early.

---

### Tool 2: suggest_outfit

**What it does:**
<!-- Describe what this tool does in 1–2 sentences -->
Takes the listing the user is about to buy and their existing wardrobe, and writes a short, specific styling suggestion that pairs the new item with pieces they already own. It looks for wardrobe items whose `category`, `colors`, and `style_tags` complement the new item (e.g. a top gets matched with bottoms + shoes in a shared aesthetic).

**Input parameters:**
<!-- List each parameter, its type, and what it represents -->
- `new_item` (dict): a single listing dict — the top result from `search_listings`. Uses its `category`, `colors`, and `style_tags` to decide what pairs well.
- `wardrobe` (dict): the user's closet in the schema format `{"items": [ {id, name, category, colors, style_tags, notes}, ... ]}`, as returned by `get_example_wardrobe()`. May have an empty `items` list.

**What it returns:**
<!-- Describe the return value -->
A `str`: a 1–3 sentence styling suggestion in a friendly stylist voice that names actual wardrobe pieces by their `name` and gives a concrete tip (e.g. *"Pair this with your wide-leg khaki trousers and chunky white sneakers for a 90s streetwear look — roll the sleeves once for shape."*).

**What happens if it fails or returns nothing:**
<!-- What should the agent do if the wardrobe is empty or no outfit can be suggested? -->
If `wardrobe["items"]` is empty (e.g. a brand-new user), it falls back to a **standalone** styling tip that styles the new item on its own — generic complementary pieces rather than owned ones — and never references items that don't exist. It always returns a non-empty string so `create_fit_card` still has something to work with.

---

### Tool 3: create_fit_card

**What it does:**
<!-- Describe what this tool does in 1–2 sentences -->
Turns the outfit suggestion and the new item into a short, casual, ready-to-post social caption — the kind of thing you'd put on a Depop "sold" post or an Instagram story. It pulls the item's name, price, and platform into a first-person, hype-y one-liner.

**Input parameters:**
<!-- List each parameter, its type, and what it represents -->
- `outfit` (str): the styling suggestion string returned by `suggest_outfit` — gives the caption its vibe/aesthetic.
- `new_item` (dict): the same listing dict, used for the concrete details that go in the caption (`title`, `price`, `platform`).

**What it returns:**
<!-- Describe the return value -->
A `str`: a 1–2 sentence caption in lowercase, casual social-media voice with an emoji, e.g. *"thrifted this faded band tee off depop for $22 and honestly it was made for my wide-legs 🖤 full look in my stories"*.

**What happens if it fails or returns nothing:**
<!-- What should the agent do if the outfit data is incomplete? -->
If `outfit` is empty or `new_item` is missing key fields (`title`/`price`/`platform`), it degrades gracefully: it builds a minimal caption from whatever item fields are present (at least the title) instead of crashing. If even the item is missing, it returns a short generic caption and the planning loop notes that the card was generated with limited detail.

---

### Additional Tools (if any)

<!-- Copy the block above for any tools beyond the required three -->

### Tool 4: check_price  *(extra credit — price comparison)*

**What it does:**
<!-- Describe what this tool does in 1–2 sentences -->
Given a listing the user is considering, estimates whether its price is fair by comparing it against *comparable* items already in the dataset (same `category` with at least one shared `style_tag`). It returns a verdict — great deal / fair / overpriced — backed by the median and price range of those comparables, so the user knows if the find is actually worth it.

**Input parameters:**
<!-- List each parameter, its type, and what it represents -->
- `item` (dict): the listing to evaluate — normally `session["selected_item"]`, the top result from `search_listings`. Uses its `id` (to exclude itself), `category`, `style_tags`, `price`, and `title`.

**What it returns:**
<!-- Describe the return value -->
A `dict` with the assessment, so it's easy to display and easy to test:
- `verdict` (str): one of `"great deal"`, `"fair"`, `"overpriced"`, or `"unknown"` (when there isn't enough comparable data).
- `item_price` (float): the item's own price.
- `comparable_count` (int): how many comparable listings were found.
- `median_price` / `min_price` / `max_price` (float | None): the price stats of the comparables (None when no comps).
- `message` (str): a human-readable one-liner, e.g. *"At $24, this faded band tee is a great deal — comparable graphic tees run $19–$30 (median $25)."*

**Comparison logic:**
Filter the full dataset to listings with the same `category` AND ≥1 overlapping `style_tag`, excluding the item itself by `id`. Take the median of their prices. Then: `price ≤ 0.85 × median` → **great deal**; within `0.85×–1.15× median` → **fair**; `> 1.15 × median` → **overpriced**.

**What happens if it fails or returns nothing:**
<!-- What should the agent do if the outfit data is incomplete? -->
If fewer than 3 comparables are found (too thin to judge), it returns `verdict="unknown"` with a message saying there isn't enough comparable data to assess the price, rather than giving a misleading verdict. It never raises — a missing `price` or empty dataset still returns a well-formed `unknown` dict.

**Where it fits in the loop:** runs right after `search_listings` selects the top item (Step 4 below), before `suggest_outfit`. Its result is stored in `session["price_check"]` and surfaced to the user alongside the listing. It is **non-blocking** — an `"unknown"` verdict does not stop the chain; styling and the fit card still proceed.

---

## Planning Loop

**How does your agent decide which tool to call next?**
<!-- Describe the logic your planning loop uses. What does it look at? What conditions change its behavior? How does it know when it's done? -->
The loop is a fixed three-stage pipeline (search → suggest → card) where each stage's output is the gate for the next. It's not a free-form "pick any tool" loop — the order is fixed, but the branches decide whether we continue or stop early. In pseudocode:

```
1. Parse the user query into search params:
   description = keywords from the request
   size       = size if the user mentioned one, else None
   max_price  = budget if the user mentioned one, else None

2. results = search_listings(description, size, max_price)
   IF results is empty:
       session["error"] = "No listings matched..."  (with loosen-the-search advice)
       RETURN session            # ← early exit, suggest_outfit is never called
   ELSE:
       session["selected_item"] = results[0]   # top-ranked match

2b. (EXTRA CREDIT) session["price_check"] = check_price(session["selected_item"])
    # Non-blocking: an "unknown" verdict never stops the chain.

3. suggestion = suggest_outfit(session["selected_item"], session["wardrobe"])
   # suggest_outfit handles the empty-wardrobe case internally and always
   # returns a non-empty string, so there's no early-exit branch here.
   session["outfit_suggestion"] = suggestion

4. card = create_fit_card(session["outfit_suggestion"], session["selected_item"])
   session["fit_card"] = card

5. RETURN session   # loop is done — all three artifacts are populated
```

**What it looks at to branch:** the only hard branch is step 2 — `if results == []`. That's the single point where the chain can terminate early. Steps 3 and 4 always run once we have a selected item, because both tools are written to degrade gracefully rather than fail. **How it knows it's done:** the pipeline ends after `create_fit_card` populates `session["fit_card"]` (success), or immediately when `session["error"]` is set (failure). Either way it returns the session once and does not loop again.

---

## State Management

**How does information from one tool get passed to the next?**
<!-- Describe how your agent stores and accesses state within a session. What data is tracked? How is it passed between tool calls? -->
Everything lives in a single `session` dict that the planning loop creates at the start of a request and threads through every stage. Tools don't talk to each other directly — each one reads what it needs out of `session` and the loop writes the result back in. That keeps the tools independent and easy to test in isolation.

The session tracks:

| Key | Type | Set by | Read by |
|-----|------|--------|---------|
| `user_query` | str | loop (from user input) | parsing step |
| `search_params` | dict (`description`, `size`, `max_price`) | loop (parse step) | `search_listings` |
| `results` | list[dict] | `search_listings` | loop (empty-check) |
| `selected_item` | dict | loop (`results[0]`) | `suggest_outfit`, `create_fit_card` |
| `wardrobe` | dict | loop (`get_example_wardrobe()` / `get_empty_wardrobe()`) | `suggest_outfit` |
| `outfit_suggestion` | str | `suggest_outfit` | `create_fit_card`, final output |
| `fit_card` | str | `create_fit_card` | final output |
| `error` | str or None | loop (on empty results) | final output |

Flow of data between calls: `search_listings` writes `results` → loop copies `results[0]` into `selected_item` → that same dict is passed into both `suggest_outfit` and `create_fit_card` → `outfit_suggestion` flows from the second tool into the third. The wardrobe is loaded once and stored on the session so it doesn't get re-read per call.

---

## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No results match the query | Stop the chain (don't call `suggest_outfit`). Tell the user plainly: *"I couldn't find anything matching 'vintage graphic tee' in size M under $30."* Then offer a concrete next step based on which filter was tightest — e.g. *"Want me to try up to $40, or drop the size filter? There are a couple of close matches just above your budget."* No empty data is ever passed downstream. |
| suggest_outfit | Wardrobe is empty | Don't error out. Switch to standalone styling: style the new item using generic complementary pieces and call out that it's a from-scratch suggestion — *"You haven't added a wardrobe yet, so here's how I'd style it on its own: pair this faded band tee with baggy jeans and chunky boots for a 90s grunge fit."* Optionally invite the user to add wardrobe items for personalized pairings. Still returns a usable string. |
| create_fit_card | Outfit input is missing or incomplete | Degrade gracefully instead of failing. Build the caption from whatever fields exist — at minimum the item `title` — and skip price/platform if absent (*"obsessed with this faded band tee 🖤"*). The loop flags internally that the card was made with limited detail, but the user still gets a postable caption rather than an error. |
| check_price *(EC)* | Fewer than 3 comparable listings to judge against | Don't guess. Return `verdict="unknown"` with *"Not enough comparable listings to judge this price."* The chain is **not** blocked — `suggest_outfit` and `create_fit_card` still run; the user simply sees no price verdict. |

---

## Architecture

<!-- Draw a diagram of your agent showing how the components connect:
     User input → Planning Loop → Tools (search_listings, suggest_outfit, create_fit_card)
                                                                          ↕
                                                                   State / Session
     Show what triggers each tool, how state flows between them, and where error paths branch off.
     ASCII art, a Mermaid diagram (https://mermaid.js.org/syntax/flowchart.html), or an embedded
     sketch are all fine. You'll share this diagram with an AI tool when asking it to implement
     the planning loop and each individual tool. -->

```
User query
    │
    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ PLANNING LOOP                                                             │
│                                                                           │
│  parse query → search_params {description, size, max_price}               │
│    │                                                                      │
│    ├─► search_listings(description, size, max_price) ──┐                  │
│    │        │                                          │ reads/writes     │
│    │        │  results == []                           ▼                  │
│    │        ├──► [ERROR] session.error =          ┌──────────────┐        │
│    │        │     "No listings matched…(loosen)"  │   SESSION    │        │
│    │        │            │                         │   STATE      │        │
│    │        │            └────────► RETURN ───────►│              │        │
│    │        │                       (early exit)   │ user_query   │        │
│    │        │  results == [item, …]                │ search_params│        │
│    │        ▼                                       │ results      │        │
│    │   session.selected_item = results[0] ────────►│ selected_item│        │
│    │        │                                       │ wardrobe     │        │
│    ├─► suggest_outfit(selected_item, wardrobe) ────►│ outfit_sug.  │        │
│    │        │   (empty wardrobe → standalone tip)   │ fit_card     │        │
│    │   session.outfit_suggestion = "…" ────────────►│ error        │        │
│    │        │                                       └──────┬───────┘        │
│    └─► create_fit_card(outfit_suggestion, ──────────┐     │                │
│             selected_item)                          │ reads│ writes        │
│             │  (missing fields → minimal caption)   ▼     │                │
│        session.fit_card = "…" ◄──────────────────────────┘                │
│             │                                                             │
└─────────────┼─────────────────────────────────────────────────────────────┘
              ▼
   Return session  →  listing + outfit suggestion + fit card shown to user
              ▲
              └─ error path from search_listings returns here too
                 (shows only session.error, no outfit / card)
```

**How to read it:** the planning loop is the only thing that calls tools; tools never call each other. Each tool reads its inputs from SESSION STATE and the loop writes results back. The single early-exit branch is the `results == []` path off `search_listings` — that's where the flow terminates before `suggest_outfit`/`create_fit_card` and returns just the error. The happy path falls straight through all three tools and returns the full session.

---

## AI Tool Plan

<!-- For each part of the implementation below, describe:
     - Which AI tool you plan to use (Claude, Copilot, ChatGPT, etc.)
     - What you'll give it as input (which sections of this planning.md, your agent diagram)
     - What you expect it to produce
     - How you'll verify the output matches your spec before moving on

     "I'll use AI to help me code" is not a plan.
     "I'll give Claude my Tool 1 spec (inputs, return value, failure mode) and ask it to implement
     search_listings() using load_listings() from the data loader — then test it against 3 queries
     before trusting it" is a plan. -->

**Milestone 3 — Individual tool implementations:**

**Milestone 4 — Planning loop and state management:**

---

## A Complete Interaction (Step by Step)

**What FitFindr needs to do (in my own words):**
FitFindr is a secondhand-shopping stylist agent: it takes a user's request (an item, a budget, a size, and their personal style) and runs a three-step chain. A search request triggers `search_listings`, which filters the mock listings by description/style, `size`, and `max_price`; if it finds matches, the top result triggers `suggest_outfit`, which pairs that item against the user's wardrobe, and that suggestion triggers `create_fit_card` to write a short social caption. If `search_listings` returns nothing, the agent stops the chain and tells the user how to loosen their query (e.g. raise the price or drop the size filter) — it never passes empty input into `suggest_outfit` — and if the wardrobe is empty, `suggest_outfit` falls back to standalone styling tips instead of referencing owned pieces.

Write out what a full user interaction looks like from start to finish — tool call by tool call. Use a specific example query.

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1:**
<!-- What does the agent do first? Which tool is called? With what input? -->
Search: search_listings("vintage graphic tee", size="M", max_price=30.0) returns 3 matching listings sorted by relevance. FitFindr picks the top result: "Faded Band Tee — $22, Depop, Good condition."

**Step 2:**
<!-- What happens next? What was returned from step 1? What tool is called now? -->
Suggest outfit: suggest_outfit(new_item=<band tee>, wardrobe=<user's wardrobe>) returns: "Pair this with your wide-leg jeans and platform Docs for a classic 90s grunge look. Roll the sleeves once and tuck the front corner slightly for shape."

**Step 3:**
<!-- Continue until the full interaction is complete -->
Fit card: create_fit_card(outfit=<suggestion>, new_item=<band tee>) returns: "thrifted this faded band tee off depop for $22 and honestly it was made for my wide-legs 🖤 full look in my stories"

**Final output to user:**
<!-- What does the user actually see at the end? -->
The user sees the matched listing (Faded Band Tee — $22, Depop, Good condition), the styling suggestion (wide-leg jeans + platform Docs, 90s grunge), and the ready-to-post fit card caption — all three combined into one response.
