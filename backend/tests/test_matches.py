from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from backend.main import create_app

ORIGIN = {"origin": "http://testserver"}


def register(client, name):
    response = client.post(
        "/api/auth/register",
        json={"username": name, "name": name, "password": "pass"},
    )
    assert response.status_code == 201
    return {"cookie": f"session={response.cookies['session']}", **ORIGIN}


def send(socket, kind, payload, key=None):
    key = key or uuid4().hex
    socket.send_json({"type": kind, "request_id": key, "payload": payload})
    while True:
        response = socket.receive_json()
        if response.get("request_id") == key:
            return response


def create(socket, role="organizer_observer", capacity=2, key=None):
    return send(
        socket,
        "create_match",
        {"organizer_role": role, "capacity": capacity, "board_size": 24},
        key,
    )


def subscribe(socket, view, **params):
    result = send(socket, "subscribe", {"view": view, **params})
    assert result["type"] == "result"
    snapshot = socket.receive_json()
    assert snapshot["subscription_id"] == result["request_id"]
    return snapshot["payload"]


@pytest.fixture
def server(tmp_path):
    with TestClient(create_app(tmp_path / "matches.db")) as client:
        yield client


def test_socket_requires_session_and_origin(server):
    valid = register(server, "Team1")
    with pytest.raises(WebSocketDisconnect):
        with server.websocket_connect(
            "/api/ws", headers=valid | {"origin": "http://foreign.test"}
        ):
            pass
    with server.websocket_connect("/api/ws", headers=ORIGIN | {"cookie": ""}) as socket:
        assert socket.receive()["code"] == 1008
    with server.websocket_connect("/api/ws", headers=valid) as socket:
        assert subscribe(socket, "list") == {"current_match_id": None, "matches": []}


def test_snapshots_create_retry_join_leave_and_close(server):
    host = register(server, "Host")
    player = register(server, "Player")
    with (
        server.websocket_connect("/api/ws", headers=host) as a,
        server.websocket_connect("/api/ws", headers=player) as b,
    ):
        assert subscribe(b, "list")["matches"] == []
        key = uuid4().hex
        match = create(a, key=key)["payload"]["id"]
        assert b.receive_json()["payload"]["matches"][0]["participant_count"] == 0
        assert create(a, key=key)["payload"]["id"] == match
        assert create(a, capacity=3, key=key)["code"] == "request_id_reused"
        assert create(a)["code"] == "active_match"
        assert subscribe(a, "lobby", match_id=match)["board_size"] == 24

        assert (
            send(b, "subscribe", {"view": "lobby", "match_id": match})["code"]
            == "forbidden"
        )
        assert send(b, "join_match", {"match_id": match})["payload"]["id"] == match
        assert a.receive_json()["payload"]["participant_count"] == 1
        assert send(b, "join_match", {"match_id": match})["payload"]["id"] == match
        assert subscribe(b, "lobby", match_id=match)["my_role"] == "participant"
        assert send(b, "close_match", {"match_id": match})["code"] == "forbidden"
        assert send(b, "leave_match", {"match_id": match})["type"] == "result"
        assert a.receive_json()["payload"]["participant_count"] == 0
        assert send(b, "join_match", {"match_id": match})["type"] == "result"
        assert subscribe(b, "lobby", match_id=match)["participant_count"] == 1
        assert send(a, "close_match", {"match_id": match})["type"] == "result"
        assert b.receive_json()["code"] == "match_closed"
        assert subscribe(b, "list") == {"matches": [], "current_match_id": None}


def test_last_slot_and_team_membership_are_atomic(server):
    headers = [register(server, f"Team{i}") for i in range(4)]
    with ExitStack() as stack:
        sockets = [
            stack.enter_context(server.websocket_connect("/api/ws", headers=h))
            for h in headers
        ]
        first = create(sockets[0], "organizer_player")["payload"]["id"]
        second = create(sockets[1], "organizer_player")["payload"]["id"]

        def race(*entries):
            barrier = Barrier(len(entries))

            def join(pair):
                socket, match = pair
                barrier.wait(3)
                return send(socket, "join_match", {"match_id": match}).get(
                    "code", "joined"
                )

            with ThreadPoolExecutor(len(entries)) as pool:
                return set(pool.map(join, entries))

        assert race((sockets[2], first), (sockets[3], first)) == {
            "joined",
            "match_full",
        }
        winner = next(
            s for s in sockets[2:] if subscribe(s, "list")["current_match_id"] == first
        )
        winner_headers = headers[sockets.index(winner)]
        assert send(winner, "leave_match", {"match_id": first})["type"] == "result"
        other_tab = stack.enter_context(
            server.websocket_connect("/api/ws", headers=winner_headers)
        )
        assert race((winner, first), (other_tab, second)) == {"joined", "active_match"}


def test_reconnect_after_restart_gets_current_snapshot(tmp_path):
    path = tmp_path / "persistent.db"
    with TestClient(create_app(path)) as client:
        host = register(client, "Host")
        guest = register(client, "Guest")
        with client.websocket_connect("/api/ws", headers=host) as socket:
            match = create(socket)["payload"]["id"]
        with client.websocket_connect("/api/ws", headers=guest) as socket:
            assert send(socket, "join_match", {"match_id": match})["type"] == "result"

    with TestClient(create_app(path)) as client:
        with client.websocket_connect("/api/ws", headers=host) as socket:
            snapshot = subscribe(socket, "lobby", match_id=match)
            assert snapshot["participants"][0]["name"] == "Guest"


def test_socket_closes_on_logout(server):
    host = register(server, "Host")
    with server.websocket_connect("/api/ws", headers=host) as socket:
        assert subscribe(socket, "list")["matches"] == []
        assert server.post("/api/auth/logout", headers=host).status_code == 204
        assert socket.receive()["code"] == 1008


def test_socket_closes_on_session_expiry(server, tmp_path):
    import sqlite3
    import time

    host = register(server, "Host")
    with sqlite3.connect(tmp_path / "matches.db") as db:
        db.execute("UPDATE sessions SET expires = ?", (time.time() + 0.5,))

    with server.websocket_connect("/api/ws", headers=host) as socket:
        assert subscribe(socket, "list")["matches"] == []
        assert socket.receive()["code"] == 1008


def test_reconnect_after_logout_reports_invalid_session(server):
    team = register(server, "Team")
    assert server.post("/api/auth/logout", headers=team).status_code == 204

    with server.websocket_connect("/api/ws", headers=team) as socket:
        assert socket.receive()["code"] == 1008


def test_close_and_join_are_atomic(server):
    host = register(server, "Host")
    guest = register(server, "Guest")
    with (
        server.websocket_connect("/api/ws", headers=host) as organizer,
        server.websocket_connect("/api/ws", headers=guest) as participant,
    ):
        match_id = create(organizer)["payload"]["id"]
        barrier = Barrier(2)

        def command(socket, action):
            barrier.wait(3)
            return send(socket, action, {"match_id": match_id})

        with ThreadPoolExecutor(2) as pool:
            closing = pool.submit(command, organizer, "close_match")
            joining = pool.submit(command, participant, "join_match")
            assert closing.result()["type"] == "result"
            joined = joining.result()
            assert joined["type"] == "result" or joined["code"] == "match_closed"
        assert subscribe(participant, "list") == {
            "current_match_id": None,
            "matches": [],
        }


def test_invalid_command_preserves_subscription(server):
    host = register(server, "Host")
    with server.websocket_connect("/api/ws", headers=host) as socket:
        assert subscribe(socket, "list")["matches"] == []
        assert create(socket, capacity=5)["code"] == "invalid_request"
        assert create(socket, role="participant")["code"] == "invalid_request"
        match_id = create(socket)["payload"]["id"]
        assert socket.receive_json()["payload"]["current_match_id"] == match_id


def test_organizer_starts_with_two_players_and_can_cancel_countdown(server):
    host, player, other = [
        register(server, name) for name in ("Host", "Player", "Other")
    ]
    with (
        server.websocket_connect("/api/ws", headers=host) as a,
        server.websocket_connect("/api/ws", headers=player) as b,
        server.websocket_connect("/api/ws", headers=other) as c,
    ):
        match = create(a, "organizer_player", capacity=4)["payload"]["id"]
        target = {"match_id": match}
        start = target | {"countdown_seconds": 30}
        assert send(a, "start_match", start)["code"] == "not_enough_players"
        assert send(b, "join_match", target)["type"] == "result"
        assert send(b, "start_match", start)["code"] == "forbidden"
        assert subscribe(a, "lobby", **target)["minimum_players"] == 2
        assert subscribe(b, "lobby", **target)["status"] == "waiting"

        assert send(a, "start_match", start)["type"] == "result"
        countdown = b.receive_json()["payload"]
        assert countdown["status"] == "countdown"
        assert countdown["starts_at"] > countdown["server_time"]
        assert send(c, "join_match", target)["code"] == "match_not_waiting"
        assert send(b, "leave_match", target)["code"] == "match_not_waiting"
        assert send(b, "cancel_countdown", target)["code"] == "forbidden"

        assert send(a, "cancel_countdown", target)["type"] == "result"
        reopened = b.receive_json()["payload"]
        assert reopened["status"] == "waiting"
        assert reopened["starts_at"] is None
        assert send(c, "join_match", target)["type"] == "result"
        assert send(a, "start_match", start)["type"] == "result"
        assert send(a, "close_match", target)["type"] == "result"
        assert subscribe(b, "list") == {"matches": [], "current_match_id": None}


def test_observer_starts_round_and_teams_receive_finish(server, monkeypatch):
    monkeypatch.setattr("backend.game.TICK_SECONDS", 0.01, raising=False)
    host, player, other = [
        register(server, name) for name in ("Host", "Player", "Other")
    ]
    with (
        server.websocket_connect("/api/ws", headers=host) as a,
        server.websocket_connect("/api/ws", headers=player) as b,
        server.websocket_connect("/api/ws", headers=other) as c,
    ):
        match = create(a, capacity=3)["payload"]["id"]
        target = {"match_id": match}
        assert send(b, "join_match", target)["type"] == "result"
        start = target | {"countdown_seconds": 0}
        assert send(a, "start_match", start)["code"] == "not_enough_players"
        assert send(c, "join_match", target)["type"] == "result"
        assert subscribe(b, "lobby", **target)["status"] == "waiting"
        assert send(a, "start_match", start)["type"] == "result"
        first = b.receive_json()["payload"]
        assert first["status"] == "running"
        assert len(first["game"]["snakes"]) == 2
        last = first
        for _ in range(301):
            last = b.receive_json()["payload"]
            if last["status"] == "finished":
                break
        assert last["status"] == "finished"
        assert last["game"]["tick"] > first["game"]["tick"]
        assert subscribe(b, "list")["current_match_id"] is None
        assert subscribe(b, "lobby", **target)["status"] == "finished"


def test_pending_countdown_resumes_after_restart(tmp_path):
    path = tmp_path / "restart.db"
    with TestClient(create_app(path)) as client:
        host = register(client, "Host")
        guest = register(client, "Guest")
        with (
            client.websocket_connect("/api/ws", headers=host) as a,
            client.websocket_connect("/api/ws", headers=guest) as b,
        ):
            match = create(a, "organizer_player")["payload"]["id"]
            target = {"match_id": match}
            assert send(b, "join_match", target)["type"] == "result"
            assert (
                send(a, "start_match", target | {"countdown_seconds": 2})["type"]
                == "result"
            )

    with (
        TestClient(create_app(path)) as client,
        client.websocket_connect("/api/ws", headers=guest) as b,
    ):
        current = subscribe(b, "lobby", **target)
        if current["status"] == "countdown":
            current = b.receive_json()["payload"]
        assert current["status"] == "running"
        assert [snake["name"] for snake in current["game"]["snakes"]] == [
            "Host",
            "Guest",
        ]
