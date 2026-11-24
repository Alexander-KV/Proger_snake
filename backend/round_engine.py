from collections import Counter
from random import Random
from typing import Literal

from pydantic import BaseModel, Field

Cell = tuple[int, int]
Direction = Literal["UP", "RIGHT", "DOWN", "LEFT"]
DIRECTIONS: tuple[Direction, ...] = ("UP", "RIGHT", "DOWN", "LEFT")
OFFSETS = dict(zip(DIRECTIONS, ((0, -1), (1, 0), (0, 1), (-1, 0))))
TICK_SECONDS = 0.25
MAX_TICKS = 240


class Snake(BaseModel):
    team_id: int
    name: str
    strategy: Literal["food", "space"]
    body: list[Cell]
    direction: Direction
    score: int = 0
    eliminated_at: int | None = None


class RoundState(BaseModel):
    tick: int = 0
    snakes: list[Snake]
    food: Cell | None
    winner_ids: list[int] = Field(default_factory=list)


def move(cell: Cell, direction: Direction) -> Cell:
    dx, dy = OFFSETS[direction]
    return cell[0] + dx, cell[1] + dy


def inside(cell: Cell, size: int) -> bool:
    return 0 <= cell[0] < size and 0 <= cell[1] < size


def place_food(size: int, occupied: set[Cell], seed: int) -> Cell | None:
    free = [(x, y) for y in range(size) for x in range(size) if (x, y) not in occupied]
    return Random(seed).choice(free) if free else None


def create_round(
    size: int, match_id: int, players: list[tuple[int, str]]
) -> RoundState:
    low, high = size // 4, size - 1 - size // 4
    positions: list[tuple[Cell, Direction]] = [
        ((low, low), "RIGHT"),
        ((high, high), "LEFT"),
        ((high, low), "DOWN"),
        ((low, high), "UP"),
    ]
    snakes = []
    for index, (team_id, name) in enumerate(players):
        head, direction = positions[index]
        reverse = DIRECTIONS[(DIRECTIONS.index(direction) + 2) % len(DIRECTIONS)]
        neck = move(head, reverse)
        snakes.append(
            Snake(
                team_id=team_id,
                name=name,
                strategy="food" if index % 2 == 0 else "space",
                body=[head, neck, move(neck, reverse)],
                direction=direction,
            )
        )
    occupied = {cell for snake in snakes for cell in snake.body}
    return RoundState(snakes=snakes, food=place_food(size, occupied, match_id))


def directions_from(direction: Direction) -> tuple[Direction, Direction, Direction]:
    current = DIRECTIONS.index(direction)
    return (
        direction,
        DIRECTIONS[(current + 1) % 4],
        DIRECTIONS[(current - 1) % 4],
    )


def choose_direction(
    snake: Snake,
    size: int,
    occupied: set[Cell],
    food: Cell | None,
    contested: set[Cell],
) -> Direction:
    def preference(direction: Direction):
        target = move(snake.body[0], direction)
        if not inside(target, size) or target in occupied:
            return (-1, 0, 0)
        distance = abs(target[0] - food[0]) + abs(target[1] - food[1]) if food else 0
        if snake.strategy == "food":
            return (0, 0, -distance)

        # Оцениваем, сколько клеток доступно из новой позиции.
        visited = {target}
        frontier = [target]
        while frontier:
            cell = frontier.pop()
            for step in DIRECTIONS:
                adjacent = move(cell, step)
                if (
                    inside(adjacent, size)
                    and adjacent not in occupied
                    and adjacent not in visited
                ):
                    visited.add(adjacent)
                    frontier.append(adjacent)
        return (int(target not in contested), len(visited), -distance)

    return max(directions_from(snake.direction), key=preference)


def advance(state: RoundState, size: int, match_id: int) -> bool:
    state.tick += 1
    active = [snake for snake in state.snakes if snake.eliminated_at is None]
    occupied = {cell for snake in active for cell in snake.body}
    directions = []
    for snake in active:
        contested = {
            move(other.body[0], direction)
            for other in active
            if other is not snake
            for direction in directions_from(other.direction)
        }
        directions.append(
            choose_direction(snake, size, occupied, state.food, contested)
        )
    heads = [
        move(snake.body[0], direction) for snake, direction in zip(active, directions)
    ]
    head_counts = Counter(heads)
    # Освобождаются хвосты змеек, которые на этом тике не пытаются съесть еду.
    bodies = {
        cell
        for snake, head in zip(active, heads)
        for cell in (snake.body if head == state.food else snake.body[:-1])
    }
    for snake, direction, head in zip(active, directions, heads):
        if not inside(head, size) or head in bodies or head_counts[head] > 1:
            snake.eliminated_at = state.tick
            snake.body = []
            continue
        snake.direction = direction
        snake.body.insert(0, head)
        if head == state.food:
            snake.score += 1
            state.food = None
        else:
            snake.body.pop()

    survivors = [snake for snake in active if snake.eliminated_at is None]
    if state.food is None:
        occupied = {cell for snake in survivors for cell in snake.body}
        state.food = place_food(size, occupied, match_id * (MAX_TICKS + 1) + state.tick)
    if len(survivors) > 1 and state.tick < MAX_TICKS and state.food is not None:
        return False

    contenders = survivors or active
    best_score = max(snake.score for snake in contenders)
    state.winner_ids = [
        snake.team_id for snake in contenders if snake.score == best_score
    ]
    return True
