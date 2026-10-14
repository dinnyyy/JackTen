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
| `comparisons.csv` | pair of bots | always (empty with one bot) |
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
| `bb_per_100_ci95` | Half-width of the 95% confidence interval on `bb_per_100`, built from 100-hand blocks (see Evaluation below). |
| `bb_per_100_ev` | `bb_per_100` with every all-in runout replaced by its expected value. Same long-run mean, less noise. |
| `ev_ci95` | 95% half-width on `bb_per_100_ev`. |
| `sd_100` | Standard deviation of one full 100-hand block's bb/100. Expect roughly 100 for a 6-max bot at constant depth. |
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

## Evaluation (Phase 8)

How to read `bb_per_100` and compare bots.

- **Blocks.** A block is 100 consecutive hands of one match. The CI is `1.96 x SD(block bb/100) / sqrt(blocks)`. Blocks cut short by a bust-out count in proportion to their length (ratio estimator).
- **All-in EV.** When every bet is called and cards are still to come, the engine averages each player's winnings over all runouts (exact for one or two cards to come, 1,000 samples preflop) and replaces the actual result with that. `*_ev` columns use it. The actual-minus-expected luck has mean zero, so nothing is biased.
- **`--cash`.** Stacks reset to the starting stack after every hand. Hands are independent, nobody busts, and bb/100 is at a constant depth. Placement, win and bust columns mean nothing in this mode. Without it, a match ends when one player has everything, matches run short, and bots that bust more play fewer hands.
- **`--duplicate`.** Each deal seed is played several times with the bots moved between seats: two labels with equal seat counts swap (2 plays); anything else rotates one seat per play. Cards are seeded per (seed, hand number), so every play sees the same hole cards by seat. The CI unit becomes the (deal, block) pair with the plays pooled. `matches` is rounded up to a whole number of deals.
- **`--bench`.** Frozen seeds from 1,000,000,000, implying `--duplicate --cash`. Ordinary runs refuse that seed range and never draw it. Each benchmark run is appended to `data/bench_log.jsonl`. Tune on dev seeds, then benchmark once.

### comparisons.csv

One row per pair of bots. `diff` is `a` minus `b` in bb/100.

| Column | Meaning |
|---|---|
| `a`, `b` | The two bots. |
| `blocks` | Units the CI is built from (blocks, or (deal, block) pairs with `--duplicate`). |
| `diff`, `ci95`, `z`, `significant` | Realised difference, its 95% half-width, z score, and whether the difference is outside the CI. |
| `diff_ev`, `ci95_ev`, `z_ev`, `significant_ev` | The same with all-in runouts replaced by EV. |
| `ci95_nodup`, `ci95_nodup_ev` | Only with `--duplicate`: the half-width the same hands would have given without deal pairing. Compare with `ci95` to see what duplicating bought. |
