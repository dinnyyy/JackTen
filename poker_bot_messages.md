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
`amount` required for `bet`/`raise`; omitted for `fold`/`check`/`call`. All-in is either its own action type or a `raise` with `amount == your_stack` — pick one convention and document it.
