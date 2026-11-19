from time import time
from uuid import uuid4

import pytest
from sqlmodel import Session, SQLModel, create_engine

from backend.matches import MatchError, Subscription, advance_round, mutate, snapshot
from backend.models import MatchRound, Team
from backend.training.state import decode_state


@pytest.mark.parametrize("with_second_submission", [True, False])
def test_preparation_cutoff_versions_and_results_access(
    tmp_path, monkeypatch, with_second_submission
):
    engine = create_engine(f"sqlite:///{tmp_path / 'match.db'}")
    SQLModel.metadata.create_all(engine)
    now = time()
    monkeypatch.setattr("backend.matches.time", lambda: now)

    with Session(engine) as db:
        for id in range(1, 4):
            db.add(
                Team(
                    id=id,
                    username=str(id),
                    name=f"Команда {id}",
                    password_hash="fixture",
                )
            )
        db.commit()

    def act(id, action, **data):
        key = data.pop("key", None) or uuid4().hex
        with Session(engine) as db:
            return mutate(db, id, action, data, key)

    match, _, _ = act(
        1, "create_match", organizer_role="organizer_player", board_size=16, capacity=3
    )
    target = {"match_id": match}
    for id in (2, 3):
        act(id, "join_match", **target)

    _, _, deadline = act(1, "start_preparation", **target, preparation_minutes=2)
    assert deadline == now + 120
    key = uuid4().hex
    assert act(1, "submit_version", **target, source="selected", key=key)[1]
    assert not act(1, "submit_version", **target, source="selected", key=key)[1]
    act(1, "submit_version", **target, source="newer")
    if with_second_submission:
        act(2, "submit_version", **target, source="default")
    with Session(engine) as db:
        view = Subscription(view="lobby", **target)
        mine = snapshot(db, 1, view)
        other = snapshot(db, 2, view)
        assert [v["name"] for v in mine["versions"]] == ["Версия #1", "Версия #2"]
        assert not any(v["source"] == "selected" for v in other["versions"])
        selected = mine["versions"][0]["id"]
    act(1, "select_version", **target, version_id=selected)
    act(1, "rename_version", **target, version_id=selected, name="Финал")
    now = deadline
    with pytest.raises(MatchError, match="Подготовка завершена"):
        act(1, "submit_version", **target, source="late")
    with Session(engine) as db:
        assert advance_round(db, match)[1:] == (True, True)
        result = snapshot(db, 3, view)
        assert result["skipped"][-1]["id"] == 3
        assert result["versions"] == []
        game = db.get_one(MatchRound, match).game
        assert game["versions"]["1"] == selected
        state = decode_state(game["state"])
        assert result["status"] == ("running" if with_second_submission else "finished")
        assert len(state.snakes) in (0, 2)
        if not with_second_submission:
            assert result["arena"]["winners"] == []
            assert result["finish_reason"] == "not_enough_algorithms"


def test_resumes_preparation_and_recovers_online_with_memory(tmp_path, monkeypatch):
    from threading import Event
    from time import monotonic, sleep

    from fastapi.testclient import TestClient

    from backend.main import create_app
    from backend.tests.test_matches import create, register, send, subscribe
    from backend.training.executor import ExecutorUnavailable

    available = Event()
    attempted = Event()
    path = tmp_path / "recovery.db"

    class Runner:
        async def decide(self, source, state, memory, *, online):
            attempted.set()
            if not available.is_set():
                raise ExecutorUnavailable
            assert online
            return state["self"]["direction"], {
                "calls": 1 + (memory or {}).get("calls", 0),
                "source": source,
            }

    monkeypatch.setattr("backend.game.TICK_SECONDS", 0.03)
    with TestClient(create_app(path, executor=Runner())) as client:
        host, guest = register(client, "Host"), register(client, "Guest")
        with (
            client.websocket_connect("/api/ws", headers=host) as first,
            client.websocket_connect("/api/ws", headers=guest) as second,
        ):
            id = create(first, "organizer_player")["payload"]["id"]
            target = {"match_id": id}
            assert send(second, "join_match", target)["type"] == "result"
            assert (
                send(first, "start_preparation", {**target, "preparation_minutes": 1})[
                    "type"
                ]
                == "result"
            )
            assert (
                send(first, "submit_version", {**target, "source": "host"})["type"]
                == "result"
            )
            assert (
                send(second, "submit_version", {**target, "source": "guest"})["type"]
                == "result"
            )

    engine = create_engine(f"sqlite:///{path}")
    with Session(engine) as db:
        db.get_one(MatchRound, id).next_at = 0
        db.commit()

    def read():
        with Session(engine) as db:
            return db.get_one(MatchRound, id).game

    with (
        TestClient(create_app(path, executor=Runner())) as client,
        client.websocket_connect("/api/ws", headers=guest) as second,
    ):
        assert attempted.wait(3)
        lobby = subscribe(second, "lobby", **target)
        assert lobby["status"] == "running"
        assert lobby["arena"]["tick"] == 0
        assert read()["memories"] == {}
        available.set()
        end = monotonic() + 4
        while read()["state"]["tick"] < 2 and monotonic() < end:
            sleep(0.02)
        assert read()["state"]["tick"] >= 2
        assert read()["memories"]["1"]["source"] == "host"
        assert read()["memories"]["1"]["calls"] >= 2
