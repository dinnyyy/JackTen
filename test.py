from treys import Card, Deck, Evaluator

evaluator = Evaluator()
board = [Card.new('Ah'), Card.new('Kd'), Card.new('Qc')]
hand  = [Card.new('Jh'), Card.new('Th')]
rank = evaluator.evaluate(hand, board)
print(rank, evaluator.class_to_string(evaluator.get_rank_class(rank)))
# should print: 1600 Straight