from collections import deque
from random import Random
from typing import Literal

from backend.training.geometry import OPPOSITE, VECTORS, Cell, Direction, move

BotKind = Literal["random", "hunter", "pathfinding", "survival"]
NAMES = {
    "random": "Random Bot",
    "hunter": "Food Hunter",
    "pathfinding": "Pathfinding Bot",
    "survival": "Survival Bot",
}


def explore(
    start: Cell, direction: Direction, safe, food: set[Cell]
) -> tuple[int, int]:
    queue = deque([(start, direction, 1)])
    visited = {(start, direction)}
    cells = {start}
    distance = 100_000
    while queue:
        cell, previous, steps = queue.popleft()
        if cell in food:
            distance = min(distance, steps)
        for choice in VECTORS:
            if choice == OPPOSITE[previous]:
                continue
            target = move(cell, choice)
            if (target, choice) not in visited and safe(target):
                visited.add((target, choice))
                cells.add(target)
                queue.append((target, choice, steps + 1))
    return distance, len(cells)


def decide_bot(bot: BotKind, state: dict, seed: int) -> Direction:
    own = state["self"]
    allowed = own["allowed_directions"].copy()
    if len(allowed) == 1:
        return allowed[0]
    Random(f"{seed}:{state['tick']}:{own['id']}").shuffle(allowed)
    if bot == "random":
        return allowed[0]

    blocked = {tuple(cell) for cell in state["obstacles"]}
    if not own["effects"]["shield_ticks"]:
        blocked.update(map(tuple, state["poison"]))
    for snake in [own, *state["opponents"]]:
        blocked.update(map(tuple, snake["body"]))
        if (target := snake["movement"]["target"]) is not None:
            blocked.add(tuple(target))
    head = tuple(own["body"][0])
    food = {tuple(item["cell"]) for item in state["food"]}

    def safe(cell: Cell) -> bool:
        return (
            0 <= cell[0] < state["width"]
            and 0 <= cell[1] < state["height"]
            and cell not in blocked
        )

    def rank(direction: Direction):
        target = move(head, direction)
        if bot == "hunter":
            return min(
                (abs(target[0] - x) + abs(target[1] - y) for x, y in food), default=0
            )
        distance, area = explore(target, direction, safe, food)
        return (-area, distance) if bot == "survival" else (distance, -area)

    return min(
        (direction for direction in allowed if safe(move(head, direction))),
        key=rank,
        default=own["direction"],
    )
