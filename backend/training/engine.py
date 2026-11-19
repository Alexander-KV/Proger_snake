from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from itertools import combinations
from random import Random

from backend.training.geometry import Cell, Direction, move
from backend.training.state import SHIELD_TICKS, ArenaState, Snake


@dataclass(frozen=True)
class Intent:
    snake: Snake
    direction: Direction
    target: Cell
    complete: bool
    released: int
    poison_death: bool

    def occupied(self, dead: bool) -> tuple[Cell, ...]:
        return (
            self.snake.body[: -self.released]
            if self.released and not dead
            else self.snake.body
        )


def intent(state: ArenaState, snake: Snake, choice: Direction) -> Intent:
    direction = choice if choice in snake.allowed() else snake.direction
    target = snake.target or move(snake.body[0], direction)
    shield = snake.shielded(state.tick)
    complete = snake.target is not None or target not in state.water or shield
    poisoned = complete and target in state.poison and not shield
    poison_death = poisoned and snake.length == 2
    released = (
        0 if not complete or target in state.food or poison_death else 1 + poisoned
    )
    return Intent(snake, direction, target, complete, released, poison_death)


def collisions(state: ArenaState, intents: dict[int, Intent]) -> set[int]:
    targets = Counter(turn.target for turn in intents.values())
    dead = {
        id
        for id, turn in intents.items()
        if targets[turn.target] > 1
        or not state.inside(turn.target)
        or turn.target in state.obstacles
    }
    for (left, a), (right, b) in combinations(intents.items(), 2):
        if a.target == b.snake.body[0] and b.target == a.snake.body[0]:
            dead.update((left, right))
    while True:
        occupied = {
            cell for id, turn in intents.items() for cell in turn.occupied(id in dead)
        }
        hits = {id for id, turn in intents.items() if turn.target in occupied}
        if hits <= dead:
            return dead
        dead.update(hits)


def replenish(state: ArenaState) -> ArenaState:
    if not state.food_targets or state.finished:
        return state
    food = state.food.copy()
    blocked = state.obstacles | state.water | state.poison | state.shields | food.keys()
    for snake in state.snakes:
        blocked.update(snake.body)
        if snake.target is not None:
            blocked.add(snake.target)
    free = [
        (x, y)
        for y in range(state.height)
        for x in range(state.width)
        if (x, y) not in blocked
    ]
    Random(f"{state.seed}:{state.tick}").shuffle(free)
    counts = Counter(food.values())
    for kind, amount in sorted(state.food_targets.items()):
        for _ in range(min(amount - counts[kind], len(free))):
            food[free.pop()] = kind
    return state.model_copy(update={"food": food})


def advance(state: ArenaState, directions: Mapping[int, Direction]) -> ArenaState:
    if state.finished:
        return state
    turns = {
        s.id: intent(state, s, directions.get(s.id, s.direction))
        for s in state.snakes
        if s.alive
    }
    dead = collisions(state, turns)
    tick = state.tick + 1
    food, poison, shields = state.food.copy(), set(state.poison), set(state.shields)
    snakes = []
    for snake in sorted(state.snakes, key=lambda s: s.id):
        turn = turns.get(snake.id)
        if turn is None:
            snakes.append(snake)
            continue
        if snake.id in dead or turn.poison_death:
            if snake.id not in dead:
                poison.remove(turn.target)
            snakes.append(
                snake.model_copy(
                    update={
                        "body": (),
                        "target": None,
                        "dead_length": snake.length,
                        "shield_until": 0,
                    }
                )
            )
            continue
        shield = snake.shield_until if snake.shielded(tick) else 0
        if not turn.complete:
            snakes.append(
                snake.model_copy(
                    update={
                        "direction": turn.direction,
                        "target": turn.target,
                        "shield_until": shield,
                    }
                )
            )
            continue
        kind = food.pop(turn.target, None)
        if turn.target in poison:
            poison.remove(turn.target)
            shield = 0
        if turn.target in shields:
            shields.remove(turn.target)
            shield = tick + SHIELD_TICKS
        snakes.append(
            snake.model_copy(
                update={
                    "body": (turn.target, *turn.occupied(False)),
                    "direction": turn.direction,
                    "target": None,
                    "shield_until": shield,
                    "score": snake.score + {None: 0, "normal": 10, "gold": 30}[kind],
                }
            )
        )
    return replenish(
        state.model_copy(
            update={
                "tick": tick,
                "snakes": tuple(snakes),
                "food": food,
                "poison": frozenset(poison),
                "shields": frozenset(shields),
            }
        )
    )
