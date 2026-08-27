# JackTen

A No-Limit Texas Hold'em bot for the NDJSON tournament engine, built around a
maximum-likelihood opponent model.

Most bots play the same way against everyone at the table. JackTen's design goal
is the opposite: hold a live, probabilistic read on each opponent and deviate
from a solid baseline strategy only as far as the accumulated evidence actually
justifies. With no hands observed, it plays its baseline. As reads sharpen, it
exploits.

## Status

Early. The engine interface is specified; the bot is not yet built.

| Component | State |
|---|---|
| Engine protocol spec | Documented — [`poker_bot_messages.md`](poker_bot_messages.md) |
| Phase 0 — protocol I/O + harness | Not started |
| Phase 1 — baseline strategy | Not started |
| Phase 2 — mixture-model opponent typing | Designed, not started |
| Phase 3 — neural opponent embeddings | Designed, not started |
| Phase 4 — likelihood-trained value net | Designed, not started |

Nothing below is implemented. [`ROADMAP.md`](ROADMAP.md) is the build plan and
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

Two properties of that data shape the modelling approach in Phase 2:

1. **Actions are fully observed.** Every fold, call and raise by every opponent
   is visible, for every hand, whether or not it reaches showdown. An opponent
   model built on *action frequencies* therefore trains on a complete sample.
2. **Hole cards are not.** They appear only when a player chooses to show, and
   that choice correlates with what they're holding. Any model of "what were
   they holding given how they played" fitted on showdown data alone is fitted
   on a self-selected sample and will be biased. Phase 2 deliberately avoids
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

The Phase 2 approach instead assumes only that the player pool is a *mixture* of
some number of unobserved types, and lets maximum likelihood recover what those
types are, how common each is, and the probability that any given opponent
belongs to each. The types are discovered, not defined. See
[`ROADMAP.md`](ROADMAP.md) for the likelihood, the estimation route, and the
reason the usual test for "how many types are there?" does not apply here.

## Open spec decisions

Carried over from the protocol reference, still to settle:

- **All-in convention.** Either its own action type, or a `raise` with
  `amount == your_stack`. Pick one and document it.
- **Time bank policy.** `time_per_action_ms` is 5000 with a 30s bank; the
  decision policy needs a budget rule, especially once Phase 3/4 inference is in
  the hot path.
