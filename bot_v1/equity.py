from bot_v1.combinatorics import remaining_deck, live_combos, parse_cards
from engine.evaluator import evaluate
from itertools import combinations
import random
import math

def showdown(hero_score, opp, board):
    """Score one opponent hand against the hero on a full 5-card board: 1 win, 0.5 tie, 0 loss.

    hero_score is evaluate(hero + board), computed once by the caller and reused.
    """
    opp_score = evaluate(list(opp) + board)
    if hero_score>opp_score:
        return 1
    elif hero_score==opp_score:
        return 0.5
    return 0


def equity_exact(hero, board):
    """Exact equity vs one random hand: enumerate every opponent hand and every runout.

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
            score +=showdown(hero_score, opp, board)
            i +=1
        else:
            for runout in combinations(deck, num_remaining):
                hero_score = evaluate(hero+board+list(runout))
                score +=showdown(hero_score, opp, board + list(runout))
                i +=1

    return score/i

def equity_monte_carlo(hero, board, n, rng=None, potential=False, target_se=None, batch=200):
    """Monte Carlo equity vs one random hand. Returns (equity, standard_error).

    With potential=True, the same simulation also tallies hand potential and returns
    (equity, standard_error, ppot, npot). ppot: chance of finishing ahead given behind now. npot: chance of finishing
    behind given ahead now. Ties count half (Billings). Needs a flop or turn board; a potential is None if no
    sample started in the state it conditions on.

    With target_se, n is a cap: after every `batch` samples it stops once the standard error is at or below the target.
    The check uses add-one smoothed equity, so a lucky run of all wins or all losses cannot end it early at SE = 0.
    The SE returned is for the samples actually used.
    """
    if n < 1:
        raise ValueError("n must be at least 1")
    if potential and len(board) not in (3, 4):
        raise ValueError("potential needs a flop or turn board")
    hero, board = list(hero), list(board)
    if rng is None:
        rng = random.Random()

    combos = live_combos(hero, board)
    if potential:
        hero_now = evaluate(hero + board)
        # hp[start][final]: 0 = behind, 1 = tied, 2 = ahead; start on the current board, final at showdown
        hp = [[0, 0, 0] for _ in range(3)]
    score = 0
    used = 0
    for _ in range(n):
        opp = rng.choice(combos)
        deck = remaining_deck(hero, opp, board)
        full_board = board + rng.sample(deck, 5 - len(board))
        result = showdown(evaluate(hero + full_board), opp, full_board)
        score += result
        if potential:
            opp_now = evaluate(list(opp) + board)
            start = 2 if hero_now > opp_now else 1 if hero_now == opp_now else 0
            hp[start][int(result * 2)] += 1
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
