import asyncio
import json
import os
from pathlib import Path

from backend.training.bots import BotKind
from backend.training.protocol import (
    REQUEST_LIMIT,
    RESPONSE_LIMIT,
    encode,
    validate_result,
)

LOCAL_SETTINGS = Path(__file__).resolve().parents[2] / ".env.local"
RUNNER_KEYS = {"SNAKE_RUNNER_TOKEN", "SNAKE_RUNNER_PORT"}


def local_settings() -> dict[str, str]:
    try:
        lines = LOCAL_SETTINGS.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return {}
    settings = {}
    for line in lines:
        key, separator, value = line.partition("=")
        key = key.strip()
        if separator and key in RUNNER_KEYS:
            settings[key] = value.strip()
    return settings


class AlgorithmError(Exception):
    def __init__(self, code: str, message: str, line: int | None = None):
        super().__init__(message)
        self.code = code
        self.line = line

    def detail(self) -> dict:
        return {"code": self.code, "message": str(self), "line": self.line}


class ExecutorUnavailable(Exception):
    def __init__(self):
        super().__init__("Исполнитель Python недоступен. Повторите попытку.")


class Executor:
    def __init__(self, port: int | None = None, token: str | None = None):
        settings = local_settings() if port is None or token is None else {}
        if port is None:
            port = int(
                os.getenv("SNAKE_RUNNER_PORT")
                or settings.get("SNAKE_RUNNER_PORT")
                or "8765"
            )
        if token is None:
            token = os.getenv("SNAKE_RUNNER_TOKEN") or settings.get(
                "SNAKE_RUNNER_TOKEN", ""
            )
        self.port = port
        self.token = token

    async def request(self, payload: dict) -> dict:
        writer = None
        try:
            data = encode({**payload, "token": self.token})
            if len(data) >= REQUEST_LIMIT:
                raise ValueError
            async with asyncio.timeout(4):
                reader, writer = await asyncio.open_connection(
                    "127.0.0.1", self.port, limit=RESPONSE_LIMIT
                )
                writer.write(data + b"\n")
                await writer.drain()
                response = json.loads(await reader.readline())
            if type(response) is not dict:
                raise ValueError
            return response
        except (OSError, TimeoutError, ValueError, RecursionError) as exc:
            raise ExecutorUnavailable from exc
        finally:
            if writer is not None:
                writer.close()

    async def ready(self):
        if await self.request({"ping": True}) != {"ready": True}:
            raise ExecutorUnavailable

    async def decide(self, source: str, state: dict, memory, *, online=False):
        return await self.run(state, source=source, memory=memory, online=online)

    async def bot(self, bot: BotKind, state: dict, seed: int):
        direction, _ = await self.run(state, bot=bot, seed=seed)
        return direction

    async def run(self, state: dict, **options):
        response = await self.request(dict(state=state, **options))
        if "error" not in response:
            response = validate_result(response, state["self"]["allowed_directions"])
        if "error" in response:
            detail = response["error"]
            if not isinstance(detail, dict) or detail.get("code") == "unavailable":
                raise ExecutorUnavailable
            if not isinstance(detail.get("code"), str) or not isinstance(
                detail.get("message"), str
            ):
                raise ExecutorUnavailable
            line = detail.get("line")
            raise AlgorithmError(
                detail["code"],
                detail["message"][:400],
                line if type(line) is int and 0 < line <= 8000 else None,
            )
        return response["direction"], response["memory"]
