# FitFindr — Triggered Failure Modes (Milestone 5)

Each of the three tools has a deliberate failure mode. Below are the exact
commands to trigger each one and the verified output. None raise an exception —
every failure returns a specific, informative response.

To reproduce, run from the project root with the `.AI201_venv` active.
(On Windows, prefix with `PYTHONUTF8=1` so emoji in LLM output prints cleanly.)

---

## Failure 1 — `search_listings` returns zero results

**Trigger:**
```bash
python -c "from tools import search_listings; print(search_listings('designer ballgown', size='XXS', max_price=5))"
```

**Output:**
```
[]
```
Returns an empty list, exit code 0 — no exception.

**Full agent with the same impossible query:**
```bash
python -c "
from agent import run_agent
from utils.data_loader import get_example_wardrobe
s = run_agent('designer ballgown size XXS under \$5', get_example_wardrobe())
print(s['error'])
print('fit_card:', s['fit_card'])
"
```

**Output:**
```
I couldn't find any listings matching "designer ballgown" (size XXS, under $5).
Try raising your max price, dropping the size filter, or using broader keywords.
fit_card: None
```
The agent names *what* failed (the query, the size, the price) and *what to try*
next — it does not just say "no results found." `suggest_outfit` and
`create_fit_card` are never called; `selected_item`, `outfit_suggestion`, and
`fit_card` all stay `None`.

---

## Failure 2 — `suggest_outfit` with an empty wardrobe

**Trigger:**
```bash
python -c "
from tools import search_listings, suggest_outfit
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe
results = search_listings('vintage graphic tee', size=None, max_price=50)
print(suggest_outfit(results[0], get_empty_wardrobe()))
"
```

**Output (example — LLM, varies per run):**
```
To style this adorable Y2K Baby Tee, try pairing it with a flowy white skirt and
sandals for a sweet, cottagecore-inspired look. Alternatively, you could team it
with distressed denim jeans and sneakers for a more casual, vintage vibe...
```
Returns a useful, non-empty styling string. It gives **general** advice (items
the user could find) rather than referencing wardrobe pieces that don't exist —
and it does not raise or return an empty string.

---

## Failure 3 — `create_fit_card` with an empty outfit string

**Trigger:**
```bash
python -c "
from tools import search_listings, create_fit_card
results = search_listings('vintage graphic tee', size=None, max_price=50)
print(create_fit_card('', results[0]))
"
```

**Output:**
```
Can't create a fit card without an outfit suggestion — run suggest_outfit first.
```
A descriptive error-message string, not a Python exception. The guard fires
before any LLM call, so this also costs nothing to run.

---

## Bonus — `check_price` (extra credit) with too few comparables

**Trigger:**
```bash
python -c "
from tools import check_price
print(check_price({'id':'x','category':'outerwear','style_tags':['nonexistent-tag'],'price':40})['verdict'])
"
```

**Output:**
```
unknown
```
Returns `verdict='unknown'` with an explanatory message instead of guessing from
insufficient data. Non-blocking — never stops the agent chain.

---

## Automated coverage

All of the above are also covered by the pytest suite (failure-mode tests run
without an API key since their guards fire before any LLM call):

```bash
pytest tests/ -q
# 23 passed
```
