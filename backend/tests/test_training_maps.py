import pytest

from backend.training.bots import decide_bot
from backend.training.geometry import move
from backend.training.maps import ArenaConfig, generate_map
from backend.training.state import ArenaState, Snake, build_observation


def test_generation_replays_and_leaves_clear_starts():
    config = ArenaConfig(width=8, height=12, snake_count=4)
    state = generate_map(config, 18)
    assert state == generate_map(config, 18)
    assert state != generate_map(config, 19)
    groups = [
        state.obstacles,
        state.water,
        state.food.keys(),
        state.poison,
        state.shields,
        [
            cell
            for snake in state.snakes
            for cell in (*snake.body, move(snake.body[0], snake.direction))
        ],
    ]
    assert len(set().union(*groups)) == sum(map(len, groups))
    with pytest.raises(ValueError):
        generate_map(config.model_copy(update={"water": 100}), 18)
    empty = generate_map(config, 18, empty=True)
    assert not (
        empty.obstacles
        or empty.water
        or empty.food
        or empty.poison
        or empty.shields
        or empty.food_targets
    )
    assert empty.snakes == state.snakes


def test_bots_handle_detour_and_mandatory_water_direction():
    own = Snake(id=1, name="A", direction="RIGHT", body=[(2, 2), (1, 2)])
    state = ArenaState(
        width=8,
        height=8,
        snakes=[own],
        food={(4, 2): "normal"},
        obstacles={(3, 2), (2, 3)},
    )
    for bot in ("hunter", "pathfinding", "survival"):
        assert decide_bot(bot, build_observation(state, 1), 1) == "UP"
    water = state.model_copy(
        update={"snakes": (own.model_copy(update={"target": (3, 2)}),)}
    )
    for bot in ("random", "hunter", "pathfinding", "survival"):
        assert decide_bot(bot, build_observation(water, 1), 1) == "RIGHT"
