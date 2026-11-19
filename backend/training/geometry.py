from typing import Literal

Cell = tuple[int, int]
Direction = Literal["UP", "DOWN", "LEFT", "RIGHT"]
VECTORS: dict[Direction, Cell] = {
    "UP": (0, -1),
    "DOWN": (0, 1),
    "LEFT": (-1, 0),
    "RIGHT": (1, 0),
}
OPPOSITE: dict[Direction, Direction] = {
    "UP": "DOWN",
    "DOWN": "UP",
    "LEFT": "RIGHT",
    "RIGHT": "LEFT",
}


def move(cell: Cell, direction: Direction) -> Cell:
    dx, dy = VECTORS[direction]
    return cell[0] + dx, cell[1] + dy
