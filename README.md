# Agentic Commerce — voice-driven, mandate-bound agent checkout

A live demo for the **Pune Product × GCC Forum** (1 Nov 2026, Women in Product India).

Two agents transact with each other, out loud, while a human watches. A shopper
agent works for the buyer, a merchant agent works for the store, and a
**mandate** sits between them deciding what is actually allowed to happen.

You talk to it. It talks back. You approve a payment by saying "approve".

The point of the demo is the thing most agent demos skip: not that an agent can
buy something, but that it can be **stopped**.

---

## Why these three acts

| Act | What the room sees | What it argues |
|---|---|---|
| **1 — Happy path, human in the loop** | Agent shops, finds a ₹2,990 frame, then stops and asks before charging | Autonomy is a dial, not a switch. The ceiling is a product decision. |
| **2 — Out of stock, agent re-plans** | First pick is unavailable; the agent recovers and completes without escalating | Good agent UX is recovering silently, not handing failures back to the human |
| **3 — The mandate refuses** | Buyer asks for a ₹4,200 shawl, then says "split it into two payments" | Code wins, not persuasion. The gate is a function call, not a system prompt. |

Act 3 is the one to spend time on. The agent refuses, explains which rule
blocked it, offers the best in-mandate alternative, and then refuses the
structuring workaround too.

---

## The architecture

```
  Priya (human)
      │  issues a signed, scoped, expiring mandate
      ▼
  shopper_agent ──AgentTool: ask_merchant──▶ merchant_agent
      │                                          │
      │ read_mandate                             │ search_catalog
      │ check_against_mandate                    │ get_product
      │ execute_payment  [human confirmation]    │ suggest_alternative
      ▼
  mandate.py  ← deterministic Python, no LLM
```

Built on **Google ADK** (`google-adk` 2.13). The shopper is `root_agent`, so
`adk web` and `adk run agents` work on this package directly.

**Two enforcement points, deliberately.** The shopper agent is instructed to
preflight every SKU with `check_against_mandate`. But `execute_payment`
re-runs the same check itself. An agent that skips the preflight, hallucinates
an approval, or decides the cap is negotiable still cannot move money. The
prompt is guidance; the tool boundary is the control.

`execute_payment` is wrapped in ADK's `FunctionTool(require_confirmation=True)`,
so the human-in-the-loop pause is the framework's, not a prop.

Receipts are HMAC-SHA256 signed against the mandate id and verified on render.
Tamper with one field and verification fails.

---

## Running it

```bash
./run.sh            # builds the UI if needed, serves everything on :8000
```

Then open <http://127.0.0.1:8000>.

First run from scratch:

```bash
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
cd web && npm install && npm run build && cd ..
./run.sh
```

### Replay vs live

| Mode | What runs | Needs network |
|---|---|---|
| **Replay** (default) | Pre-written agent turns, **real** tools and **real** mandate enforcement | No |
| **Live** | Real ADK `Runner` driving Gemini | Yes, `GOOGLE_API_KEY` |

The key goes in a gitignored, mode-600 `.env` at the repo root, which the
server reads at import. Never the shell profile — a shared laptop leaks that
into every other process.

```
GOOGLE_API_KEY=...
GOOGLE_GENAI_USE_VERTEXAI=FALSE
```

Both modes emit the identical SSE event stream, so the UI has one code path.
**Present in replay.** Venue wifi does not get a vote on whether your demo
works, and replay still runs the genuine mandate logic — the verdicts, the
refusals and the signed receipts on screen are all computed live. Only the
model's prose is pre-written.

### Live mode is less dependable than it looks

Three separate things went wrong wiring it up, and all three happen mid-demo:

- **Models get retired.** `gemini-2.5-flash` now 404s for new keys with a note
  pointing at a newer one.
- **Models get busy.** 503 `UNAVAILABLE` under load.
- **Free-tier quota is 20 requests/day *per model*.** One act costs several, so
  a few rehearsals exhaust a model for 24h.

So live mode walks a `MODEL_CHAIN` and falls through 404 / 429 / 503 to the
next candidate, but only until real content has been emitted — past that point
restarting would duplicate the turn on screen. Because quota is per model, a
spent model does not spend the rest of the chain. Set `ADK_MODEL` to jump the
queue.

If every candidate is spent, the UI says so in plain words instead of showing a
stack trace, and replay still runs the whole demo.

---

## Voice

The demo is meant to be driven by talking to it.

**Output.** Each agent speaks its own turns in its own voice, so the room can
hear an agent-to-agent handoff rather than read one. Voices are chosen from
**on-device** synths only — Chrome's "Google …" voices round-trip to a server
and would fail at the venue. On macOS this usually lands on `Rishi` (en-IN) for
the shopper and `Daniel` (en-GB) for the merchant; the pair in use is shown in
the status bar. macOS novelty voices are excluded by name, because having
"Boing" read out a payment refusal on stage is not a recoverable mistake.

**Input.** Press `M` (or click **Speak**) and talk. Recognised speech is matched
to an intent locally — no model call — and whatever it heard is printed across
the top of the screen so the audience can see it work:

| Say | Does |
|---|---|
| *"I need a gift under three thousand rupees"* | Runs act 1 |
| *"Get me the Kolhapuri juttis"* | Runs act 2 |
| *"Buy the pashmina shawl instead"* | Runs act 3 |
| *"Approve"* / *"Go ahead"* | Approves the pending charge |
| *"Decline"* | Rejects it |
| *"Reset"* / *"Stop"* | Resets, stops |

**Pacing.** `speechSynthesis` gives no completion signal back to the server, so
in voice mode the server spreads each token stream over the *estimated* speaking
time instead of typing at a fixed rate. Captions and audio then start and finish
together. If the captions lag the voice, raise the estimate:

```bash
DEMO_VOICE_WPM=180 ./run.sh    # default 165
```

**The catch worth knowing.** Speech *synthesis* is fully on-device, so the
agents will always talk. Speech *recognition* in Chrome goes to a Google server,
so the mic needs network. If the venue wifi is bad the mic degrades to an error
chip and every act still runs from the keyboard. Rehearse the keyboard path.

---

## Presenting

Keyboard, so you never touch a trackpad on stage:

| Key | Does |
|---|---|
| `1` `2` `3` | Pick an act |
| `Enter` / `Space` | Run the selected act |
| `M` | Talk to it |
| `A` | Approve the pending charge |
| `V` | Mute / unmute the agent voices |
| `Z` | Cycle UI scale 100 / 115 / 130% for the projector |
| `R` | Reset |
| `Esc` | Stop the run and cut the audio |

The header sheds text rather than clipping as the window narrows: act titles
ellipsize, then pill labels drop to their coloured dot, then act titles go
entirely and the numbers carry it. Verified down to 1120px.

Pacing is tunable for the room:

```bash
DEMO_TOKEN_DELAY=0.022 DEMO_STEP_PAUSE=0.42 ./run.sh   # defaults
```

Raise both if the back row is struggling to read the projector.

### Lines that land

- On the mandate pane: *"This is the only thing on screen that can say no, and
  it is ordinary Python. You cannot sweet-talk a function call."*
- At the approval gate: *"Two and a half thousand rupees is where this buyer
  stops trusting the agent. That number is a product decision, and right now
  nobody owns it."*
- At the Act 3 refusal: *"It refused to split the payment. If your agent would
  have said yes there, you do not have a spending control, you have a
  suggestion."*
- After approving by voice: *"I just authorised three thousand rupees by saying
  one word. Everything that made that safe is in the middle column, and none of
  it is in the model."*

### Mapping to the panels

**Designing AI-native user experiences** — there is no cart, no PDP, no checkout
funnel, and with voice on there is no screen to read either. Search, compare,
filter and pay collapse into one conversation. The new surfaces are the
tool-call trace (can the user see what the agent did?), the approval gate (when
does it stop?), and the receipt (what can they audit after?). Voice sharpens the
question: when the interface is audio, the trust layer is the only thing the
user can still inspect — so it had better not be a prompt.

**From delivery to innovation: the new GCC product playbook** — the mandate is a
platform asset, not a ticket. A GCC that owns the trust layer between buyer
agents and merchant agents owns something durable. Worth naming the real
protocols here: Agentic Commerce Protocol (OpenAI/Stripe), AP2 (Google), Visa
Intelligent Commerce.

---

## Layout

```
agents/
  agent.py      two ADK LlmAgents and the AgentTool wiring
  mandate.py    the trust layer: caps, exclusions, HITL ceiling, signed receipts
  tools.py      ADK FunctionTools; execute_payment re-checks the mandate
  catalog.py    20 in-memory products, no network
  script.py     the three acts' pre-written prose
  server.py     FastAPI + SSE; replay and live backends, one event contract
  trace.py      in-process bus for semantic UI events
web/src/
  App.tsx       three-pane shell, presenter keybindings, voice wiring
  useVoice.ts   on-device TTS voice assignment + local speech-intent matching
  useRun.ts     SSE client and event reducer
  components.tsx  lanes, mandate card, checks, gate, receipt, audit
  styles.css    Google palette on white, no webfont CDN, projector scaling
```

## Caveats

No real money, no real payment rail, no persistence — the mandate resets on
every act. The receipt signing key is in source, which a real deployment would
never do; it belongs in a KMS. The catalog is 20 hardcoded products. `zoom:` is
Chrome-only, which is fine for a demo driven from one laptop.

Speech recognition needs network and is Chrome-only; everything else runs
offline. This is a conversation piece for a 2.5-hour forum, not a product.
