from collections import Counter
from random import Random
from typing import TypedDict

TICK_SECONDS = 0.25
MAX_TICKS = 300
START_DIRECTIONS = ((1, 0), (-1, 0), (0, 1), (0, -1))

Cell = tuple[int, int]


class Snake(TypedDict):
    team_id: int
    name: str
    body: list[Cell]
    direction: Cell
    alive: bool
    score: int


class Game(TypedDict):
    tick: int
    snakes: list[Snake]
    food: Cell | None
    winners: list[int]


def move(cell: Cell, direction: Cell) -> Cell:
    return cell[0] + direction[0], cell[1] + direction[1]


def inside(cell: Cell, size: int) -> bool:
    return all(0 <= axis < size for axis in cell)


def place_food(size: int, snakes: list[Snake], seed: int) -> Cell | None:
    occupied = {cell for snake in snakes if snake["alive"] for cell in snake["body"]}
    free = [(x, y) for y in range(size) for x in range(size) if (x, y) not in occupied]
    return Random(seed).choice(free) if free else None


def new_game(size: int, players: list[tuple[int, str]], seed: int) -> Game:
    low, high = size // 4, size - 1 - size // 4
    corners = ((low, low), (high, high), (high, low), (low, high))
    snakes: list[Snake] = []
    for index, ((team_id, name), head) in enumerate(zip(players, corners)):
        direction = START_DIRECTIONS[index]
        tail = move(head, (-direction[0], -direction[1]))
        snakes.append(
            Snake(
                team_id=team_id,
                name=name,
                body=[head, tail],
                direction=direction,
                alive=True,
                score=0,
            )
        )
    return Game(tick=0, snakes=snakes, food=place_food(size, snakes, seed), winners=[])


def choose_direction(
    snake: Snake,
    food: Cell | None,
    occupied: set[Cell],
    size: int,
    avoid_dead_ends: bool,
) -> Cell:
    head = snake["body"][0]
    dx, dy = snake["direction"]
    options = (snake["direction"], (-dy, dx), (dy, -dx))
    safe = [
        direction
        for direction in options
        if inside(target := move(head, direction), size) and target not in occupied
    ]
    if not safe:
        return snake["direction"]

    def cost(direction: Cell) -> int:
        x, y = target = move(head, direction)
        distance = abs(x - food[0]) + abs(y - food[1]) if food is not None else 0
        if not avoid_dead_ends:
            return distance

        next_dx, next_dy = direction
        exits = (direction, (-next_dy, next_dx), (next_dy, -next_dx))
        open_exits = sum(
            inside(cell := move(target, exit_direction), size) and cell not in occupied
            for exit_direction in exits
        )
        return distance + (3 - open_exits) * 2

    return min(safe, key=cost)


def advance(game: Game, size: int, seed: int) -> tuple[Game, bool]:
    snakes = game["snakes"]
    food = game["food"]
    occupied = {cell for snake in snakes if snake["alive"] for cell in snake["body"]}
    directions = {
        index: choose_direction(snake, food, occupied, size, index % 2 == 1)
        for index, snake in enumerate(snakes)
        if snake["alive"]
    }
    heads = {
        index: move(snakes[index]["body"][0], direction)
        for index, direction in directions.items()
    }

    # Занятость рассчитывается до тика. Все головы оцениваются одновременно.
    head_counts = Counter(heads.values())
    advanced = snakes.copy()
    ate = False
    for index, head in heads.items():
        snake = snakes[index]
        if not inside(head, size) or head in occupied or head_counts[head] > 1:
            advanced[index] = {**snake, "alive": False, "body": []}
            continue
        grows = head == food
        body = snake["body"] if grows else snake["body"][:-1]
        advanced[index] = {
            **snake,
            "direction": directions[index],
            "body": [head, *body],
            "score": snake["score"] + int(grows),
        }
        ate |= grows

    tick = game["tick"] + 1
    alive = [snake for snake in advanced if snake["alive"]]
    if ate:
        food = place_food(size, advanced, seed + tick)
    finished = len(alive) <= 1 or tick >= MAX_TICKS or food is None
    winners = []
    if finished:
        # Выжившие имеют приоритет. При равных очках победителей несколько.
        eligible = alive or advanced
        score = max(snake["score"] for snake in eligible)
        winners = [snake["team_id"] for snake in eligible if snake["score"] == score]
    return Game(tick=tick, snakes=advanced, food=food, winners=winners), finished


def restore_game(state: dict) -> Game:
    # После SQLite JSON координаты приходят списками.
    snakes = [
        {
            **snake,
            "direction": tuple(snake["direction"]),
            "body": [tuple(cell) for cell in snake["body"]],
        }
        for snake in state["snakes"]
    ]
    return Game(
        tick=state["tick"],
        snakes=snakes,
        food=tuple(state["food"]) if state["food"] is not None else None,
        winners=state["winners"],
    )
