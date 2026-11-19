import asyncio
import hmac
import json
import os
import signal
import sys

from backend.training.bots import NAMES
from backend.training.protocol import (
    REQUEST_LIMIT,
    RESPONSE_LIMIT,
    SOURCE_LIMIT,
    encode,
    error,
    validate_result,
)

TIMEOUT = 0.100
UNAVAILABLE = error("unavailable", "Исполнитель Python занят или недоступен.")
WORKER = "import sys; sys.path.insert(0, '/app'); from backend.training.worker import main; main()"


WORKER_ERRORS = frozenset(
    {
        "syntax",
        "missing_decide",
        "runtime",
        "restricted",
        "resource",
        "result",
        "direction",
        "memory",
    }
)


def parse_worker_response(raw: bytes, allowed):
    result = json.loads(raw)
    if type(result) is dict and "error" in result:
        detail = result["error"]
        if type(detail) is dict:
            code, message, line = (
                detail.get("code"),
                detail.get("message"),
                detail.get("line"),
            )
            if type(code) is str and code in WORKER_ERRORS and type(message) is str:
                return error(
                    code,
                    message[:400],
                    line if type(line) is int and 0 < line <= SOURCE_LIMIT else None,
                )
        return error("result", "Алгоритм вернул некорректный результат.")
    return validate_result(result, allowed)


async def execute(job: dict):
    data = encode(job)
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-I",
        "-S",
        "-B",
        "-c",
        WORKER,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        limit=RESPONSE_LIMIT,
        env={"PYTHONUTF8": "1"},
    )
    try:
        async with asyncio.timeout(1):
            process.stdin.write(data + b"\n")
            await process.stdin.drain()
            process.stdin.close()
            if await process.stdout.readline() != b"ready\n":
                return UNAVAILABLE
        try:
            async with asyncio.timeout(TIMEOUT):
                response = await process.stdout.readline()
                status = await process.wait()
        except TimeoutError:
            return error("timeout", "Алгоритм не уложился в 100 мс.")
        if status == -signal.SIGSYS:
            return error(
                "restricted", "Алгоритм запросил недоступную системную операцию."
            )
        if status != 0 or not response:
            return error("runtime", "Выполнение алгоритма прервано.")
        return parse_worker_response(
            response, job["state"]["self"]["allowed_directions"]
        )
    except (ValueError, RecursionError, BrokenPipeError):
        return error(
            "resource", "Алгоритм вернул слишком большой или некорректный результат."
        )
    except (TimeoutError, OSError):
        return UNAVAILABLE
    finally:
        if process.returncode is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
        # Ограничиваем чтение после остановки, даже при переполненном stdout.
        await process.stdout.read()
        await process.wait()


class Runner:
    def __init__(self, token):
        self.token = token
        self.training = asyncio.Semaphore(2)
        self.total = asyncio.Semaphore(4)
        self.pending = 0
        self.pending_training = 0

    async def decide(self, job: dict, online: bool):
        if self.pending >= 32 or (not online and self.pending_training >= 8):
            return UNAVAILABLE
        self.pending += 1
        self.pending_training += not online
        try:
            async with asyncio.timeout(2):
                if online:
                    async with self.total:
                        return await execute(job)
                async with self.training, self.total:
                    return await execute(job)
        except (TimeoutError, OSError):
            return UNAVAILABLE
        finally:
            self.pending -= 1
            self.pending_training -= not online

    async def handle(self, reader, writer):
        try:
            async with asyncio.timeout(1):
                data = json.loads(await reader.readline())
            token = data.pop("token", None)
            if type(token) is not str or not hmac.compare_digest(
                token.encode(), self.token
            ):
                return
            source = data.get("source")
            if data.get("ping") is True:
                reply = {"ready": True}
            elif (
                data.get("bot") in NAMES
                or type(source) is str
                and len(source.encode()) <= SOURCE_LIMIT
            ):
                reply = await self.decide(data, data.get("online") is True)
            else:
                reply = error("source", "Исходный код должен занимать до 8000 байт.")
            writer.write(encode(reply) + b"\n")
            await writer.drain()
        except (
            TimeoutError,
            ValueError,
            TypeError,
            AttributeError,
            RecursionError,
            OSError,
        ):
            pass
        finally:
            writer.close()


async def main():
    token = os.environ.get("SNAKE_RUNNER_TOKEN", "").encode()
    if len(token) < 32:
        raise RuntimeError("Задайте SNAKE_RUNNER_TOKEN длиной от 32 байт.")
    check = await execute(
        {
            "source": "def decide(state, memory): return {'direction': 'RIGHT', 'memory': None}",
            "state": {"self": {"allowed_directions": ["RIGHT"]}},
            "memory": None,
        }
    )
    if check != {"direction": "RIGHT", "memory": None}:
        raise RuntimeError(f"Проверка изоляции Python не пройдена: {check}")
    server = await asyncio.start_server(
        Runner(token).handle, "0.0.0.0", 8765, limit=REQUEST_LIMIT
    )
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
