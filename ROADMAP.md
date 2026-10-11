# JackTen Roadmap

Each phase lists what to implement and when it is done. Build in order.
With no opponent data the bot must play its baseline exactly.

---

## Foundation: bot-side protocol

Engine, simulator and hand-history logging are built. Still to do:

- [ ] NDJSON stdin/stdout loop, one object per line, flush after every write
- [ ] Dispatch: `match_start`, `hand_start`, `action_request`, `action_taken`, `street_dealt`, `hand_result`, `match_end`
- [ ] State tracker: stacks, pot, board, position, per-seat action history this hand
- [ ] Always-legal fallback action, never time out

**Done when:** always-fold and always-call bots play 500 hands and produce a parseable history.

---

## Phase 0: Combinatorics

- [x] 1,326 combos, 169 classes
- [x] `remaining_deck(*known_cards)`
- [x] Combo filter: remove combos blocked by known cards
- [x] Bot lives in `bot/` (`bot/combinatorics.py`); `main.py` import fixed

**Done when:** known cards in, exact list of live combos out. Test counts: 1,326 with no cards, 1,225 with one hole card known.

---

## Phase 1: Equity

- [x] Hand strength vs a random hand: win = 1, tie = 0.5, loss = 0
- [x] Exact enumeration from the flop on
- [x] Monte Carlo preflop, with `n` chosen from `SE = √(p(1−p)/n)`
- [x] Return equity and standard error together
- [x] Positive potential (behind now, improves) and negative potential (ahead now, outdrawn)

**Done when:** Monte Carlo matches enumeration within 2 SE, and SE shrinks as `1/√n` in a test.

---

## Phase 2: Pot odds and single-decision EV

- [ ] Equity needed to call: `call / (pot + call)`
- [ ] EV of call, bet, raise, with fold probability as a parameter
- [ ] Break-even bluff frequency
- [ ] Minimum defence frequency
- [ ] SPR
- [ ] Rake adjustment to thresholds
- [ ] `decide()`: fold / call / raise vs one opponent with one fixed assumption

**Done when:** hand-checked spots give the right action, and it beats always-call over 10k hands.

---

## Phase 3: Multiway

- [ ] N-way equity vs several ranges at once
- [ ] Equity realisation discount (position, multiway)
- [ ] Bluff fold requirement across all live opponents
- [ ] Thinner value thresholds multiway

**Done when:** Phase 2 decisions stay sensible from 2 to 6 players.

---

## Phase 4: Ranges and Bayesian updating

- [ ] Opponent range as a weight vector over 1,326 combos
- [ ] Update per action: `P(hand | action) ∝ P(action | hand) × P(hand)`
- [ ] Remove blocked combos after each update
- [ ] Equity vs a range (feeds Phases 1 to 3)
- [ ] Action model: `P(action | hand)` from strength-ordered ranges

**Done when:** hand-checked update on a small example, and equity vs range beats equity vs random head-to-head.

---

## Phase 5: Sizing and frequencies

- [ ] Bluff share of a betting range: `B / (P + 2B)` (1/3 at pot-sized bet)
- [ ] Small set of bet sizes
- [ ] Randomised mixing of bluffs and value

**Done when:** at pot-sized bets the bot bluffs about 1/3 of its betting range, measured in simulation.

---

## Phase 6: Opponent statistics

- [ ] Track VPIP, PFR, 3-bet, fold-to-c-bet, showdown frequency per opponent
- [ ] Beta-Binomial estimate per stat, shrunk to a population prior
- [ ] Confidence threshold before a read changes play
- [ ] Feed stats into Phase 4's action model

**Done when:** estimates converge to the true value of scripted opponents, with credible intervals that cover it.

---

## Phase 7: Exploitation

- [ ] EV of baseline vs EV of best response to the estimated range
- [ ] Deviate only if the gain exceeds the Phase 6 uncertainty
- [ ] Scripted opponent pool (nit, calling station, maniac, TAG, LAG)

**Done when:** it beats the Phase 2 to 5 baseline vs the pool by a margin outside its confidence interval.

---

## Phase 8: Evaluation

Build this alongside Phase 1.

- [ ] bb/100 with `SE = SD / √(100-hand blocks)`
- [ ] Verify the SD (about 100 bb/100) on your own bot
- [ ] 95% CI on every comparison
- [ ] Duplicate deals and common random numbers
- [ ] All-in EV control variate
- [ ] Frozen benchmark seeds, never tune on them

**Done when:** a comparison reports a win rate and CI, and duplicate deals visibly shrink the CI.

---

## Phase 9: ML policy

- [ ] Features: equity, pot odds, SPR, position, live players, opponent stats
- [ ] Train/test split
- [ ] Calibration check on predicted equities
- [ ] Policy trained on the features

**Done when:** it matches or beats the Phase 7 baseline, with CIs saying which.

---

# Advanced

## Phase 10: Mixture-model opponent typing

Opponents are a mixture of `K` unobserved types. Fit from action counts only.

- [ ] Contexts: street, position, facing (unopened / bet / raise), pot-odds bucket
- [ ] Actions: fold, call/check, raise
- [ ] Count matrix `n_jca` per opponent
- [ ] Likelihood: `L_j = Σ_k π_k ∏_c ∏_a θ_kca^n_jca`
- [ ] EM: E-step responsibilities `r_jk`, M-step weighted frequencies
- [ ] Dirichlet smoothing
- [ ] Multiple random restarts, keep best likelihood
- [ ] Fix label switching: order types by aggression
- [ ] Newton-Raphson cross-check
- [ ] Standard errors by outer product of gradients
- [ ] Choose `K`: parametric bootstrap LRT (chi-squared is invalid: boundary null, unidentified parameters), plus BIC and ICL
- [ ] Online posterior: add `log θ_kca` per observed action, normalise
- [ ] Blend baseline toward exploit by posterior confidence
- [ ] Recovery test: plant `K` scripted types, fit blind, check profiles and weights

**Done when:** planted types are recovered, bootstrap picks the right `K`, and the exploit layer beats the Phase 7 baseline outside its CI.

---

## Phase 11: Neural opponent embeddings

- [ ] GRU or small transformer over an opponent's action history
- [ ] Continuous latent `z_j`, trained to predict next action
- [ ] Compare the embedding space to Phase 10 types
- [ ] Inference inside the 5s action budget

**Done when:** next-action prediction beats Phase 10 out of sample.

---

## Phase 12: Likelihood-trained value network

- [ ] Network outputs mean `μ(x)` and variance `σ²(x)`
- [ ] Train on Gaussian negative log-likelihood, not MSE
- [ ] Fall back toward baseline when variance is high
- [ ] Calibration: 90% intervals contain the outcome 90% of the time
- [ ] Stretch: Laplace approximation over the weights

**Done when:** intervals are calibrated within a few points of nominal, and uncertainty-aware play beats the point-estimate version.
