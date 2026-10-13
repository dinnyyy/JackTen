from bots.v4.combinatorics import remaining_deck, live_combos, filter_range, parse_cards
from engine.evaluator import evaluate
from itertools import combinations
import random
import math

def showdown(hero_score, opps, board):
    """Score the hero against every opponent hand on a full 5-card board: 1 win, 0 loss, and a tie
    with k opponents splits the pot 1/(k+1).

    opps is a list of hole-card pairs. hero_score is evaluate(hero + board), computed once by the caller and reused.
    """
    best = max(evaluate(list(opp) + board) for opp in opps)
    if hero_score > best:
        return 1
    if hero_score == best:
        tied = sum(1 for opp in opps if evaluate(list(opp) + board) == hero_score)
        return 1 / (tied + 1)
    return 0


def equity_exact(hero, board):
    """Exact equity vs one random hand: enumerate every opponent hand and every runout. Heads-up only; multiway
    enumeration is too large, use equity_monte_carlo.

    hero and board are lists of card ints. Cheap on the river (about 1k evaluations), about 45k on the turn and 1M on the
    flop, so use Monte Carlo before the river at the table.
    """
    hero, board = list(hero), list(board)
    num_remaining = 5-len(board)
    score = 0
    i = 0
    for opp in live_combos(hero, board):
        deck = remaining_deck(hero, board, opp)
        if num_remaining==0:
            hero_score = evaluate(hero+board)
            score +=showdown(hero_score, [opp], board)
            i +=1
        else:
            for runout in combinations(deck, num_remaining):
                hero_score = evaluate(hero+board+list(runout))
                score +=showdown(hero_score, [opp], board + list(runout))
                i +=1

    return score/i

def _opponent_pools(hero, board, opponents, ranges):
    """One (hands, weights) pool per opponent with hero and board cards removed. weights is None for a uniform pool."""
    if ranges is None:
        pool = (live_combos(hero, board), None)
        return [pool] * opponents
    pools = []
    for r in ranges:
        if r is None:
            pools.append((live_combos(hero, board), None))
            continue
        live = filter_range(r, hero, board)
        if not live:
            raise ValueError("an opponent range has no live combos")
        pools.append((list(live), list(live.values())))
    return pools


def _deal_opponents(pools, rng):
    """Draw one hand per pool with no shared cards. Independent draws rejected on overlap give the exact joint
    distribution conditioned on the hands being disjoint."""
    for _ in range(1000):
        opps, used = [], set()
        for hands, weights in pools:
            opp = rng.choice(hands) if weights is None else rng.choices(hands, weights)[0]
            if opp[0] in used or opp[1] in used:
                break
            used.update(opp)
            opps.append(opp)
        else:
            return opps
    raise ValueError("could not deal disjoint opponent hands from these ranges")


def equity_monte_carlo(hero, board, n, rng=None, players_left=1, potential=False, target_se=None, batch=200, ranges=None):
    """Monte Carlo equity vs players_left opponents. Returns (equity, standard_error).

    players_left is the number of opponents still in the hand (not counting the hero). Each holds a random hand,
    unless ranges is given: a list with one entry per opponent, each a {combo: weight} dict (or None for a random
    hand). Then len(ranges) sets the opponent count. Ties split the pot, so equity is the expected pot share.

    With potential=True, the same simulation also tallies hand potential and returns
    (equity, standard_error, ppot, npot). ppot: chance of finishing ahead given behind now. npot: chance of finishing
    behind given ahead now. Ties count as a split (Billings). Needs a flop or turn board; a potential is None if no
    sample started in the state it conditions on.

    With target_se, n is a cap: after every `batch` samples it stops once the standard error is at or below the target.
    The check uses add-one smoothed equity, so a lucky run of all wins or all losses cannot end it early at SE = 0.
    The SE returned is for the samples actually used.
    """
    if n < 1:
        raise ValueError("n must be at least 1")
    opponents = len(ranges) if ranges is not None else players_left
    if opponents < 1:
        raise ValueError("need at least one opponent")
    if potential and len(board) not in (3, 4):
        raise ValueError("potential needs a flop or turn board")
    hero, board = list(hero), list(board)
    if rng is None:
        rng = random.Random()

    pools = _opponent_pools(hero, board, opponents, ranges)
    if potential:
        hero_now = evaluate(hero + board)
        # hp[start][final]: 0 = behind, 1 = tied, 2 = ahead; start on the current board, final at showdown
        hp = [[0, 0, 0] for _ in range(3)]
    score = 0
    used = 0
    for _ in range(n):
        opps = _deal_opponents(pools, rng)
        deck = remaining_deck(hero, *opps, board)
        full_board = board + rng.sample(deck, 5 - len(board))
        result = showdown(evaluate(hero + full_board), opps, full_board)
        score += result
        if potential:
            opp_now = max(evaluate(list(opp) + board) for opp in opps)
            start = 2 if hero_now > opp_now else 1 if hero_now == opp_now else 0
            hp[start][2 if result == 1 else 0 if result == 0 else 1] += 1
        used += 1
        if target_se is not None and used % batch == 0:
            p = (score + 1) / (used + 2)
            if math.sqrt(p * (1 - p) / used) <= target_se:
                break

    equity = score / used
    se = math.sqrt(equity * (1 - equity) / used)
    if not potential:
        return equity, se

    behind, tied, ahead = sum(hp[0]), sum(hp[1]), sum(hp[2])
    ppot = (hp[0][2] + hp[0][1] / 2 + hp[1][2] / 2) / (behind + tied / 2) if behind + tied else None
    npot = (hp[2][0] + hp[2][1] / 2 + hp[1][0] / 2) / (ahead + tied / 2) if ahead + tied else None
    return equity, se, ppot, npot
