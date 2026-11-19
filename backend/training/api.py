import secrets
from time import monotonic
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, StringConstraints, field_validator
from sqlmodel import Session, select
from starlette.concurrency import run_in_threadpool

from backend.auth import find_session, session_key
from backend.models import TrainingMap
from backend.training.bots import NAMES, BotKind
from backend.training.executor import AlgorithmError, ExecutorUnavailable
from backend.training.maps import ArenaConfig, generate_map
from backend.training.protocol import SOURCE_LIMIT
from backend.training.runs import Run
from backend.training.state import (
    arena_view,
    build_observation,
    decode_state,
    encode_state,
)

RUN_TTL = 1800


class Draft(BaseModel):
    config: ArenaConfig = Field(default_factory=ArenaConfig)
    seed: int = Field(default_factory=lambda: secrets.randbits(53), ge=0, lt=2**53)
    cleared: bool = False


class Source(BaseModel):
    source: str = Field(max_length=SOURCE_LIMIT)

    @field_validator("source")
    @classmethod
    def size(cls, value):
        if len(value.encode()) > SOURCE_LIMIT:
            raise ValueError("Исходный код должен занимать до 8000 байт.")
        return value


Bots = Annotated[list[BotKind], Field(min_length=1, max_length=3)]


class MapInput(BaseModel):
    name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)
    ]
    draft: Draft
    bots: Bots


class RunInput(Source):
    draft: Draft | None = None
    map_id: int | None = None
    bots: Bots | None = None
    replace_run: str | None = Field(default=None, max_length=32)


class Step(BaseModel):
    expected_tick: int = Field(ge=0, le=1000)


def materialize(draft: Draft):
    try:
        return generate_map(draft.config, draft.seed, empty=draft.cleared)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


def map_view(data: dict, *, map_id=None, name=None):
    return {
        "id": map_id,
        "name": name,
        "draft": data["draft"],
        "bots": data.get("bots"),
        "arena": arena_view(decode_state(data["state"])),
    }


def make_router(engine, executor):
    router = APIRouter(prefix="/api/training")
    runs: dict[str, Run] = {}

    def owner(request: Request) -> int:
        with Session(engine) as db:
            identity = find_session(db, session_key(request.cookies.get("session", "")))
            if identity is None:
                raise HTTPException(401, "Требуется вход.")
            return identity[0].id

    TeamId = Annotated[int, Depends(owner)]

    def load_map(db, team_id, map_id):
        row = db.get(TrainingMap, map_id)
        if row is None or row.team_id != team_id:
            raise HTTPException(404, "Карта не найдена.")
        return row

    def load_run(team_id, run_id):
        run = runs.get(run_id)
        if (
            run is None
            or run.owner != team_id
            or (not run.lock.locked() and monotonic() - run.touched_at >= RUN_TTL)
        ):
            raise HTTPException(404, "Прогон не найден или истёк.")
        run.touched_at = monotonic()
        return run

    @router.post("/maps/generate")
    def generate(draft: Draft, _team: TeamId):
        draft = draft.model_copy(update={"cleared": False})
        return {"draft": draft, "arena": arena_view(materialize(draft))}

    @router.post("/maps/clear")
    def clear(draft: Draft, _team: TeamId):
        draft = draft.model_copy(update={"cleared": True})
        return {"draft": draft, "arena": arena_view(materialize(draft))}

    @router.get("/maps")
    def maps(team_id: TeamId):
        with Session(engine) as db:
            return [
                {"id": row.id, "name": row.name}
                for row in db.exec(
                    select(TrainingMap)
                    .where(TrainingMap.team_id == team_id)
                    .order_by(TrainingMap.id.desc())
                )
            ]

    @router.get("/maps/{map_id}")
    def get_map(map_id: int, team_id: TeamId):
        with Session(engine) as db:
            row = load_map(db, team_id, map_id)
            return map_view(row.data, map_id=row.id, name=row.name)

    @router.post("/maps", status_code=201)
    @router.put("/maps/{map_id}")
    def save_map(data: MapInput, team_id: TeamId, map_id: int | None = None):
        state = materialize(data.draft)
        if len(data.bots) != len(state.snakes) - 1:
            raise HTTPException(422, "Выберите бота для каждого соперника.")
        payload = {
            "format": 1,
            "draft": data.draft.model_dump(),
            "bots": data.bots,
            "state": encode_state(state),
        }
        with Session(engine) as db:
            if map_id is None:
                row = TrainingMap(team_id=team_id, name=data.name, data=payload)
                db.add(row)
            else:
                row = load_map(db, team_id, map_id)
                row.name, row.data = data.name, payload
            db.flush()
            result = map_view(payload, map_id=row.id, name=row.name)
            db.commit()
            return result

    @router.post("/validate")
    async def validate(data: Source, _team: TeamId):
        state = generate_map(ArenaConfig(), 0)
        try:
            await executor.decide(data.source, build_observation(state, 1), None)
        except AlgorithmError as exc:
            return {"ok": False, "error": exc.detail()}
        except ExecutorUnavailable as exc:
            raise HTTPException(503, str(exc)) from exc
        return {"ok": True, "error": None}

    def run_map(data, team_id):
        if data.map_id is not None:
            with Session(engine) as db:
                saved = load_map(db, team_id, data.map_id).data
                return decode_state(saved["state"]), data.bots or saved["bots"]
        if data.draft is None:
            raise HTTPException(422, "Сначала подготовьте карту.")
        return materialize(data.draft), data.bots

    @router.post("/runs", status_code=201)
    async def start(data: RunInput, team_id: TeamId):
        state, choices = await run_in_threadpool(run_map, data, team_id)
        if choices is None or len(choices) != len(state.snakes) - 1:
            raise HTTPException(422, "Выберите бота для каждого соперника.")
        try:
            await executor.ready()
        except ExecutorUnavailable as exc:
            raise HTTPException(503, str(exc)) from exc
        old = runs.get(data.replace_run) if data.replace_run else None
        if old is not None and old.owner == team_id:
            async with old.lock:
                runs.pop(old.id, None)
        expired = [
            id
            for id, run in runs.items()
            if not run.lock.locked() and monotonic() - run.touched_at >= RUN_TTL
        ]
        for id in expired:
            del runs[id]
        if len(runs) >= 128 or sum(run.owner == team_id for run in runs.values()) >= 4:
            raise HTTPException(
                429, "Слишком много активных прогонов. Завершите предыдущий."
            )
        bots = dict(zip(range(2, len(state.snakes) + 1), choices))
        state = state.model_copy(
            update={
                "snakes": tuple(
                    snake.model_copy(update={"name": NAMES[bots[snake.id]]})
                    if snake.id in bots
                    else snake
                    for snake in state.snakes
                )
            }
        )
        run = Run(uuid4().hex, team_id, state, data.source, bots)
        runs[run.id] = run
        return run.view()

    @router.get("/runs/{run_id}")
    async def read_run(run_id: str, team_id: TeamId):
        return load_run(team_id, run_id).view()

    @router.post("/runs/{run_id}/step")
    async def step(run_id: str, data: Step, team_id: TeamId):
        run = load_run(team_id, run_id)
        async with run.lock:
            load_run(team_id, run_id)
            if run.state.finished or run.state.tick != data.expected_tick:
                return JSONResponse(status_code=409, content=run.view())
            try:
                return await run.step(executor)
            except ExecutorUnavailable as exc:
                raise HTTPException(503, str(exc)) from exc

    @router.delete("/runs/{run_id}", status_code=204)
    async def stop(run_id: str, team_id: TeamId):
        run = runs.get(run_id)
        if run is not None and run.owner == team_id:
            async with run.lock:
                runs.pop(run_id, None)

    return router
