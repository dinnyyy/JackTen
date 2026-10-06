# Poker Bot Protocol — Message Reference

NDJSON over stdin/stdout. Every message has a `"type"` field. `amount` = total size you're betting/raising **to** for the street, not the incremental chips added. Money = integers only.

## Engine → Bot

**`match_start`** (once, at start)
```json
{
  "type": "match_start",
  "your_seat": 2,
  "num_players": 6,
  "starting_stack": 20000,
  "blind_schedule": [
    {"hand_start": 0, "small_blind": 50, "big_blind": 100, "ante": 0}
  ],
  "num_hands": 500,
  "time_per_action_ms": 5000,
  "time_bank_ms": 30000,
  "bot_names": ["alice_bot", "bob_bot", "carol_bot"]
}
```

**`hand_start`** (every hand)
```json
{
  "type": "hand_start",
  "hand_number": 17,
  "button_seat": 3,
  "small_blind": 100,
  "big_blind": 200,
  "ante": 0,
  "stacks": {"0": 19800, "1": 20200, "2": 20000},
  "your_hole_cards": ["As", "Kd"]
}
```

**`action_request`** (only to the bot on to act)
```json
{
  "type": "action_request",
  "hand_number": 17,
  "street": "flop",
  "board": ["7c", "2d", "Jh"],
  "pot": 1400,
  "to_call": 200,
  "min_raise_to": 600,
  "max_raise_to": 19500,
  "your_stack": 19100,
  "legal_actions": ["fold", "call", "raise"],
  "action_history": [
    {"seat": 3, "action": "raise", "amount": 600, "street": "preflop"}
  ],
  "time_remaining_ms": 28000
}
```
`legal_actions` gives `"check"` instead of `"call"` when `to_call == 0`; omits `"raise"` when the bot is covered.

**`action_taken`** (broadcast, informational, no reply expected)
```json
{"type": "action_taken", "seat": 3, "action": "raise", "amount": 600, "street": "preflop", "pot": 1400}
```

**`street_dealt`** (broadcast)
```json
{"type": "street_dealt", "street": "turn", "board": ["7c", "2d", "Jh", "4s"], "pot": 2600}
```

**`hand_result`** (broadcast, end of hand)
```json
{
  "type": "hand_result",
  "hand_number": 17,
  "board": ["7c", "2d", "Jh", "4s", "9c"],
  "showdown": [
    {"seat": 3, "hole_cards": ["Kh", "Kc"], "hand_rank": "three of a kind, kings"},
    {"seat": 4, "hole_cards": null}
  ],
  "winners": [{"seat": 3, "amount": 5200}],
  "stacks": {"0": 19800, "1": 20200, "2": 20000}
}
```
`hole_cards: null` for anyone who didn't show. `winners` already reflects side-pot splits.

**`match_end`** (once, at end)
```json
{"type": "match_end", "final_stacks": {"0": 15200, "1": 0, "2": 41000}, "rankings": [2, 0, 1]}
```

## Bot → Engine

**`action_response`** (only in reply to `action_request`)
```json
{"type": "action_response", "action": "raise", "amount": 600}
```
`amount` required for `bet`/`raise`; omitted for `fold`/`check`/`call`.

## Local engine conventions (`engine/`)

Settled decisions and additive fields. Bots may ignore any extra field.

**All-in:** send `raise` with `amount == max_raise_to`. `"action": "allin"` is also accepted. Calling for less than `to_call` is automatic when your stack is short.

**Invalid responses** never crash a hand:
- `check` facing a bet becomes `fold`.
- `fold` when checking is free becomes `check`.
- `raise` when raising isn't legal becomes `call` or `check`.
- A raise outside `[min_raise_to, max_raise_to]` is clamped.
- Timeouts, crashes and garbage become check-or-fold.

`action_taken` carries `corrected` when this happens.

**Extra fields:**
- `hand_start.posts` — antes and blinds actually posted: `[{"seat", "type": "ante"|"small_blind"|"big_blind", "amount"}]`. `hand_start.stacks` are *before* posting.
- `action_request.your_bet` — chips you've already put in this street.
- `min_raise_to`/`max_raise_to` are `0` when `raise` isn't legal.
- `action_taken.all_in` is a bool. `amount` appears on `call` and `raise` as the street total.
- `hand_result.pots` — `[{"amount", "eligible", "winners", "shares"}]`, main pot first. `hand_result.uncalled_returned` is `{seat: chips}`. `winners[].amount` excludes your own returned uncalled bet.

**Betting rules (TDA):**
- **Heads-up:** the button posts the SB, acts first preflop and last postflop.
- **Short big blind:** a BB all-in for less doesn't lower the call amount.
- **Min raise:** the size of the last *full* bet or raise on the street, never less than the BB.
- **Short all-ins:** an all-in below a full raise doesn't reopen betting for players who already acted. It does reopen once several short all-ins add up to a full raise.
- **No pointless raises:** you can't raise when everyone else is all-in.
- **Antes** are dead money.
- **Pots:** each side pot is awarded separately. Uncalled bets are returned.
- **Odd chips** go to the first winner left of the button.
- **Showdown order:** the last river aggressor shows first, otherwise the first player left of the button. Later players muck hands that can't win or tie a pot they're in. If anyone is all-in, every hand is tabled.

**Table:**
- **Moving button:** it advances to the next seat with chips.
- **Same-hand busts:** the player who started the hand with fewer chips finishes lower.
