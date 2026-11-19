import asyncio
import json
from dataclasses import dataclass, field
from time import time
from typing import Literal

from anyio import CancelScope, create_task_group
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlmodel import Session
from starlette.concurrency import run_in_threadpool

from backend.auth import find_session, session_key
from backend.matches import (
    MatchError,
    Subscription,
    active_rounds,
    advance_round,
    load_online_turn,
    mutate,
    save_online_turn,
    snapshot,
)
from backend.training.executor import ExecutorUnavailable
from backend.training.runs import make_turn


class Message(BaseModel):
    type: Literal[
        "subscribe",
        "unsubscribe",
        "create_match",
        "join_match",
        "leave_match",
        "close_match",
        "start_preparation",
        "cancel_preparation",
        "submit_version",
        "rename_version",
        "select_version",
        "cancel_countdown",
    ]
    request_id: str = Field(pattern=r"^[a-fA-F0-9]{32}$")
    payload: dict


@dataclass(eq=False)
class Peer:
    team_id: int
    key: str
    expires: float
    view: Subscription | None = None
    subscription_id: str | None = None
    queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=32))
    closing: bool = False

    def send(self, message: dict):
        if self.closing:
            return
        if self.queue.full():
            self.close(1013)
        else:
            self.queue.put_nowait(message)

    def close(self, code: int):
        if self.closing:
            return
        self.closing = True
        while not self.queue.empty():
            self.queue.get_nowait()
        self.queue.put_nowait(code)


class MatchSocket:
    def __init__(self, engine: Engine, executor):
        self.engine = engine
        self.executor = executor
        self.router = APIRouter()
        self.router.add_api_websocket_route("/api/ws", self.connect)
        self.peers: set[Peer] = set()
        self.lock = asyncio.Lock()
        self.rounds: dict[int, asyncio.Task] = {}
        self.runner_waiting: set[int] = set()

    def load_rounds(self):
        with Session(self.engine) as db:
            return active_rounds(db)

    async def resume_rounds(self):
        for match_id, next_at in await run_in_threadpool(self.load_rounds):
            self.schedule(match_id, next_at)

    async def stop_rounds(self):
        async with self.lock:
            tasks = list(self.rounds.values())
            for task in tasks:
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    def schedule(self, match_id: int, next_at: float | None = None):
        previous = self.rounds.pop(match_id, None)
        self.runner_waiting.discard(match_id)
        if previous is not None:
            previous.cancel()
        if next_at is not None:
            self.rounds[match_id] = asyncio.create_task(
                self.run_round(match_id, next_at)
            )

    def in_db(self, operation, *args):
        with Session(self.engine) as db:
            return operation(db, *args)

    async def run_round(self, match_id: int, next_at: float):
        try:
            while next_at is not None:
                await asyncio.sleep(max(0, next_at - time()))
                try:
                    job = await run_in_threadpool(
                        self.in_db, load_online_turn, match_id
                    )
                    turn = None
                    if job is not None:
                        state, sources, memories = job
                        turn = await make_turn(
                            self.executor, state, sources, memories, online=True
                        )
                    async with self.lock:
                        if turn is None:
                            outcome = await run_in_threadpool(
                                self.in_db, advance_round, match_id
                            )
                        else:
                            outcome = await run_in_threadpool(
                                self.in_db, save_online_turn, match_id, state.tick, turn
                            )
                        next_at, changed, status_changed = outcome
                        if changed:
                            self.runner_waiting.discard(match_id)
                            await self.publish(match_id, include_list=status_changed)
                except ExecutorUnavailable:
                    async with self.lock:
                        if match_id not in self.runner_waiting:
                            self.runner_waiting.add(match_id)
                            await self.publish(match_id, include_list=False)
                    next_at = time() + 1
                except OperationalError:
                    next_at = time() + 1
        finally:
            if self.rounds.get(match_id) is asyncio.current_task():
                del self.rounds[match_id]
                self.runner_waiting.discard(match_id)

    def identify(self, key: str) -> Peer | None:
        with Session(self.engine) as db:
            identity = find_session(db, key)
            if identity is not None:
                team, session = identity
                assert team.id is not None
                return Peer(team.id, key, session.expires)
        return None

    async def revoke(self, key: str):
        async with self.lock:
            for peer in self.peers:
                if peer.key == key:
                    peer.close(1008)

    async def connect(self, socket: WebSocket):
        scheme = "https" if socket.url.scheme == "wss" else "http"
        origin = f"{scheme}://{socket.headers.get('host')}"
        token = socket.cookies.get("session")
        if socket.headers.get("origin") != origin:
            await socket.close(code=1008)
            return

        async with self.lock:
            peer = (
                await run_in_threadpool(self.identify, session_key(token))
                if token
                else None
            )
            await socket.accept()
            if peer is None:
                # Клиенту нужен код закрытия, чтобы открыть форму входа.
                await socket.close(code=1008)
                return
            self.peers.add(peer)

        try:
            async with create_task_group() as group:

                async def run_until_disconnected(operation):
                    try:
                        await operation(socket, peer)
                    except WebSocketDisconnect:
                        pass
                    finally:
                        group.cancel_scope.cancel()

                group.start_soon(run_until_disconnected, self.receive)
                group.start_soon(run_until_disconnected, self.deliver)
                group.start_soon(self.expire, peer)
        finally:
            self.peers.discard(peer)

    async def expire(self, peer: Peer):
        await asyncio.sleep(max(0, peer.expires - time()))
        peer.close(1008)

    async def deliver(self, socket: WebSocket, peer: Peer):
        while True:
            message = await peer.queue.get()
            if isinstance(message, int):
                await socket.close(code=message)
                return
            await socket.send_json(message)

    async def receive(self, socket: WebSocket, peer: Peer):
        while True:
            event = await socket.receive()
            if event["type"] == "websocket.disconnect":
                return
            raw = event.get("text")
            data = None
            try:
                if raw is None or len(raw) > 65_536:
                    raise ValueError
                data = json.loads(raw)
                message = Message.model_validate(data)
            except (ValueError, RecursionError):
                peer.send(
                    {
                        "type": "error",
                        "request_id": data.get("request_id")
                        if isinstance(data, dict)
                        and isinstance(data.get("request_id"), str)
                        else None,
                        "code": "invalid_request",
                        "message": "Некорректная команда.",
                    }
                )
                continue

            async with self.lock:
                if not peer.closing:
                    with CancelScope(shield=True):
                        await self.execute(peer, message)

    def view(self, db: Session, team_id: int, view: Subscription):
        data = snapshot(db, team_id, view)
        if view.view == "lobby":
            data["runner_waiting"] = view.match_id in self.runner_waiting
        return data

    def perform(self, peer: Peer, message: Message):
        with Session(self.engine) as db:
            if find_session(db, peer.key) is None:
                return None
            if message.type == "subscribe":
                view = Subscription.model_validate(message.payload)
                return self.view(db, peer.team_id, view), view, None
            if message.type == "unsubscribe":
                return {}, None, None
            return mutate(
                db, peer.team_id, message.type, message.payload, message.request_id
            )

    async def execute(self, peer: Peer, message: Message):
        try:
            outcome = await run_in_threadpool(self.perform, peer, message)
        except MatchError as error:
            response = {
                "type": "error",
                "request_id": message.request_id,
                "code": error.code,
                "message": str(error),
            }
            if error.match_id is not None:
                response["match_id"] = error.match_id
            peer.send(response)
            return
        except (ValidationError, OperationalError) as error:
            invalid = isinstance(error, ValidationError)
            peer.send(
                {
                    "type": "error",
                    "request_id": message.request_id,
                    "code": "invalid_request" if invalid else "unavailable",
                    "message": "Проверьте параметры матча."
                    if invalid
                    else "Сервер занят. Попробуйте ещё раз.",
                }
            )
            return

        if outcome is None:
            peer.close(1008)
            return

        value, detail, next_at = outcome
        if message.type in ("subscribe", "unsubscribe"):
            peer.view = detail
            peer.subscription_id = message.request_id if detail else None
            peer.send(
                {"type": "result", "request_id": message.request_id, "payload": {}}
            )
            if detail is not None:
                peer.send(
                    {
                        "type": "snapshot",
                        "subscription_id": peer.subscription_id,
                        "payload": value,
                    }
                )
            return

        peer.send(
            {
                "type": "result",
                "request_id": message.request_id,
                "payload": {"id": value},
            }
        )
        if detail:
            if message.type in (
                "start_preparation",
                "cancel_preparation",
                "cancel_countdown",
                "close_match",
            ):
                self.schedule(value, next_at)
            if message.type in ("submit_version", "select_version", "rename_version"):
                await self.publish(value, include_list=False, team_id=peer.team_id)
            else:
                await self.publish(value)

    def collect(self, peers: list[Peer]):
        messages = []
        with Session(self.engine) as db:
            for peer in peers:
                assert peer.view is not None
                try:
                    if find_session(db, peer.key) is None:
                        messages.append((peer, 1008))
                        continue
                    messages.append(
                        (
                            peer,
                            {
                                "type": "snapshot",
                                "subscription_id": peer.subscription_id,
                                "payload": self.view(db, peer.team_id, peer.view),
                            },
                        )
                    )
                except MatchError as error:
                    messages.append(
                        (
                            peer,
                            {
                                "type": "subscription_end",
                                "subscription_id": peer.subscription_id,
                                "code": error.code,
                                "message": str(error),
                            },
                        )
                    )
        return messages

    async def publish(
        self, match_id: int, *, include_list: bool = True, team_id: int | None = None
    ):
        targets = [
            peer
            for peer in self.peers
            if not peer.closing
            and (team_id is None or peer.team_id == team_id)
            and peer.view is not None
            and (
                (include_list and peer.view.view == "list")
                or peer.view.match_id == match_id
            )
        ]
        try:
            messages = await run_in_threadpool(self.collect, targets)
        except OperationalError:
            for peer in targets:
                peer.close(1013)
            return
        for peer, message in messages:
            if isinstance(message, int):
                peer.close(message)
                continue
            peer.send(message)
            if message["type"] == "subscription_end":
                peer.view = None
                peer.subscription_id = None
