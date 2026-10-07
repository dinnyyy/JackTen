# JackTen v1: Build, Evaluation and Showcase Plan

**Author:** Joshua Dinn
**Scope:** v1 = README Phases 0 to 2 (protocol and harness, baseline strategy, mixture-model opponent typing). Phases 3 and 4 come after v1 ships.
**Target:** v1 shipped by **31 January 2027**, before 2028 graduate applications at quant firms open (around February to May 2027).
**Last updated:** 6 October 2026

---

## 0. Instructions for Claude Code (read first)

Read these in order before writing any code:

1. `README.md`: what JackTen is and the design principles.
2. `poker_bot_messages.md`: the engine protocol. It is authoritative on message formats.
3. `ROADMAP.md`: the statistical detail. **This plan was written without sight of ROADMAP.md.** Where the two disagree on statistics or phase content, stop and ask Josh which is right, then record the answer in `DECISIONS.md`.
4. This file: scope, decisions, evaluation and deliverables for v1.

**Roles.** Josh owns every design decision, derives the statistics by hand, interprets results and writes the findings. Claude writes most of the code, tests, tooling and plots, and proposes options. Claude does not make a design decision on Josh's behalf.

**Working rules**

1. **Stop and ask** before any choice that changes how the bot plays or how results are measured: contexts, archetype definitions, priors, blending rule, benchmark size, metrics. Offer options with trade-offs, wait for Josh, record the outcome in `DECISIONS.md`.
2. **Baseline guarantee.** With the opponent model disabled or holding no data, JackTen must produce exactly the baseline's decision. This is a hard test, not a goal (Section 9).
3. **Never tune on benchmark seeds.** Exploit settings, thresholds and model choices are tuned on dev seeds only. Benchmark seeds are frozen per version.
4. **Never send an illegal action and never time out.** Every decision path falls back to a legal, safe action.
5. **Every statistic has a hand-checkable test.** EM updates, posteriors, win-rate standard errors and variance reduction each ship with a small example Josh can verify by hand.
6. **Write for understanding.** Clear names, short functions, docstrings explaining the statistics in plain English. Josh must be able to explain every line in a quant interview.
7. Prose in the README, write-up and posts uses Australian spelling and no em dashes.
8. JackTen is for the tournament engine and research only. It is never connected to a real-money poker site.

---

## 1. Plain-English summary

Most poker bots play the same way against everyone. JackTen holds a live, probabilistic read on each opponent and only deviates from a solid baseline as far as the evidence justifies. With no hands observed it plays its baseline; as its read sharpens, it exploits.

The interesting part is the statistics. Nobody labels opponents as "nit" or "calling station", so JackTen assumes the player pool is a mixture of unknown types and lets maximum likelihood discover what those types are, how common each is, and how likely each opponent is to belong to each. It deliberately avoids learning from shown-down hole cards, because players choose when to show, which makes that data a biased sample.

v1 proves three things with numbers:

1. **The model works.** On simulated opponents whose true types I set, it recovers those types.
2. **The bot improves.** Its win rate rises as it watches an opponent for more hands.
3. **The statistics earned the improvement.** It beats the same bot without the model, and a bot using simple stat thresholds, with confidence intervals that exclude zero.

## 2. Technical summary

Opponent actions are summarised as counts over a small set of decision contexts (Section 6.1). Each opponent's count vector is modelled as a draw from a finite mixture of K latent types, each type a product of categorical distributions over actions within each context (a latent class model). Parameters are estimated by EM with Dirichlet smoothing; K is chosen by parametric bootstrap likelihood-ratio testing and BIC, since the standard chi-squared LRT for the number of mixture components is invalid (the null lies on the parameter-space boundary and some parameters are unidentified under it).

During play, each opponent carries a posterior over types, updated after every observed action using the fitted type parameters. The same posterior drives Bayesian range updates within each hand: each type's action frequencies are turned into strength-ordered ranges, so equity is computed against an opponent-specific range rather than a fixed default. The decision policy moves a set of exploit settings from baseline toward the posterior-weighted type-specific best responses, by an amount that grows with posterior concentration and sample size, and is exactly zero with no data.

Every quantity is expressed in big blinds and effective stack depth, so one bot plays whatever blinds, stacks and table size the engine sends. Performance is measured in big blinds per 100 hands (bb/100) on a frozen benchmark, using duplicate deals, common random numbers and an all-in EV control variate to cut variance, with 95% confidence intervals on every comparison.

---

## 3. v1 scope

**In:** protocol layer, game state tracker, settings-aware design (any blinds, stacks and table size), hand evaluator and equity, hand-history logging, local dealer and harness, baseline strategy, scripted opponent pool, benchmark suite across a grid of formats, mixture model (offline fit and online posterior), Bayesian range updates, exploit layer with blending, evaluation, showcase artefacts.

**Out (after v1):** Phase 3 neural opponent embeddings, Phase 4 likelihood-trained value net, a solver-grade baseline, ICM-aware tournament decisions, multi-table tournament strategy beyond what the engine requires.

### How the original roadmap maps onto this plan

Nothing from the original roadmap is dropped. It is reorganised into layers:

| Original roadmap layer | Where it lives in v1 |
| --- | --- |
| Hand evaluation and equity | Phase 0 (`cards/`), written from scratch and verified against brute force |
| EV, pot odds, minimum defence frequency | Phase 1 baseline strategy (Section 7.2) |
| Opponent stats (VPIP, PFR, 3-bet%) | Phase 2 contexts (Section 6.1); also the raw-stat comparison bot (Section 8.1) |
| Bayesian range updates | Phase 2b, driven by the type posterior (Section 6.6) |
| Deep learning on action sequences (LSTM, transformer) | Phase 3 after v1, feeding the same Bayesian layer (Section 15) |

The new layer in the middle is the mixture model, which discovers opponent types instead of relying on hand-picked stat thresholds.

---

## 4. Decisions Josh must make

Fill in the last column. Defaults are starting points, not answers. Each choice also goes into `DECISIONS.md` with a one-line reason. Decisions marked **Before Phase 0** block the start; the rest can wait until their phase.

| ID | When | Decision | Options | Suggested default | Josh's choice |
| --- | --- | --- | --- | --- | --- |
| D1 | Before Phase 0 | Language | Python; C++ for hot paths | Python throughout for v1; profile before optimising | |
| D2 | Before Phase 0 | Local engine | Official engine binary if available; or a local dealer that speaks the same NDJSON protocol | Official engine if it runs locally; otherwise a local dealer, conformance-tested against `poker_bot_messages.md` | |
| D3 | Before Phase 0 | Primary format (for tuning) | Heads-up; 6-max; whatever the tournament uses | Match the tournament; other formats are tested via the grid (D21) | |
| D4 | Before Phase 0 | All-in convention (README open decision) | Own action type; or raise with amount equal to stack | Whatever the engine accepts; document it in the spec | |
| D5 | Before Phase 0 | Time budget rule (README open decision) | Fixed per-action cap; cap plus bank draw on hard spots | 1,500 ms soft cap per action, bank used only above it, hard fallback at 4,000 ms | |
| D6 | Phase 0 | Hand evaluator | Own implementation; or existing library | Own implementation, so "from the math up" holds; verified against brute force and a library in tests | |
| D7 | Phase 1 | Baseline design | Preflop ranges by position plus postflop equity and pot-odds rules; or a simplified solver | Rules-based: position-aware preflop ranges, postflop equity vs a default range, pot odds, minimum defence frequency | |
| D8 | Phase 1 | Opponent archetypes and their parameters | See Section 7.1 | Five archetypes plus two hold-outs, with within-type variation | |
| D9 | Phase 1 | Benchmark size | Hands per comparison | Set after the pilot measures the standard deviation (Section 8.2) | |
| D10 | Phase 1 | Variance reduction | Duplicate; common random numbers; all-in EV; AIVAT | Duplicate plus common random numbers plus all-in EV control variate; AIVAT is a stretch goal | |
| D11 | Phase 2 | Decision contexts | See Section 6.1 | The 10 contexts listed | |
| D12 | Phase 2 | Action categories per context | Fold / passive / aggressive; or with raise-size buckets | Three categories; size buckets later | |
| D13 | Phase 2 | Dirichlet prior strength | alpha per cell | alpha = 1 (add-one smoothing) | |
| D14 | Phase 2 | Range of K to consider | 1 to 8 | 1 to 8 | |
| D15 | Phase 2 | Choosing K | Bootstrap LRT; BIC; ICL | Report all three; use bootstrap LRT as primary | |
| D16 | Phase 2 | Exploit settings per type | Which levers can move | Steal width, 3-bet frequency, c-bet frequency, bluff frequency, value threshold, call-down threshold | |
| D17 | Phase 2 | Blending rule | See Section 6.5 | lambda = [n / (n + kappa)] x [1 - H(p) / log K], kappa = 50 | |
| D18 | Phase 2 | Non-stationary opponents | No discounting; exponential discount on old actions | Exponential discount with half-life of 200 actions, tested both ways | |
| D19 | Phase 2 | Significance level | alpha | 0.05, two-sided, 95% CIs | |
| D20 | Before Phase 0 | Definition of "v1 done" | See Section 12 | The Section 12 checklist | |
| D21 | Phase 1 | Format grid for the benchmark | Table sizes and stack depths to test | Primary format, plus heads-up and 6-max at 20, 50 and 100 big blinds | |
| D22 | Phase 1 | Stack-depth handling | One strategy for all depths; or depth buckets | Baseline rules by depth bucket (under 25, 25 to 60, over 60 bb); contexts split by the same buckets | |
| D23 | Phase 2 | Range representation | 169 preflop hand classes; full combos with card removal | 169 classes preflop, combos with card removal postflop | |
| D24 | Phase 2 | Turning frequencies into ranges | Strength-ordered ranges; with a bluff fraction | Strength-ordered, plus a per-type bluff fraction drawn from the weakest hands | |

---

## 5. Phase 0: protocol, state and harness

**Goal:** a bot that always acts legally and on time, and a harness that can run millions of hands offline with full logs.

**Components**

- `protocol/`: NDJSON read and write, message schemas, validation against `poker_bot_messages.md`.
- `state/`: game state tracker built from `action_request`, `action_taken` and `hand_result`; reconstructs every player's action sequence per hand.
- `settings/`: reads blinds, stacks, seat count and match length from engine messages and converts every amount to big blinds. No format value is hard-coded anywhere.
- `cards/`: hand evaluator (D6) and Monte Carlo equity against a range.
- `history/`: append-only hand-history store (JSONL or Parquet) with every action by every seat, board, pot, stacks, and showdown cards where shown (`null` otherwise, never imputed).
- `harness/`: local dealer or engine wrapper (D2), seeded deck control, a runner for N hands across a table of bots, and per-hand result logging.
- `bots/`: `random_bot` and `always_call_bot` as the first opponents.

**Done when**

- 1,000,000 hands run with zero illegal actions and zero timeouts.
- The protocol layer passes a conformance test for every message type in the spec.
- The same seed reproduces the same deals and results exactly.
- The evaluator agrees with brute force on 100,000 random hands.
- The same bot runs unchanged on every format in the grid (D21).

---

## 6. The statistical core (Phases 1 and 2)

### 6.1 Decision contexts

Actions are only comparable within the same kind of situation, so each opponent decision is assigned to one of C contexts. Suggested set (D11):

| # | Street | Situation | Actions |
| --- | --- | --- | --- |
| 1 | Preflop | Unopened pot | fold / limp / raise |
| 2 | Preflop | Facing an open raise | fold / call / 3-bet |
| 3 | Preflop | Facing a 3-bet | fold / call / 4-bet |
| 4 | Flop | Preflop aggressor, checked to | check / bet |
| 5 | Flop | Facing a bet | fold / call / raise |
| 6 | Flop | Not aggressor, checked to | check / bet |
| 7 | Turn | First to act or checked to | check / bet |
| 8 | Turn | Facing a bet | fold / call / raise |
| 9 | River | First to act or checked to | check / bet |
| 10 | River | Facing a bet | fold / call / raise |

**Plain English:** instead of one vague "how aggressive is this player" number, JackTen tracks how they act in ten specific spots.

When the format grid includes several stack depths, each context is also split by effective stack bucket (D22), because the same player acts differently at 20 and at 100 big blinds.

### 6.2 The model

For opponent i, let n_icj be the number of times they took action j in context c. Each opponent belongs to an unobserved type z_i in {1, ..., K}, with P(z_i = k) = pi_k. Given the type, actions in context c follow a categorical distribution with probabilities theta_kcj.

```
L(pi, theta) = prod_i  sum_k  pi_k  prod_c prod_j  theta_kcj ^ n_icj
```

**Key assumption:** given the type and the context, each action is an independent draw. Cards are dealt independently of type, so hand strength averages out within each type's action probabilities. This is a simplification: real players also react to board texture and to us. It is stated as a limitation and partly tested by the hold-out archetypes (Section 7.1).

**Why not use shown-down cards:** players choose whether to show, and that choice depends on what they hold. A model fitted on shown hands is fitted on a self-selected sample and is biased. v1 uses action frequencies only, which are observed for every hand.

### 6.3 Estimation by EM (Josh derives by hand first)

**E-step:** posterior type probabilities for each opponent.

```
tau_ik = pi_k f_k(n_i) / sum_m pi_m f_m(n_i),   f_k(n_i) = prod_c prod_j theta_kcj ^ n_icj
```

Computed in log space with log-sum-exp to avoid underflow.

**M-step:** closed-form updates, with Dirichlet smoothing alpha (D13).

```
pi_k     = (1/N) sum_i tau_ik
theta_kcj = [ sum_i tau_ik n_icj + alpha ] / [ sum_i tau_ik n_ic. + J_c alpha ]
```

**Practicalities:** 20 random starts, keep the best log-likelihood; stop when the log-likelihood gain is below 1e-8; sort types by a fixed rule (for example, preflop raise rate) to handle label switching.

**Plain English:** guess what the types look like, work out how likely each player is to be each type, re-estimate the types from those weighted guesses, and repeat until nothing changes.

### 6.4 How many types? (the non-standard test)

Testing K types against K + 1 with the usual likelihood-ratio test fails: under the null, the extra type's weight sits on the boundary (pi = 0) and its action probabilities are not identified, so Wilks' theorem does not hold and the statistic is not chi-squared.

Use a **parametric bootstrap LRT**: fit K and K + 1 to the data; simulate B = 200 datasets from the fitted K-type model; refit both models to each; the p-value is the share of simulated LR statistics at least as large as the observed one. Report BIC and ICL alongside.

**Plain English:** the textbook test for "is there one more type?" gives wrong answers here, so I simulate what the test statistic looks like when there really is no extra type, and compare.

### 6.5 Online posterior and the exploit blend

During play, type parameters are fixed from the offline fit. For each opponent, keep log-posterior weights and add log theta_kcj every time they take action j in context c. This is cheap enough for any time budget.

Each type k has a set of exploit settings s_k (D16), tuned on dev seeds as the best response to that type. The baseline has settings s_0. JackTen plays

```
s = s_0 + lambda * sum_k p_k (s_k - s_0)
lambda = [ n / (n + kappa) ] * [ 1 - H(p) / log K ]
```

where p is the posterior, H(p) its entropy and n the number of actions observed (D17). With no data, n = 0 so lambda = 0 and s = s_0: exactly the baseline.

**Plain English:** JackTen only leans toward exploiting a player as far as it is both confident about their type and has seen enough hands to back that up.

### 6.6 Bayesian range updates

Within a hand, JackTen narrows each opponent's range as they act, and the type posterior makes that narrowing opponent-specific.

**From frequencies to ranges (D24).** Hands are ordered by strength in each spot. A type that raises 9% of the time in a context is assumed to raise its strongest 9%, plus a bluff fraction b_k taken from its weakest hands. This gives P(action | hand, context, type) without needing any shown-down cards.

**The update.** With the type posterior p taken from previous hands and held fixed within the current hand:

```
P(h | actions so far) is proportional to  P(h | board, our cards) * sum_k p_k * prod_t P(a_t | h, c_t, k)
```

Equity is then computed against this range instead of a fixed default range.

**Plain English:** if JackTen thinks a player is probably a nit and they 3-bet, it puts them on a much stronger hand than if it thinks they are a maniac.

**Assumptions to test:** strength-ordered ranges are an approximation, and holding p fixed within a hand ignores what the current hand reveals about type. Both are checked against the scripted archetypes, whose true ranges are known. A joint update is a later refinement.

### 6.7 Statistics Josh derives before Claude implements

| Item | What to derive | Test that checks it |
| --- | --- | --- |
| E-step and M-step | The update formulas in 6.3 from the expected complete-data log-likelihood | `test_em_toy.py`: two types, two contexts, hand-computed one-step update |
| EM monotonicity | Why the log-likelihood never decreases | `test_em_monotone.py` |
| Why Wilks fails | The boundary and identification argument | Written note in `docs/` |
| Bootstrap LRT | The procedure and its p-value | `test_bootstrap_lrt.py`: correct size on simulated K-type data |
| Online posterior | The sequential update | `test_posterior.py`: matches batch posterior on the same data |
| Range update | The posterior over hands given actions and types | `test_range_update.py`: matches full enumeration on a small example |
| Win-rate SE | SE of bb/100 and of a paired difference | `test_winrate_se.py` |
| Control variate | Optimal coefficient beta = Cov(Y, X) / Var(X) and variance reduction 1 - rho^2 | `test_control_variate.py` |

---

## 7. Phase 1: baseline, opponent pool and benchmark

### 7.1 Opponent pool (known truth)

Scripted bots whose tendencies Josh sets. Each archetype defines target action probabilities per context, and each individual bot draws its own parameters around the archetype's values (D8), so the mixture model faces realistic within-type variation.

| Archetype | Rough VPIP / PFR (%) | Character |
| --- | --- | --- |
| Nit | 12 / 9 | Very tight, folds to pressure |
| TAG | 22 / 18 | Solid tight-aggressive |
| LAG | 32 / 26 | Loose-aggressive, bluffs often |
| Calling station | 45 / 8 | Loose-passive, rarely folds |
| Maniac | 60 / 45 | Raises constantly |
| **Hold-out: trapper** | 20 / 10 | Passive early, check-raises strong hands; not in the training pool |
| **Hold-out: style switcher** | TAG then LAG | Changes style after a set number of hands; tests non-stationarity |

Hold-outs are never used to fit the model or tune exploits. They test what happens when reality is not in the model.

### 7.2 Baseline

Rules-based (D7): position-aware preflop ranges, postflop decisions from equity against a default range, pot odds, and minimum defence frequency so it cannot be folded out of every pot. Simple, documented and stable. It is the reference every improvement is measured against.

Every rule is a function of position, number of players and effective stack in big blinds (D22), never a fixed chip amount, so the same baseline plays any format the engine sends. Once Phase 2b is in, equity is computed against type-weighted ranges (Section 6.6) instead of the default.

**Done when** the baseline beats `random_bot`, `always_call_bot` and the calling-station archetype with 95% CIs excluding zero.

### 7.3 Benchmark suite

The JackTen Benchmark is a frozen, versioned test:

- Fixed table compositions of archetype bots (and hold-outs in a separate track).
- Frozen evaluation seeds, separate from dev seeds.
- Format grid (D21): the primary format is the headline track; the other formats are reported as separate tracks.
- Duplicate format: every deal is replayed with seats rotated, so each bot gets the same cards in the same spots.
- Output: bb/100 against each archetype and overall, with 95% CIs, written to `results/benchmark_history.csv` with the git tag and date.

Every version of JackTen runs the same benchmark, so improvement over time is measured, not claimed.

---

## 8. Evaluation: showing the bot works and improves

### 8.1 Comparison ladder

All bots run the same benchmark.

| Bot | What it shows |
| --- | --- |
| Random | The floor |
| Baseline | The reference |
| Baseline + raw-stat exploits (fixed thresholds on VPIP/PFR, like a basic HUD) | What a simple, non-statistical exploit achieves |
| Baseline + pooled model (K = 1) | Whether types matter, or one average opponent is enough |
| Baseline + mixture model, no range updates | What type-aware exploits achieve on their own |
| **JackTen v1 (baseline + mixture model + range updates)** | The headline |
| Baseline + oracle exploit (told the true type) | The ceiling: the most type-based exploitation could gain |

**Headline claim, if the data supports it:** JackTen v1 beats the baseline, the raw-stat bot and the pooled model, and closes X% of the gap to the oracle.

### 8.2 Variance reduction (the quant part)

Poker results are very noisy; the standard deviation is often around 100 bb/100, so naive comparisons need hundreds of thousands of hands. v1 uses:

1. **Duplicate deals:** the same cards are played by both bots being compared, removing most card luck.
2. **Common random numbers:** paired comparisons share seeds.
3. **All-in EV control variate:** when players are all in before the river, score the expected value from equity rather than the realised outcome. More generally, Y_adj = Y - beta X, where X is a luck term with known mean zero, which reduces variance by a factor of 1 - rho^2.

The pilot (Phase 1) measures the actual standard deviation before and after each step, then sets the benchmark size (D9) to hit a target CI width of plus or minus 2 bb/100. The write-up reports how much each step reduced variance: the same techniques used to price derivatives by Monte Carlo.

### 8.3 Learning curves (how the bot improves as it watches)

For each archetype, run fresh opponents and record, after 0, 25, 50, 100, 250, 500 and 1,000 observed actions:

- the posterior probability on the true type;
- MAP type accuracy;
- lambda (how much JackTen is exploiting);
- win rate in that window, with CIs.

This is the main chart: confidence and win rate rising as JackTen learns a player.

### 8.4 Model recovery study (known truth)

A small Monte Carlo study inside the project: R = 200 replications, varying true K (3, 4, 5), opponents per pool (20, 50, 100) and hands per opponent (100, 500, 2,000). Report:

- K selection accuracy for bootstrap LRT, BIC and ICL;
- adjusted Rand index between estimated and true types;
- mean absolute error in theta;
- confusion matrix of MAP type against true type.

### 8.5 Robustness

- **Hold-out trapper:** does JackTen fall back toward baseline rather than misclassify confidently?
- **Style switcher:** with and without discounting (D18), how fast does JackTen notice?
- **Baseline guarantee:** with the model off, results match the baseline exactly.
- **Format generalisation:** results on every format in the grid, including those not used for tuning.

---

## 9. Required tests

| Test | Checks |
| --- | --- |
| `test_protocol_conformance.py` | Every message type parses and round-trips |
| `test_legal_actions.py` | No illegal action across 1M random hands |
| `test_timing.py` | Decision time under the D5 budget at the 99.9th percentile |
| `test_seed_reproducibility.py` | Same seed, same deals, same results |
| `test_evaluator_bruteforce.py` | Evaluator matches brute force |
| `test_baseline_guarantee.py` | Model disabled or empty: decisions identical to baseline |
| `test_no_showdown_leak.py` | The opponent model never reads hole cards |
| `test_no_hardcoded_settings.py` | Changing blinds, stacks or seat count changes no code path except through `settings/` |
| `test_range_update.py` | Section 6.7 |
| `test_seed_separation.py` | Dev and benchmark seeds never overlap |
| `test_em_*.py`, `test_bootstrap_lrt.py`, `test_posterior.py`, `test_winrate_se.py`, `test_control_variate.py` | Section 6.7 |

---

## 10. Repository additions

```
jackten/
  README.md                    <- existing; headline result and chart added at v1
  ROADMAP.md                   <- existing
  poker_bot_messages.md        <- existing
  JACKTEN_V1_PLAN.md           <- this file
  DECISIONS.md                 <- running decision log
  configs/
    benchmark.yaml             <- frozen per version
    archetypes.yaml            <- opponent definitions
  src/jackten/
    protocol/  state/  cards/  history/
    harness/                   <- dealer, runner, seeds
    bots/                      <- random, always_call, archetypes, baseline
    model/                     <- contexts, em, select_k, posterior
    policy/                    <- exploit settings, blend, decision
    eval/                      <- benchmark, variance_reduction, learning_curves, recovery
    viz/                       <- charts, posterior animation, hand replayer
  scripts/
  tests/
  results/
    benchmark_history.csv
  docs/
    derivations/               <- Josh's hand derivations (scanned or typed)
  site/                        <- static showcase page
  report/                      <- the write-up
```

---

## 11. Timeline

About 17 weeks at 5 to 8 hours a week, lighter during exams and over Christmas. Estimated 90 to 120 hours.

| Phase | Dates | Main work | Exit criterion |
| --- | --- | --- | --- |
| 0. Protocol and harness | 6 Oct to 2 Nov | Section 5 | Section 5 "done when" |
| 1. Baseline, pool, benchmark | 3 Nov to 30 Nov | Section 7, variance-reduction pilot | Baseline beats weak bots with CIs; benchmark frozen as v0.1 |
| 2a. Mixture model offline | 1 Dec to 21 Dec | EM, K selection, recovery study | Recovers true types on simulated pools |
| 2b. Online model, ranges and exploits | 22 Dec to 12 Jan | Posterior, range updates, exploit settings, blend, comparison ladder | JackTen v1 beats baseline on the benchmark |
| 3. Evaluation and showcase | 13 Jan to 31 Jan | Learning curves, robustness, Section 13 deliverables | Section 12 checklist complete |

---

## 12. v1 is done when

- [ ] All Section 9 tests pass.
- [ ] The benchmark reports JackTen v1 against every rung of the comparison ladder, with 95% CIs.
- [ ] The learning-curve chart and the recovery study are complete.
- [ ] The README leads with the headline result and one chart.
- [ ] The write-up, showcase page and demo video exist (Section 13).
- [ ] Josh can answer every question in Section 14 without notes.

If JackTen v1 does not beat the baseline, v1 still ships: the write-up reports where and why the model fell short. An honest negative result with a clean method is still a strong project.

---

## 13. Showcase deliverables

1. **Headline result:** one sentence and one number with a CI, for example "JackTen's opponent model added X bb/100 (95% CI a to b) over its baseline, closing Y% of the gap to an oracle that knows each opponent's type."
2. **Learning-curve chart:** win rate and type confidence rising with hands observed.
3. **Posterior animation (GIF, about 20 seconds):** JackTen's read on one opponent sharpening hand by hand.
4. **Hand replayer page:** a static web page stepping through sample hands, showing the action, JackTen's posterior on each opponent, lambda, and why it chose its action. Linked from the README and the resume.
5. **Benchmark history chart:** bb/100 by version, so every later improvement is measured on the same test.
6. **Write-up (8 to 12 pages):** each technical section paired with a plain-English explanation; includes the selection-bias argument, the non-standard K test, the variance-reduction results and an honest statement of how AI was used.
7. **Demo video (2 minutes):** the replayer and the learning curve, narrated.
8. **Resume bullet and LinkedIn post** once results are in.

---

## 14. Interview questions Josh must be able to answer

1. Why model opponents as a mixture of types rather than tracking raw stats?
2. Derive the EM updates. Why does the log-likelihood never decrease?
3. Why is the standard likelihood-ratio test invalid for choosing K, and what did you do instead?
4. Why not learn from shown-down hands?
5. What does your conditional independence assumption get wrong, and how did you test its impact?
6. How did you make sure JackTen never plays worse than its baseline when it knows nothing?
7. Poker is noisy. How did you know a 3 bb/100 gain was real? What did each variance-reduction step buy you?
8. What happens against a player whose style is not in your model, or who changes style?
9. Couldn't a smart opponent exploit your exploits? What would you change?
10. What did AI write, and what did you decide?
11. How does JackTen turn action frequencies into a range without seeing cards, and where does that assumption break?
12. How does the same bot handle different blinds, stacks and table sizes, and what changes at 20 big blinds?

---

## 15. After v1

- Phase 3: neural opponent embeddings, compared on the same benchmark.
- Phase 4: likelihood-trained value net.
- AIVAT for further variance reduction.
- ICM-aware decisions for tournament payout stages.
- A joint within-hand update of type and range.
- Raise-size buckets as extra action categories.
- A counter-exploit test: an adaptive opponent that punishes over-exploitation.
- Entering the bot in the tournament engine's live events, if available.
