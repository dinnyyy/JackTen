from bot.combinatorics import remaining_deck, live_combos, parse_cards
from engine.evaluator import evaluate
from itertools import combinations
import random
import math

def showdown(hero_score, opp, board):
    """Idea is the simulation produces len(opps) possibilities for opponents, which we evaluate our average score"""
   
    opp_score = evaluate(list(opp) + board)
    if hero_score>opp_score:
        return 1
    elif hero_score==opp_score:
        return 0.5
    return 0


def equity_exact(hero, board):
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
    if rng==None:
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

