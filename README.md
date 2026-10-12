# JackTen

A No-Limit Texas Hold'em bot for the NDJSON tournament engine, built around a
maximum-likelihood opponent model.

Most bots play the same way against everyone at the table. JackTen's design goal
is the opposite: hold a live, probabilistic read on each opponent and deviate
from a solid baseline strategy only as far as the accumulated evidence actually
justifies. With no hands observed, it plays its baseline. As reads sharpen, it
exploits.

## Quick start

Python 3.10+, standard library only.

```bash
python play.py                     # opens http://127.0.0.1:8765
python simulate.py --bots "jackten=cmd:python my_bot.py" random caller raiser --matches 500
python -m unittest discover tests
```

`play.py` opens a home page with three modes:

| Mode | What you get |
|---|---|
| **Play** | You in seat 0 against up to nine bots. Raise slider with pot-size presets, keyboard shortcuts. |
| **Watch** | Bots only, cards face up. Leaderboard, pause, adjustable speed. |
| **Simulate** | Parallel matches with live progress, cumulative-winnings and bb/100 charts, a per-bot stats table, and CSV downloads. |

`simulate.py` runs the same simulations from the terminal.

Bot specs:

| Spec | What it is |
|---|---|
| `random`, `caller`, `raiser`, `folder` | Built-in bots |
| `cmd:<command>` | Any program speaking the NDJSON protocol |
| `py:module:Class` | An in-process Python class |
| `label=spec` | Any of the above, with a display name |

[`bots/random_bot.py`](bots/random_bot.py) is the template for an external bot.

Each simulation run writes to `data/sims/<run id>/`, which is gitignored:

| File | Contents |
|---|---|
| `bot_summary.csv` | Per-bot stats: bb/100 with a 95% CI, placement, VPIP, PFR, 3-bet, AF, WTSD, W$SD |
| `matches.csv` | Final stack and finishing place per seat per match |
| `hands.csv` | One row per player per hand: cards, position, result, HUD flags |
| `actions.csv` | Every decision with the context the bot saw (pot, to_call, legal actions), what it did, and think time |
| `pots.csv` | Every main and side pot, with eligibility and winners |
| `cumulative_winnings.csv` | Running net bb per bot |
| `errors.csv` | Bot timeouts and invalid responses |
| `histories/*.ndjson` | Raw protocol logs |

Every column is documented in [`docs/sim_outputs.md`](docs/sim_outputs.md). `hole_cards` columns hold ground truth for every player, including folded hands.

## Bot versions

Each version is a frozen copy of the bot in its own package, so versions can play each other in `simulate.py`. `bot/` is the working copy and currently matches `bot_v2`.

| Version | Package | Features |
|---|---|---|
| **v1** | `bot_v1/` | <ul><li>Phase 1 baseline: equity vs one random hand</li><li>Exact enumeration from the flop, Monte Carlo preflop (fixed 2,000 samples)</li><li>Call when equity beats pot odds, `call / (pot + call)`</li><li>Raise at 70% equity or more, sized at 0.75 of the pot</li><li>Check when free, always-legal fallback action</li></ul> |
| **v2** | `bot_v2/` | <ul><li>Everything in v1</li><li>Hand potential from the same simulation: positive (behind now, improves) and negative (ahead now, outdrawn)</li><li>Call price cut by 0.30 &times; positive potential (implied odds) and raised by 0.30 &times; negative potential (reverse implied odds)</li><li>Raise threshold lowered by 0.10 &times; negative potential, to charge draws</li><li>Monte Carlo sample count set by standard error: stop at SE 0.01, capped at 10,000 samples</li></ul> |

Head-to-head (3000 matches, 100,000 stacks, 50/100 blinds): v2 is statistically indistinguishable from v1, at -3.3 BB per seat per match &plusmn; 35.8 (95% CI). It still plays loose and passive (about 61% VPIP, 2.8% PFR) because both versions compare equity against one random hand.

## Status

Early. The engine, harness and a Phase 1–2 bot are built; opponent modelling is not.

| Component | State |
|---|---|
| Engine protocol spec | Documented — [`poker_bot_messages.md`](poker_bot_messages.md) |
| Local engine, web app (play / watch / simulate), CSV export | Built — `engine/`, `ui/`, `play.py`, `simulate.py` |
| Foundation — bot-side protocol I/O | Done — `bot/main.py` |
| Phase 0 — combinatorics | Done — `bot/combinatorics.py` |
| Phase 1 — equity and hand potential | Done — `bot/equity.py` |
| Phase 2 — pot odds and single-decision EV | Done — `bot/exp_value.py`; beats always-call by about +580 bb/100 (3 vs 3, 22k hands) |
| Phases 3–5 — multiway, ranges, sizing | Not started |
| Phase 6 — opponent statistics (Beta-Binomial) | Not started |
| Phase 7 — exploitation | Not started |
| Phase 8 — evaluation statistics | Partly built (bb/100 and CI in `engine/stats.py`) |
| Phase 9 — ML policy layer | Not started |
| Phase 10 — mixture-model opponent typing | Designed, not started |
| Phase 11 — neural opponent embeddings | Designed, not started |
| Phase 12 — likelihood-trained value net | Designed, not started |

Nothing in the architecture below is implemented yet. [`ROADMAP.md`](ROADMAP.md) is the build plan and
carries the statistical detail.

## Engine interface

The engine speaks NDJSON over stdin/stdout — one JSON object per line, each
tagged with a `type`. Full reference in
[`poker_bot_messages.md`](poker_bot_messages.md). The messages that matter for
the design below:

- **`action_request`** — sent only to the bot on to act. Carries street, board,
  pot, `to_call`, raise bounds, `legal_actions`, and `action_history`. The bot
  replies with one `action_response`.
- **`action_taken`** — **broadcast after every action by every player.** This is
  the key affordance for opponent modelling: the bot observes the complete
  action stream for the whole table, not just its own decisions.
- **`hand_result`** — broadcast at end of hand, including showdown hole cards
  where players showed, and `null` where they mucked.

Two properties of that data shape the modelling approach in Phase 10:

1. **Actions are fully observed.** Every fold, call and raise by every opponent
   is visible, for every hand, whether or not it reaches showdown. An opponent
   model built on *action frequencies* therefore trains on a complete sample.
2. **Hole cards are not.** They appear only when a player chooses to show, and
   that choice correlates with what they're holding. Any model of "what were
   they holding given how they played" fitted on showdown data alone is fitted
   on a self-selected sample and will be biased. Phase 10 deliberately avoids
   depending on it.

## Planned architecture

```
engine ──NDJSON──> protocol layer ──> game state tracker
                                            │
                                            ├──> hand evaluator / equity
                                            │
                                            ├──> opponent model  ── posterior over
                                            │    (per seat)         opponent type
                                            │
                                            └──> decision policy ──> action_response
                                                    │
                                       baseline ◄───┴───► exploit
                                    (used when the read is weak)
```

The opponent model is a **layer**, not a replacement strategy. The baseline
policy is always present and always playable; the model supplies a posterior,
and the decision policy blends toward the exploitative best response in
proportion to how confident that posterior is. If the opponent model is disabled
or has no data, the bot reduces exactly to its baseline.

## Why the statistics are the interesting part

Classifying opponents would need labelled data — hands where someone has already
written down "this player is a nit." That data does not exist, and hand-labelling
it just encodes the labeller's priors.

The Phase 10 approach instead assumes only that the player pool is a *mixture* of
some number of unobserved types, and lets maximum likelihood recover what those
types are, how common each is, and the probability that any given opponent
belongs to each. The types are discovered, not defined. See
[`ROADMAP.md`](ROADMAP.md) for the likelihood, the estimation route, and the
reason the usual test for "how many types are there?" does not apply here.

## Open spec decisions

- **All-in convention.** Settled for the local engine: `raise` to `max_raise_to`
  (`allin` is accepted too). See the conventions section of the protocol reference.
- **Time bank policy.** `time_per_action_ms` is 5000 with a 30s bank; the
  decision policy needs a budget rule, especially once Phase 11/12 inference is in
  the hot path.
