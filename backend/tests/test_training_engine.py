import pytest

from backend.training.engine import advance
from backend.training.state import ArenaState, Snake, build_observation


def snake(id, body, direction="RIGHT", **kwargs):
    return Snake(id=id, name=str(id), body=body, direction=direction, **kwargs)


def arena(*snakes, **kwargs):
    return ArenaState(width=8, height=8, snakes=snakes, **kwargs)


def test_same_destination_and_swapped_heads():
    for x in (3, 4):
        first = snake(1, [(2, 2), (1, 2)])
        second = snake(2, [(x, 2), (x + 1, 2)], "LEFT")
        result = advance(arena(first, second), {})
        assert result.finished and result.winners == []
        assert all(not s.alive for s in result.snakes)


def test_tail_released_only_on_successful_step_without_growth():
    first = snake(1, [(2, 2), (1, 2)])
    second = snake(2, [(3, 1), (3, 2)], "UP")
    assert all(s.alive for s in advance(arena(first, second), {}).snakes)
    for objects in (
        {"food": {(3, 0): "normal"}},
        {"obstacles": {(3, 0)}},
        {"water": {(3, 0)}},
    ):
        forward = advance(arena(first, second, **objects), {})
        backward = advance(arena(second, first, **objects), {})
        assert forward == backward
        assert not forward.snakes[0].alive


def test_water_locks_direction_then_allows_dry_exit():
    first = snake(1, [(2, 2), (1, 2)])
    second = snake(2, [(6, 6), (6, 7)], "UP")
    state = advance(arena(first, second, water={(3, 2)}), {})
    observation = build_observation(state, 1)
    assert observation["self"]["allowed_directions"] == ["RIGHT"]
    assert observation["self"]["head"] == [2.5, 2]
    assert state.snakes[0].body == first.body
    state = advance(state, {1: "UP"})
    assert state.snakes[0].body[0] == (3, 2)
    assert advance(state, {1: "UP"}).snakes[0].body[0] == (3, 1)


def test_reserved_water_destination_and_opposite_edge():
    first = snake(1, [(2, 2), (1, 2)], target=(3, 2))
    for second in (
        snake(2, [(4, 2), (5, 2)], "LEFT"),
        snake(2, [(3, 2), (4, 2)], "LEFT"),
    ):
        assert advance(arena(first, second, water={(3, 2)}), {}).winners == []


@pytest.mark.parametrize("length,remaining", [(6, 5), (3, 2), (2, 2)])
def test_poison_shrinks_or_kills(length, remaining):
    body = [(6 - i, 2) for i in range(length)]
    first = snake(1, body)
    second = snake(2, [(6, 6), (6, 7)], "UP")
    result = advance(arena(first, second, poison={(7, 2)}), {})
    assert result.snakes[0].length == remaining
    assert result.snakes[0].alive == (length > 2)
    assert result.snakes[0].score == 0
    assert not result.poison


def test_shield_protects_from_water_and_one_poison_and_expires():
    first = snake(1, [(2, 2), (1, 2)])
    second = snake(2, [(1, 6), (0, 6)])
    state = advance(
        arena(first, second, shields={(3, 2)}, water={(4, 2)}, poison={(5, 2), (6, 2)}),
        {},
    )
    assert state.snakes[0].shield_until == 11
    state = advance(state, {})
    assert state.snakes[0].body[0] == (4, 2)
    state = advance(state, {})
    assert state.snakes[0].shield_until == 0
    state = advance(state, {})
    assert not state.snakes[0].alive
    expired = advance(
        arena(
            first.model_copy(update={"shield_until": 1}), second, tick=1, water={(3, 2)}
        ),
        {},
    )
    assert expired.snakes[0].target == (3, 2)


def test_scoring_finish_and_ranking():
    first = snake(1, [(2, 2), (1, 2)], score=20)
    second = snake(2, [(2, 6), (1, 6)])
    state = advance(
        arena(first, second, tick_limit=1, food={(3, 2): "normal", (3, 6): "gold"}), {}
    )
    assert [s.score for s in state.snakes] == [30, 30]
    assert [s.length for s in state.snakes] == [3, 3]
    assert state.winners == [1, 2]
    assert [row["place"] for row in state.result_rows()] == [1, 1]
    dead_high_score = advance(arena(first, second, obstacles={(3, 2)}), {})
    assert dead_high_score.winners == [2]


def test_own_tail_is_available_and_other_body_segments_are_occupied():
    body = [(2, 2), (2, 3), (1, 3), (1, 2)]
    other = snake(2, [(6, 6), (6, 7)], "UP")
    turning = snake(1, body, "UP")
    assert advance(arena(turning, other), {1: "LEFT"}).snakes[0].body[0] == (1, 2)
    longer = snake(1, [*body, (1, 1)], "UP")
    assert not advance(arena(longer, other), {1: "LEFT"}).snakes[0].alive


def test_poison_releases_second_tail_only_if_eater_survives():
    first = snake(1, [(2, 2), (1, 2)])
    body = [(3, 1), (3, 2)]
    state = advance(arena(first, snake(2, [*body, (4, 2)], "UP"), poison={(3, 0)}), {})
    assert state.snakes[0].alive and state.snakes[1].length == 2
    state = advance(arena(first, snake(2, body, "UP"), poison={(3, 0)}), {})
    assert state.winners == [] and not any(s.alive for s in state.snakes)
