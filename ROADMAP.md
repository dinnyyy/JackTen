# JackTen — Roadmap

Build plan, in dependency order. Phases 0–1 are engineering; Phases 2–4 are the
statistical work and are the point of the project.

Each phase is independently shippable: the bot is playable at the end of Phase 1,
and every later phase adds a layer that can be switched off without breaking it.

---

## Phase 0 — Protocol layer and harness

Plumbing. No strategy.

- NDJSON reader/writer over stdin/stdout, one object per line, integer money only.
- Message dispatch for `match_start`, `hand_start`, `action_request`,
  `action_taken`, `street_dealt`, `hand_result`, `match_end`.
- Game state tracker: stacks, pot, board, position relative to button, per-seat
  action history for the current hand.
- A local engine harness so bots can be run against each other offline. This is
  the single most valuable piece of infrastructure in the project — every later
  phase needs to generate hands in bulk.
- **Hand history logging**: append every `action_taken` and `hand_result` to disk
  as NDJSON. Phase 2 cannot start without this.
- Settle the all-in convention and the time-budget rule (see README).

**Done when:** two trivial bots (always-fold, always-call) can play a 500-hand
match against each other and produce a parseable hand history.

---

## Phase 1 — Baseline strategy

A competent, deterministic, explainable policy. Deliberately not clever — its job
is to be a stable reference point that later phases are measured against, and a
safe fallback when opponent reads are weak.

- 7-card hand evaluator.
- Preflop: range charts by position and action-facing.
- Postflop: equity estimate via Monte Carlo rollout, pot odds, simple board
  texture classification, a fixed bet-sizing ladder.

**Done when:** it beats always-call and always-raise convincingly over 10k hands,
and its win rate has tight enough error bars to serve as a benchmark.

---

## Phase 2 — Mixture-model opponent typing

The core statistical contribution. Estimate, from action frequencies alone, that
the player pool consists of a small number of unobserved behavioural types — and
maintain a live posterior over which type each opponent is.

### Why a mixture model rather than a classifier

Classification needs labels. Nobody has labelled the opponents, and hand-labelling
them encodes the labeller's priors rather than learning anything. A finite
mixture model is given only one input — an assumed number of types `K` — and
recovers from the data:

- what each type looks like (the action probabilities that define it),
- how common each type is in the population,
- and, for a specific opponent, the probability they belong to each type.

The types fall out of the structure of the data. Nothing defines "tight player"
in advance.

This is also more than clustering: it is a generative probability model, which
buys three things a bucketing algorithm cannot give.

1. **Soft assignments with real probabilities** — "68% type A, 29% type B, 3%
   type C" rather than a hard label. That uncertainty is itself an input to the
   betting decision.
2. **Cheap online updating** — after each observed action, the posterior over an
   opponent's type updates with one Bayes step. No refitting at the table.
3. **Standard errors on the type profiles themselves** — you know how precisely
   each type's c-bet frequency is pinned down, which bounds how hard it is safe
   to exploit.

### Model

Discretise each decision into a **context** `c` — street, position, facing
(unopened / facing bet / facing raise), and a coarse pot-odds bucket — and an
**action** `a` ∈ {fold, call/check, raise}.

Player `j` has an unobserved type `k ∈ {1..K}` drawn with probability `π_k`.
Conditional on type `k`, their action in context `c` is categorical with
probability vector `θ_kc`.

Because the type is never observed, each player's contribution to the likelihood
must sum over all the types they might be:

$$L_j(\pi, \theta) = \sum_{k=1}^{K} \pi_k \prod_{c} \prod_{a} \theta_{kca}^{\,n_{jca}}$$

where `n_jca` counts how often player `j` took action `a` in context `c`. The
sample log-likelihood is then

$$\ell(\pi, \theta) = \sum_{j} \log \sum_{k=1}^{K} \pi_k \prod_{c}\prod_{a} \theta_{kca}^{\,n_{jca}}$$

That outer `log` of an inner sum is what makes this hard: it does not decompose,
there is no closed-form maximum, and the surface is **not concave** — unlike
every likelihood in a standard regression course.

### Estimation

- **EM.** The E-step computes each player's responsibility `r_jk` — the current
  posterior probability that player `j` is type `k`. The M-step re-estimates `π`
  and `θ` as responsibility-weighted frequencies, which for categorical emissions
  is closed-form. Monotone increase in the likelihood is guaranteed; convergence
  to the *global* maximum is not.
- **Multiple random restarts**, keeping the best likelihood, because of the
  non-concavity above.
- **Newton-Raphson** as a cross-check on the final solution, and to confirm the
  Hessian is negative definite there.
- **Standard errors by outer product of gradients (OPG)**, `J = Σ_j s_j s_j'`,
  rather than the analytical Hessian — for mixtures the Hessian is unpleasant
  enough that OPG is the practical route. Louis's method is the more careful
  alternative if OPG proves unstable.
- **Label switching**: the likelihood is invariant to permuting the type labels,
  so runs must be canonically re-ordered (e.g. by ascending aggression frequency)
  before results are compared across restarts or bootstrap samples.

### Choosing K — and why the standard test fails

The obvious move is a likelihood ratio test of `K` types against `K+1`. It is
invalid here, for two compounding reasons:

1. Setting the extra component's weight to zero puts the null **on the boundary**
   of the parameter space, not in its interior.
2. Under that null, the extra component's action probabilities are **completely
   unidentified** — the likelihood is flat in them.

Both violate the regularity conditions behind the usual asymptotic chi-squared
distribution, so the standard critical values are simply wrong.

The plan is therefore to:

- simulate the null distribution of the LR statistic by **parametric bootstrap**
  — fit under `K`, generate synthetic player pools from that fit, refit under
  both `K` and `K+1`, and build the reference distribution empirically;
- cross-check against BIC and ICL as cheaper heuristics;
- report the bootstrap distribution against the naive chi-squared as a figure,
  since the gap between them *is* the interesting result.

### Serving the model at the table

- Offline: fit `(π, θ)` on the logged hand histories from Phase 0/1.
- Online: for each seat, accumulate `log θ_kca` over their observed actions and
  normalise to get a live posterior over their type. Starts at the population
  prior `π` and sharpens with every hand.
- Decision: compute the best response to the posterior-weighted opponent model,
  and blend from baseline toward that exploit as a function of posterior
  confidence (entropy of the posterior, or effective sample size). Weak read →
  baseline.

### Validation

Because the harness generates the data, the ground truth is known. Plant `K`
scripted opponent types, generate hands, fit the mixture blind, and check it
recovers the planted profiles and mixing weights — a genuine recovery experiment
rather than a plausibility argument.

**Done when:** the model recovers planted types; the bootstrap-based `K`
selection picks the right `K`; and the exploit layer beats the Phase 1 baseline
head-to-head against a mixed pool by a margin outside its error bars.

---

## Phase 3 — Neural opponent embeddings

Relax the assumption that opponents fall into `K` discrete buckets.

Replace the one-hot type with a continuous latent vector `z_j ∈ R^d`, produced by
a sequence encoder (GRU or small transformer) reading the opponent's action
history, trained to predict their next action. The embedding is the useful
by-product.

The relationship to Phase 2 is the point worth stating clearly: **the mixture
model is the special case where `z` is constrained to `K` one-hot vectors.** The
neural version is strictly more expressive — it can represent an opponent who is
partway between two styles, or who shifts mid-match — at the cost of the
interpretability and the clean inference machinery of Phase 2.

- Train on the same logged histories, with the same fully-observed action stream.
- Validate *against* Phase 2: project the learned embedding space and check
  whether it separates into the mixture model's discovered types. If it does,
  that is strong mutual corroboration. If it does not, the discrepancy is the
  more interesting finding.
- Watch inference cost — this now sits in the hot path under a 5s action budget.

**Done when:** next-action prediction beats the Phase 2 mixture model
out-of-sample, and the embedding space is shown to be interpretable relative to
the Phase 2 types.

---

## Phase 4 — Likelihood-trained value network with calibrated uncertainty

A network that estimates the value of each available action given the game state
and the current opponent read — and, critically, says how sure it is.

The framing that makes this more than a standard value net: **training with
squared-error loss is exactly Gaussian maximum likelihood with the variance held
fixed.** Once that is explicit, the fixed-variance assumption is visibly a choice
rather than a default, and can be dropped.

- Have the network output both a mean `μ(x)` and a variance `σ²(x)`, and train on
  the full Gaussian negative log-likelihood rather than MSE.
- The result is a per-spot uncertainty estimate: the bot distinguishes "this line
  is worth 2.1bb, confidently" from "worth 2.1bb, but I've barely seen this
  situation."
- Use it in the decision policy: high predictive variance is a reason to fall
  back toward the Phase 1 baseline or take the lower-variance line, which is the
  same conservatism principle as Phase 2's posterior-confidence blending, applied
  to a different source of doubt.
- **Calibration check** as the headline result: do the 90% predictive intervals
  contain the realised outcome 90% of the time? A network trained on MSE cannot
  even be asked this question.
- *Stretch:* Laplace approximation — invert the Fisher information at the trained
  weights to get uncertainty over the parameters, not just over the noise.

**Done when:** predictive intervals are calibrated within a few points of
nominal, and uncertainty-aware action selection beats the point-estimate version
over a long match.

---

## Notes on scope

Phases 2–4 are ordered by dependency but also by risk. Phase 2 is the one with a
guaranteed result — even a negative one is publishable as a writeup, since
"recovers planted types, `K` selection needs bootstrap" is a complete finding.
Phases 3 and 4 are worth attempting only once Phase 2 is producing a working
posterior at the table, and neither should be allowed to block a bot that plays.
