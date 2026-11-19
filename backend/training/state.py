from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.training.geometry import OPPOSITE, VECTORS, Cell, Direction

FoodKind = Literal["normal", "gold"]
SHIELD_TICKS = 10


class Snake(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: int
    name: str
    body: tuple[Cell, ...]
    direction: Direction
    target: Cell | None = None
    score: int = 0
    shield_until: int = 0
    dead_length: int = 0

    @property
    def alive(self) -> bool:
        return bool(self.body)

    @property
    def length(self) -> int:
        return len(self.body) if self.alive else self.dead_length

    def allowed(self) -> list[Direction]:
        if self.target is not None:
            return [self.direction]
        return [
            direction for direction in VECTORS if direction != OPPOSITE[self.direction]
        ]

    def shielded(self, tick: int) -> bool:
        return self.shield_until > tick


class ArenaState(BaseModel):
    model_config = ConfigDict(frozen=True)
    width: int
    height: int
    snakes: tuple[Snake, ...]
    tick: int = 0
    tick_limit: int = 300
    obstacles: frozenset[Cell] = frozenset()
    water: frozenset[Cell] = frozenset()
    food: dict[Cell, FoodKind] = Field(default_factory=dict)
    poison: frozenset[Cell] = frozenset()
    shields: frozenset[Cell] = frozenset()
    seed: int = 0
    food_targets: dict[FoodKind, int] = Field(default_factory=dict)

    def inside(self, cell: Cell) -> bool:
        return 0 <= cell[0] < self.width and 0 <= cell[1] < self.height

    @property
    def finished(self) -> bool:
        return self.tick >= self.tick_limit or sum(s.alive for s in self.snakes) <= 1

    @property
    def winners(self) -> list[int]:
        alive = [s for s in self.snakes if s.alive]
        if not self.finished or not alive:
            return []
        score = max(s.score for s in alive)
        return sorted(s.id for s in alive if s.score == score)

    def result_rows(self) -> list[dict]:
        rows = []
        previous = None
        place = 0
        for index, snake in enumerate(
            sorted(self.snakes, key=lambda s: (not s.alive, -s.score, s.id)), 1
        ):
            key = (snake.alive, snake.score)
            if key != previous:
                place = index
                previous = key
            rows.append(
                {
                    "id": snake.id,
                    "name": snake.name,
                    "alive": snake.alive,
                    "score": snake.score,
                    "length": snake.length,
                    "place": place,
                }
            )
        return rows


def snake_view(state: ArenaState, snake: Snake) -> dict:
    view = {
        "id": snake.id,
        "name": snake.name,
        "body": [list(cell) for cell in snake.body],
        "direction": snake.direction,
        "length": snake.length,
        "score": snake.score,
        "alive": snake.alive,
    }
    if not snake.alive:
        return {**view, "head": None, "movement": None}
    origin = snake.body[0]
    target = snake.target
    head = (
        list(origin)
        if target is None
        else [(a + b) / 2 for a, b in zip(origin, target)]
    )
    shield = max(0, snake.shield_until - state.tick)
    return dict(
        view,
        head=head,
        effects={"shield_ticks": shield},
        movement={
            "origin": list(origin),
            "target": list(target) if target else None,
            "progress": 0.5 if target else 0,
            "in_water": (target or origin) in state.water,
            "slowed": target is not None or (origin in state.water and not shield),
            "can_turn": target is None,
        },
    )


def object_view(state: ArenaState) -> dict:
    def cells(positions):
        return [list(cell) for cell in sorted(positions)]

    return {
        "obstacles": cells(state.obstacles),
        "water": cells(state.water),
        "poison": cells(state.poison),
        "food": [
            {"cell": list(cell), "kind": kind}
            for cell, kind in sorted(state.food.items())
        ],
        "powerups": [
            {
                "cell": list(cell),
                "kind": "shield",
                "duration": SHIELD_TICKS,
                "blocks_poison": 1,
                "blocks_water_slowdown": True,
            }
            for cell in sorted(state.shields)
        ],
    }


def build_observation(state: ArenaState, snake_id: int) -> dict:
    own = next(s for s in state.snakes if s.id == snake_id and s.alive)
    return dict(
        width=state.width,
        height=state.height,
        tick=state.tick,
        ticks_remaining=max(0, state.tick_limit - state.tick),
        self=dict(snake_view(state, own), allowed_directions=own.allowed()),
        opponents=[
            snake_view(state, s) for s in state.snakes if s.alive and s.id != snake_id
        ],
        **object_view(state),
    )


def arena_view(state: ArenaState) -> dict:
    return dict(
        width=state.width,
        height=state.height,
        tick=state.tick,
        tick_limit=state.tick_limit,
        snakes=[snake_view(state, s) for s in state.snakes],
        finished=state.finished,
        winners=state.winners,
        results=state.result_rows() if state.finished else [],
        **object_view(state),
    )


def encode_state(state: ArenaState) -> dict:
    return {
        **state.model_dump(mode="json", exclude={"food"}),
        "food": object_view(state)["food"],
    }


def decode_state(data: dict) -> ArenaState:
    return ArenaState.model_validate(
        {**data, "food": {tuple(item["cell"]): item["kind"] for item in data["food"]}}
    )
