# Daily Lead Follow-Up Toolkit (prototype)

A morning call sheet built on this repo's Follow Up Boss (FUB) client. It is designed for a Metro Vancouver / Fraser Valley buyer-lead workflow where most leads come from Facebook ads:

**call → collect criteria → send listings → follow up with something of value → book showings → book appointments.**

> **Status:** prototype. It runs on **fictional mock data** by default. The live FUB connection is **read-only, disabled by default, and not yet tested against a real account.**

---

## What it does

| # | Capability | Where it lives |
|---|---|---|
| 1 | Ranks leads by who needs follow-up most urgently (with reasons) | `fub_toolkit/engine.py` |
| 2 | Finds overdue tasks, including tasks with no contact linked | `fub_toolkit/report.py` |
| 3 | Summarizes recent notes, calls and texts (last 30 days, newest first) | `fub_toolkit/activity.py` |
| 4 | Extracts buyer criteria, each value with the note it came from | `fub_toolkit/criteria.py` |
| 5 | Builds the daily call list plus a separate text/email list | `fub_toolkit/report.py` |
| 6 | Recommends the next action, a text draft and a follow-up date | `fub_toolkit/engine.py` |

## Quick start

```bash
# from the repo root
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

python -m fub_toolkit daily                          # this morning's call sheet (mock data)
python -m fub_toolkit --as-of 2026-09-26 daily       # a fixed date (matches the tests)
python -m fub_toolkit daily --format csv --out today.csv   # print it or load it into a dialer
python -m fub_toolkit daily --format json            # for automations
python -m fub_toolkit lead 101                       # one lead's full card with evidence
python -m fub_toolkit tasks                          # overdue tasks only
python -m fub_toolkit criteria                       # extracted criteria for every lead
python -m fub_toolkit --agent Karan daily            # name used in text drafts (or set AGENT_NAME)
```

After `pip install -e .`, `fub-daily` is the same as `python -m fub_toolkit`.

Run the tests:

```bash
pytest tests/test_fub_toolkit.py --no-cov -q    # toolkit only (62 tests, about 1 second)
pytest --no-cov -q                               # whole repo (see "Known pre-existing failures")
```

## The morning sheet

Sections, in the order you work them:

1. **Call list (ranked).** For each lead: phone number, temperature, score, *why now*, what they want, situation, decision makers, the last 3 touches, overdue tasks, questions still to ask, a text to send if there's no answer, and the next follow-up date.
2. **Texts & emails.** Appointment confirmations, listing sends, nurture value touches and "move to nurture" messages.
3. **Overdue tasks**, most overdue first.
4. **Upcoming appointments.**
5. **Clean up in FUB.** Leads that should stop appearing: under contract, working with another agent, do not contact, and so on.
6. **Not due today**, with each lead's next step and date so nothing drops.

The sheet sets targets: finish the call list before 11 a.m., reach conversations with 40% of the list (an assumption; tune it to your own contact rate), and set at least one appointment.

## How ranking works

Each lead gets points, and every point comes with a reason string that you see on the sheet. The weights are in `engine.WEIGHTS`.

| Signal | Points |
|---|---|
| Lead replied or called in and hasn't heard back | +100 |
| New lead (≤7 days old), never contacted | +90 (+10 if under 24h) |
| Older lead, never contacted | +60 |
| Appointment in the next 48h | +40 |
| Overdue tasks | +12 each (max 3) + up to 15 for age |
| Tasks due today | +8 each (max 2) |
| Follow-up due by cadence | +25, +3 per day late (max +20) |
| Viewed/saved a property in the last 3 days (7 days) | +20 (+10) |
| Timeline ≤3 months (≤6 months) | +20 (+10) |
| Pre-approved or cash | +10 |
| "Just browsing" or "not interested" mentioned | −15 |
| 6+ attempts and never reached | −20 |

**Temperature:**
- **Hot:** a hot stage, timeline ≤3 months, just replied, appointment booked, repeated property views, or pre-approved with timeline ≤6 months.
- **Nurture:** a nurture stage, timeline >6 months, "just browsing", or unreachable after 6 attempts.
- **Sphere:** past clients.
- **Warm:** everything else.

**Cadence** (days between touches after a conversation): Hot 2 · Warm 4 · Nurture 21 · Sphere 90.

For leads you have never reached, the gap between attempts is 1 day for attempts 1–3 and 3 days for attempts 4–6. After that the lead is moved to nurture.

## Next-action decision tree

The first rule that matches wins:

1. They replied → **Reply now** (call; text if no answer).
2. Appointment within 48h → **Confirm appointment**.
3. Never contacted → **Speed to lead** (call twice, then text referencing the ad).
4. Never reached, fewer than 6 attempts → **Contact attempt #n**. The text angle changes with each attempt: follow-up, then a listings offer, then "still looking?".
5. Never reached after 6 attempts → **Move to long-term nurture** (a "break-up" text, plus a stage change).
6. Past client → **Referral check-in**.
7. Nurture → **Send something of value** (listings or a market snapshot from the current FVREB/GVR report).
8. Criteria incomplete → **Qualification call**, using the 3 most important missing questions.
9. Buying within 6 months, not pre-approved → **Offer a mortgage broker intro**.
10. No listings sent → **Set up alert + send 3 hand-picked listings**.
11. Showing done → **Showing debrief + next step** (next showing or buyer consultation).
12. Otherwise → **Book a showing**, naming the property they viewed if known.

Leads with the stage Closed, Trash or Pending, a `DNC` / `Do Not Contact` tag, or notes saying *working with another agent*, *already bought*, *do not contact* or *wrong number* are taken off the lists. They appear under **Clean up in FUB** instead.

## Criteria extraction

Criteria are read from the FB lead-form answers (`background` and custom fields), agent notes, call notes and the lead's own texts. Sources are read oldest to newest, so newer information wins.

It captures:
- areas (about 50 Metro Vancouver and Fraser Valley places and neighbourhoods)
- property type, bedrooms and bathrooms
- budget range and timeline
- pre-approval, cash, current situation (renting, needs to sell, first-time buyer)
- must-haves (suite, garage, shop, RV parking, yard and so on)
- motivation, decision makers, and red flags

**Safeguards:**
- Where a lead *lives now* ("renting in Burnaby") is kept separate from where they want to buy.
- Negated flags ("not working with another agent") are ignored.
- A lead-form *question* ("Are you pre-approved?") is never read as the answer.

Every extracted value keeps its source snippet. `python -m fub_toolkit lead <id>` shows **where each criterion came from**.

This is rule-based. It will miss unusual phrasing, so check the notes before quoting criteria back to a client.

## Data sources

| `--source` | What it does |
|---|---|
| `mock` (default) | 17 fictional leads covering every recommendation path. Dates are relative to `--as-of`. |
| `file --file bundle.json` | A saved bundle shaped like `{"people": [], "tasks": [], "notes": [], "calls": [], "textMessages": [], "appointments": [], "events": []}` |
| `live` | Follow Up Boss API, **GET only**. Blocked unless `FUB_TOOLKIT_ALLOW_LIVE=1` is set. |

---

## Before connecting your live Follow Up Boss account

### What access is required

| Item | Needed? | Notes |
|---|---|---|
| **FUB API key** | Yes | Every user has one under **Admin → API**. The key has **the same access as the user it belongs to**: an Owner sees everything, an Agent sees only their assigned contacts. Use **your own agent-level key**, not an Owner/Admin key, unless you truly need team-wide data. |
| **X-System / X-System-Key** | Recommended | Registering your "system" with FUB gives you higher rate limits and identifies the integration. Without it, FUB allows a much lower request rate (a sliding 10-second window). |
| FUB plan feature: API key restrictions | Optional | FUB offers a "Power-Up" to restrict API keys. If your brokerage uses it, the Owner may have to allow your key. |
| Write permissions | **No** | The toolkit only reads. The client hard-blocks POST, PUT and DELETE (`ReadOnlyViolation`). |
| Webhooks | No | Not used. Webhook management needs Owner access anyway. |

**Endpoints read:** `GET /people`, `/tasks`, `/appointments`, and per person `/notes`, `/calls`, `/textMessages`, `/events`.

A run of 75 people costs about 75 × 4 + 3 ≈ 300 requests. The toolkit caps people (`--max-people`) and pages, and pauses between requests.

### Checklist (do these in order)

1. **Check with your brokerage.**
   - Confirm your brokerage's privacy policy and managing broker allow exporting client data to a local script.
   - Client personal information is covered by BC's *Personal Information Protection Act* (PIPA); confirm how your brokerage wants you to handle it.
   - Confirm whether a team or brokerage FUB account means other agents' leads could be visible to your key.
2. **Use a dedicated key on your own user.** Never commit it to git. Put it in a local `.env` file, which is already git-ignored:
   ```
   FOLLOW_UP_BOSS_API_KEY=...
   X_SYSTEM=YourSystemName
   X_SYSTEM_KEY=...
   ```
3. **Keep debug logging off.** Before this change, the SDK printed every response (names, phones, notes) and the X-System-Key to the console. That output is now opt-in via `FOLLOW_UP_BOSS_DEBUG=1`, and the key is masked. Leave it off with real data.
4. **Do a supervised dry run** with a small cap:
   ```bash
   FUB_TOOLKIT_ALLOW_LIVE=1 python -m fub_toolkit --source live --max-people 10 daily
   ```
   Compare the output against FUB for those 10 people. Things to check:
   - Stage names match yours (e.g. "Hot Prospect", "Nurture", "Past Client").
   - Call outcomes and `isIncoming` flags come through.
   - Task `dueDate` / `isCompleted` are correct.
   - Your Facebook lead-form answers land in `background` or custom fields.
   - The API's `sort` and filter parameters behave as expected.

   The field and parameter names come from the SDK and FUB docs, but they have **not been verified against a real account**.
5. **Tune for your data:** stage names in `engine.py` (`HOT_STAGES`, `NURTURE_STAGES`, …), cadence, weights, and area aliases.
6. **Keep outputs private.** CSV and JSON reports contain client PII. Save them under `reports/`, which is git-ignored, and don't upload them anywhere public.
7. **Rotate the key** if it is ever exposed. Regenerating it in FUB invalidates the old one.

### Messaging reminders

- Text drafts are suggestions. **You** send them. Nothing is sent automatically.
- Commercial electronic messages in Canada fall under CASL. Identify yourself, honour opt-outs (the toolkit flags "stop texting / remove me"), and confirm your brokerage's consent practices for Facebook leads.
- Don't quote market statistics from memory. Pull the current FVREB/GVR monthly figures.

---

## Known limitations

- The criteria parser is regex-based. Uncommon phrasing will be missed, and a mention of a current home can occasionally read as a want. Evidence is shown so you can catch this.
- There's no listing/MLS data, so the toolkit tells you *to* send listings but can't pick them.
- Live adapter: one request per person per activity type (no bulk endpoint used), and unverified against a real account.
- "Listings sent" is detected from notes, texts and tags (`Listings Sent`, `Listing Alert`, `Saved Search`). Tag consistently in FUB for best results.

## Known pre-existing test failures (not caused by this toolkit)

Seven existing tests (`test_corrected_apis`, `test_fub_api_direct`, `test_people_unclaimed` ×3, one test each in `test_enhanced_client` and `test_enhanced_people`) call the real FUB API. They fail without an API key and network access. They are not marked `integration`, so they run by default.
