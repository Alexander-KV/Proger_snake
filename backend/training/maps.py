from random import Random
from typing import Annotated

from pydantic import BaseModel, Field

from backend.training.geometry import OPPOSITE, Direction, move
from backend.training.state import ArenaState, Snake

Count = Annotated[int, Field(ge=0, le=1024)]


class ArenaConfig(BaseModel):
    width: int = Field(default=16, ge=8, le=32)
    height: int = Field(default=12, ge=8, le=32)
    snake_count: int = Field(default=2, ge=2, le=4)
    tick_limit: int = Field(default=300, ge=1, le=1000)
    obstacles: Count = 6
    water: Count = 12
    normal: Count = 4
    gold: Count = 1
    poison: Count = 2
    shields: Count = 1


def generate_map(
    config: ArenaConfig,
    seed: int,
    players: list[tuple[int, str]] | None = None,
    *,
    empty: bool = False,
) -> ArenaState:
    w, h = config.width, config.height
    spots = [(2, 2), (w - 3, h - 3), (w - 3, 2), (2, h - 3)]
    directions: tuple[Direction, ...] = ("RIGHT", "LEFT", "DOWN", "UP")
    if players is None:
        players = [
            (i, "Ваш алгоритм" if i == 1 else f"Соперник {i - 1}")
            for i in range(1, config.snake_count + 1)
        ]
    snakes = tuple(
        Snake(
            id=id,
            name=name,
            body=(head, move(head, OPPOSITE[direction])),
            direction=direction,
        )
        for (id, name), head, direction in zip(players, spots, directions)
    )
    state = ArenaState(
        width=w, height=h, snakes=snakes, seed=seed, tick_limit=config.tick_limit
    )
    if empty:
        return state
    reserved = {
        cell for s in snakes for cell in (*s.body, move(s.body[0], s.direction))
    }
    free = [(x, y) for y in range(h) for x in range(w) if (x, y) not in reserved]
    counts = (
        config.obstacles,
        config.water,
        config.normal,
        config.gold,
        config.poison,
        config.shields,
    )
    if sum(counts) > len(free):
        raise ValueError(f"На поле доступно {len(free)} клеток для объектов.")
    Random(seed).shuffle(free)
    obstacles, water, normal, gold, poison, shields = (
        frozenset(free.pop() for _ in range(count)) for count in counts
    )
    food = {**dict.fromkeys(normal, "normal"), **dict.fromkeys(gold, "gold")}
    return state.model_copy(
        update={
            "obstacles": obstacles,
            "water": water,
            "food": food,
            "poison": poison,
            "shields": shields,
            "food_targets": {"normal": config.normal, "gold": config.gold},
        }
    )
