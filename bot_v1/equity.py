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

def equity_monte_carlo(hero, board, n, rng=None):
    """Monte Carlo equity vs one random hand. Returns (equity, standard_error)."""
    if n < 1:
        raise ValueError("n must be at least 1")
    hero, board = list(hero), list(board)
    if rng is None:
        rng = random.Random()

    score = 0
    combos = live_combos(hero, board)
    for i in range(n):
        random_hand = rng.choice(combos)
        deck = remaining_deck(hero, random_hand, board)
        sample = rng.sample(deck, 5 - len(board))
        full_board = sample + board
        hero_score = evaluate(hero+full_board)
        score += showdown(hero_score, random_hand, full_board)
    score = score/n
    se = math.sqrt(score*(1-score)/n)
    return score, se



def estimate_equity(hero, board, rng=None, n=2000):
    """Equity vs one random hand, exact on the river, Monte Carlo before it.

    Exact on the turn took about 600 ms a decision (45k evaluations), so it is sampled.
    Returns (equity, standard_error); the error is 0 for exact results.
    """
    if len(board) == 5:
        return equity_exact(hero, board), 0.0
    return equity_monte_carlo(hero, board, n, rng)
