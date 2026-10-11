from evals.datasets.build_golden import CASES, HELDOUT, check_and_expand


def test_every_hand_label_agrees_with_rules_engine():
    for case in CASES + HELDOUT:
        check_and_expand(case)  # raises on any disagreement
