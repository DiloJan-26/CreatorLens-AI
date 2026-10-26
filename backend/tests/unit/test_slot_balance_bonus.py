from app.rag.reranker import slot_balance_bonus


def test_slot_balance_bonus_rewards_an_unrepresented_slot() -> None:
    desired_slots = {"content_1", "content_2"}

    assert slot_balance_bonus("content_2", {"content_1"}, desired_slots) == 1.0
    assert slot_balance_bonus("content_1", {"content_1"}, desired_slots) == 0.0


def test_slot_balance_bonus_ignores_unknown_slots() -> None:
    assert slot_balance_bonus(None, set(), {"content_1", "content_2"}) == 0.0
