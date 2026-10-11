from bot.combinatorics import remaining_deck, live_combos, parse_cards
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

def equity_monte_carlo(hero, board, n, rng=None):
    """Monte Carlo equity vs one random hand. Returns (equity, standard_error)."""
    if n < 1:
        raise ValueError("n must be at least 1")
    hero, board = list(hero), list(board)
    if rng is None:
        rng = random.Random()

    score = 0
    combos = live_combos(hero, board)
    hero_now = evaluate(hero + board)
    curr_win_score = 0
    curr_lose_score = 0
    start_losing = 0
    start_winning = 0
    winning = None
    for i in range(n):
        opp = rng.choice(combos)
        opp_now = evaluate(opp + board)
        if opp_now>hero_now:
            winning = False
            start_losing += 1
        else:
            winning = True
            start_winning += 1
        deck = remaining_deck(hero, opp, board)
        sample = rng.sample(deck, 5 - len(board))
        full_board = sample + board
        hero_score = evaluate(hero+full_board)
        eval = showdown(hero_score, opp, full_board)
        score += eval
        if winning and eval ==0:
            curr_win_score += 1
        elif not winning and eval>0:
            curr_lose_score += 1

    Ppot = curr_lose_score/start_losing
    Npot = curr_win_score/start_winning

    score = score/n
    se = math.sqrt(score*(1-score)/n)
    return score, se, Ppot, Npot



def estimate_equity(hero, board, rng=None, n=2000):
    """Equity vs one random hand, exact on the river, Monte Carlo before it.

    Exact on the turn took about 600 ms a decision (45k evaluations), so it is sampled.
    Returns (equity, standard_error); the error is 0 for exact results.
    """
    if len(board) == 5:
        return equity_exact(hero, board), 0.0
    hs, se, Ppot, Npot = equity_monte_carlo(hero, board, n, rng)
    return (hs*(1-Npot)+(1-hs)*Ppot), se
