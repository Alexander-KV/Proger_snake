import asyncio
from dataclasses import dataclass, field
from time import monotonic

from backend.training.bots import BotKind
from backend.training.engine import advance
from backend.training.executor import AlgorithmError, Executor
from backend.training.state import ArenaState, arena_view, build_observation


async def make_turn(
    executor: Executor,
    state: ArenaState,
    sources: dict[int, str],
    memories: dict,
    bots: dict[int, BotKind] | None = None,
    *,
    online=False,
):
    async def decide(snake):
        obs = build_observation(state, snake.id)
        memory = memories.get(str(snake.id))
        try:
            if bots and snake.id in bots:
                direction = await executor.bot(bots[snake.id], obs, state.seed)
                return snake.id, direction, None, None
            direction, memory = await executor.decide(
                sources[snake.id], obs, memory, online=online
            )
            return snake.id, direction, memory, None
        except AlgorithmError as exc:
            return snake.id, snake.direction, memory, exc.detail()

    decisions = await asyncio.gather(
        *(decide(snake) for snake in state.snakes if snake.alive),
        return_exceptions=True,
    )
    directions, next_memories, errors = {}, {}, {}
    for decision in decisions:
        if isinstance(decision, BaseException):
            raise decision
        id, direction, memory, error = decision
        directions[id] = direction
        next_memories[str(id)] = memory
        if error is not None:
            errors[str(id)] = {**error, "tick": state.tick}
    return advance(state, directions), next_memories, errors


@dataclass
class Run:
    id: str
    owner: int
    state: ArenaState
    source: str
    bots: dict[int, BotKind]
    memories: dict = field(default_factory=dict)
    touched_at: float = field(default_factory=monotonic)
    error: dict | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def view(self):
        return {"id": self.id, "arena": arena_view(self.state), "error": self.error}

    async def step(self, executor):
        self.state, self.memories, errors = await make_turn(
            executor, self.state, {1: self.source}, self.memories, self.bots
        )
        if "1" in errors:
            self.error = errors["1"]
        return self.view()
