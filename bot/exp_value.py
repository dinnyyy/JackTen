def calc_ev(pot, to_call, equity):
    bet = 0.75*pot
    amount = 0
    opp_fold_prob = fold_prob(pot, bet)   
    ev_call = equity*pot - (1-equity)*to_call
    ev_bet = opp_fold_prob*pot + (1-opp_fold_prob)*(equity*(pot+bet)-(1-equity)*bet)
    ev_fold = 0

    evs = {
        "bet": ev_bet,
        "call": ev_call,
        "fold": ev_fold
    }

    action = max(evs, key=evs.get)
    if to_call == 0 and action!="bet":
        return "call", 0
    if action == "bet":
        amount = bet
    return action, amount

def fold_prob(pot, bet):
    return 0.4