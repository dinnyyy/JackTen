# Simulation outputs

Every simulation run writes to `data/sims/<run id>/`. That directory is gitignored. You can download any file, or all of them as a zip, from the Simulations page in `python play.py`. The CLI (`python simulate.py`) writes the same files.

Conventions:
- **Seats** are shuffled every match, so `seat` is only meaningful within a match. Use `bot` to group.
- **Chips** are integers. `*_bb` columns are divided by that hand's big blind.
- **Cards** are space-separated two-char strings (`As Kd`). Lists inside one cell are `|`-separated.
- **Ground truth:** `hole_cards` holds every player's real cards, including hands that were folded or mucked. Bots never see this. Use it to validate opponent models. Don't train a model on it if that model has to work from observable data only. For that, use `went_to_showdown` and `showed`.
- **Row order** in `actions`, `hands`, `pots` and `matches` is grouped by worker process. Sort by `match`, `hand` (and `action_idx`) if order matters.

| File | One row per | Written when |
|---|---|---|
| `bot_summary.csv` | bot | always |
| `matches.csv` | seat per match | always |
| `cumulative_winnings.csv` | sampled point in the run | always |
| `errors.csv` | bot error | always (may be empty) |
| `hands.csv` | player per hand | detailed CSVs on |
| `actions.csv` | decision | detailed CSVs on |
| `pots.csv` | main or side pot | detailed CSVs on |
| `histories/match_XXXX.ndjson` | protocol message | NDJSON histories on |

## bot_summary.csv

| Column | Meaning |
|---|---|
| `bot` | Label from the lineup. Bots with the same label are pooled. |
| `hands` | Hands dealt to this bot. |
| `matches` | Seats this bot occupied across all matches. |
| `net_chips` | Total chips won or lost. |
| `bb_per_100` | Big blinds won per 100 hands. |
| `bb_per_100_ci95` | Half-width of the 95% confidence interval on `bb_per_100`. It treats hands as independent, so read it as a guide, not gospel. |
| `avg_place` | Mean finishing position. 1 = won the match. |
| `win_rate` | % of matches finished 1st. |
| `bust_rate` | % of matches that ended with zero chips. |
| `avg_final_stack` | Mean chips at match end. |
| `vpip` | % of hands voluntarily putting chips in preflop. Blinds don't count. |
| `pfr` | % of hands raising preflop. |
| `threebet` | % re-raising when facing exactly one preflop raise. |
| `af` | Postflop aggression factor: (bets + raises) / calls. Empty if there were no calls. |
| `wtsd` | % of flops seen that reached showdown. |
| `wsd` | % of showdowns that won chips. |
| `bot_errors` | Timeouts, crashes and invalid responses. |

## matches.csv

| Column | Meaning |
|---|---|
| `match`, `seed` | Match index, and the seed that reproduces it. |
| `seat`, `bot` | Where the bot sat. |
| `final_stack` | Chips at the end of the match. |
| `net_chips` | `final_stack` minus the starting stack. |
| `place` | Finishing position. Players who bust on the same hand are ordered by their starting stack for that hand. |
| `busted` | 1 if the bot finished with zero chips. |
| `hands_played` | Hands in the match: the max hands setting, or fewer if one player won everything. |

## hands.csv

| Column | Meaning |
|---|---|
| `match`, `hand` | Identifiers. `hand` is 0-based. |
| `seat`, `bot`, `position` | Position is one of BTN, SB, BB, UTG, UTG+n, LJ, HJ, CO. Heads-up: BTN (which posts the SB) and BB. |
| `num_players`, `button_seat` | Table state for the hand. |
| `small_blind`, `big_blind`, `ante` | Blind level for the hand. |
| `hole_cards`, `board` | Ground truth, and the final board (may have fewer than 5 cards). |
| `start_stack`, `end_stack` | Stack before antes and blinds, and after the pot is awarded. |
| `net_chips`, `net_bb` | Result of the hand. Sums to 0 across a hand. |
| `vpip`, `pfr`, `saw_flop` | 0/1 HUD flags. |
| `folded_on` | Street the player folded on. Empty if they never folded. |
| `went_to_showdown` | 1 if the hand reached showdown and this player was still in it. |
| `showed` | 1 if the cards were tabled. Losing hands are mucked unless someone was all-in. |
| `hand_rank` | For shown hands, e.g. `two pair, kings and sevens`. |
| `won_chips` | Chips won from pots. Excludes your own uncalled bet. |
| `uncalled_returned` | Your own uncalled bet handed back. |

## actions.csv

One row per decision. It captures exactly what the bot saw and did, which makes it the natural training table.

| Column | Meaning |
|---|---|
| `match`, `hand`, `action_idx` | `action_idx` counts decisions within the hand. |
| `street`, `seat`, `bot`, `position` | Who acted, and when. |
| `hole_cards`, `board` | The actor's cards, and the board at decision time. |
| `pot_before` | Total pot, including current-street bets, before acting. |
| `to_call` | Chips needed to call. Capped at the stack. |
| `stack_before` | Chips behind before acting. |
| `street_bet_before` | Chips already put in this street. |
| `min_raise_to`, `max_raise_to` | Legal raise range, as a street total. Both are 0 if raising wasn't legal. |
| `legal_actions` | E.g. `fold\|call\|raise`. |
| `requested_action`, `requested_amount` | What the bot actually sent. |
| `action`, `amount` | What the engine applied. `amount` is the street total, for call and raise only. |
| `chips_added` | Chips moved into the pot by this action. |
| `all_in` | 1 if the action put the player all-in. |
| `corrected` | Why the engine changed the request, if it did, e.g. `check facing a bet -> fold`. |
| `pot_after` | Pot after the action. |
| `elapsed_ms` | Bot thinking time. |

## pots.csv

| Column | Meaning |
|---|---|
| `match`, `hand`, `pot_index` | 0 = main pot, 1+ = side pots. |
| `amount` | Chips in this pot. |
| `eligible_seats`, `eligible_bots` | Live players who could win it. |
| `winner_seats`, `winner_bots` | Who won it. |
| `split` | 1 if more than one winner. |
| `shares` | `bot:chips` per winner. Odd chips go to the first winner left of the button. |

## cumulative_winnings.csv

`hand_index`, then one `<bot>_bb` column per bot. It's the running net big blinds across the whole run, downsampled to about 400 points. This is the curve on the Simulations page.

## errors.csv

`match`, `hand`, `seat`, `bot`, `error`.
