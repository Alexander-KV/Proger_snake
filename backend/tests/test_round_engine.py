from backend import round_engine
from backend.round_engine import RoundState, Snake, advance


def test_snake_eats_and_grows_while_other_hits_wall(monkeypatch):
    monkeypatch.setattr(
        round_engine, "choose_direction", lambda snake, *_: snake.direction
    )
    state = RoundState(
        food=(4, 2),
        snakes=[
            Snake(
                team_id=1,
                name="One",
                strategy="food",
                body=[(3, 2), (2, 2), (1, 2)],
                direction="RIGHT",
            ),
            Snake(
                team_id=2,
                name="Two",
                strategy="space",
                body=[(0, 4), (1, 4), (2, 4)],
                direction="LEFT",
            ),
        ],
    )
    assert advance(state, 16, 1)
    assert state.snakes[0].body == [(4, 2), (3, 2), (2, 2), (1, 2)]
    assert state.snakes[0].score == 1
    assert state.food not in state.snakes[0].body
    assert state.snakes[1].eliminated_at == 1
    assert state.winner_ids == [1]


def test_head_collision_on_food_eliminates_both_without_points():
    state = RoundState(
        food=(4, 2),
        snakes=[
            Snake(
                team_id=1,
                name="One",
                strategy="food",
                body=[(3, 2), (2, 2), (1, 2)],
                direction="RIGHT",
            ),
            Snake(
                team_id=2,
                name="Two",
                strategy="food",
                body=[(5, 2), (6, 2), (7, 2)],
                direction="LEFT",
            ),
        ],
    )
    assert advance(state, 16, 1)
    assert [(snake.eliminated_at, snake.score) for snake in state.snakes] == [
        (1, 0),
        (1, 0),
    ]
    assert state.winner_ids == [1, 2]


def test_space_strategy_yields_food_to_avoid_head_collision():
    state = RoundState(
        food=(4, 2),
        snakes=[
            Snake(
                team_id=1,
                name="One",
                strategy="food",
                body=[(3, 2), (2, 2), (1, 2)],
                direction="RIGHT",
            ),
            Snake(
                team_id=2,
                name="Two",
                strategy="space",
                body=[(5, 2), (6, 2), (7, 2)],
                direction="LEFT",
            ),
        ],
    )
    assert not advance(state, 16, 1)
    assert [snake.score for snake in state.snakes] == [1, 0]
    assert all(snake.eliminated_at is None for snake in state.snakes)
