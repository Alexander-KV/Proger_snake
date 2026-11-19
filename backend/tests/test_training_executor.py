import asyncio
import json
import os

import pytest

from backend.training.executor import AlgorithmError, Executor, ExecutorUnavailable
from backend.training.maps import ArenaConfig, generate_map
from backend.training.state import build_observation


def test_executor_preserves_errors_and_revalidates_decisions(monkeypatch):
    replies = iter(
        [
            {
                "error": {
                    "code": "syntax",
                    "message": "Синтаксическая ошибка",
                    "line": 2,
                }
            },
            {"direction": "LEFT", "memory": None},
            {"direction": "UP", "memory": {"path": [[3, 2]]}},
        ]
    )
    inputs = []

    class Writer:
        def write(self, data):
            inputs.append(json.loads(data))

        async def drain(self):
            return None

        def close(self):
            return None

    async def connect(_host, _port, *, limit):
        reply = next(replies, None)
        if reply is None:
            raise ConnectionRefusedError
        reader = asyncio.StreamReader(limit)
        reader.feed_data(json.dumps(reply).encode() + b"\n")
        reader.feed_eof()
        return reader, Writer()

    monkeypatch.setattr("backend.training.executor.asyncio.open_connection", connect)

    async def scenario():
        executor = Executor(8765, "test-token")
        state = {"self": {"allowed_directions": ["UP"]}}
        for code in ("syntax", "direction"):
            with pytest.raises(AlgorithmError) as error:
                await executor.decide("code", state, None)
            assert error.value.code == code
            if code == "syntax":
                assert error.value.line == 2
        assert await executor.decide("code", state, [1], online=True) == (
            "UP",
            {"path": [[3, 2]]},
        )
        assert inputs[-1]["memory"] == [1] and inputs[-1]["online"] is True
        with pytest.raises(ExecutorUnavailable):
            await executor.decide("code", state, None)

    asyncio.run(scenario())


@pytest.mark.skipif(
    not os.environ.get("SNAKE_RUNNER_TOKEN"),
    reason="Нужен работающий контейнер исполнителя",
)
def test_container_enforces_contract_deadline_and_isolation():
    async def scenario():
        executor = Executor()
        await executor.ready()
        board = generate_map(ArenaConfig(width=32, height=32, snake_count=4), 11)
        observations = [build_observation(board, id) for id in range(1, 5)]
        bots = ("random", "hunter", "pathfinding", "survival")
        directions = await asyncio.gather(
            *(
                executor.bot(bot, observation, 11)
                for bot, observation in zip(bots, observations)
            )
        )
        for direction, observation in zip(directions, observations):
            assert direction in observation["self"]["allowed_directions"]
        observation = {"self": {"allowed_directions": ["UP"]}}
        correct = """from collections import deque
def decide(state, memory):
    path = deque(memory or ())
    path.append([4, 5])
    return {"direction": "UP", "memory": list(path)}
"""
        for source, category, line in (
            ("def decide(", "syntax", 1),
            ("pass", "missing_decide", None),
            ("def decide(state, memory):\n    return unknown", "runtime", 2),
            ("def decide(state, memory): return None", "result", None),
            (
                "def decide(state, memory): return {'direction': 'DOWN', 'memory': None}",
                "direction",
                None,
            ),
            (
                "def decide(state, memory): return {'direction': 'UP', 'memory': {1, 2}}",
                "memory",
                None,
            ),
            (
                "def decide(state, memory): return {'direction': 'UP', 'memory': 'x' * 17000}",
                "memory",
                None,
            ),
            ("def decide(state, memory): return open('/nonexistent')", "restricted", 1),
            (
                "def decide(state, memory): return bytearray(120_000_000)",
                "resource",
                None,
            ),
        ):
            with pytest.raises(AlgorithmError) as exc:
                await executor.decide(source, observation, None)
            assert (exc.value.code, exc.value.line) == (category, line)
        results = await asyncio.gather(
            executor.decide(
                "def decide(state, memory):\n    while True: pass", observation, None
            ),
            executor.decide(correct, observation, None, online=True),
            return_exceptions=True,
        )
        assert isinstance(results[0], AlgorithmError)
        assert results[0].code == "timeout"
        assert results[1] == ("UP", [[4, 5]])
        assert await executor.decide(correct, observation, results[1][1]) == (
            "UP",
            [[4, 5], [4, 5]],
        )
        assert await executor.decide(correct, observation, None) == ("UP", [[4, 5]])

    asyncio.run(scenario())


def test_only_parent_can_signal_service_unavailability():
    from backend.training.runner import parse_worker_response

    for code in ("unavailable", "unknown"):
        response = parse_worker_response(
            json.dumps(
                {"error": {"code": code, "message": "fixture", "line": None}}
            ).encode(),
            ["UP"],
        )
        assert response["error"]["code"] == "result"
    assert parse_worker_response(b'{"direction":"UP","memory":["a"]}', ["UP"]) == {
        "direction": "UP",
        "memory": ["a"],
    }


def test_executor_reads_local_settings_and_prefers_environment(tmp_path, monkeypatch):
    local = tmp_path / ".env.local"
    local.write_text("SNAKE_RUNNER_TOKEN=fixture-local\nSNAKE_RUNNER_PORT=8766\n")
    monkeypatch.setattr(
        "backend.training.executor.LOCAL_SETTINGS", local, raising=False
    )
    monkeypatch.delenv("SNAKE_RUNNER_TOKEN", raising=False)
    monkeypatch.delenv("SNAKE_RUNNER_PORT", raising=False)

    executor = Executor()
    assert executor.token == "fixture-local"
    assert executor.port == 8766

    monkeypatch.setenv("SNAKE_RUNNER_TOKEN", "fixture-env")
    monkeypatch.setenv("SNAKE_RUNNER_PORT", "8767")
    executor = Executor()
    assert executor.token == "fixture-env"
    assert executor.port == 8767

    executor = Executor(8768, "fixture-explicit")
    assert executor.token == "fixture-explicit"
    assert executor.port == 8768
