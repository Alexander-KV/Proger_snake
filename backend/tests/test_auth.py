from fastapi.testclient import TestClient
from backend.main import create_app


def test_uvicorn_entrypoint():
    from fastapi import FastAPI
    from uvicorn.importer import import_from_string

    assert isinstance(import_from_string("backend.main:app"), FastAPI)


def test_registration_session_and_logout(tmp_path):
    with TestClient(create_app(tmp_path / "test.db")) as client:
        response = client.post(
            "/api/auth/register",
            json={"username": "Snake_1", "name": "123", "password": "1234"},
        )
        assert response.status_code == 201
        assert client.get("/api/auth/me").json()["name"] == "123"
        assert client.post("/api/auth/logout").status_code == 204
        assert client.get("/api/auth/me").status_code == 401
        assert (
            client.post(
                "/api/auth/login", json={"username": "snake_1", "password": "1234"}
            ).status_code
            == 200
        )


def test_validation_and_unique_username(tmp_path):
    with TestClient(create_app(tmp_path / "test.db")) as client:
        assert (
            client.post(
                "/api/auth/register",
                json={"username": "bad name", "name": "123", "password": "1234"},
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/api/auth/register",
                json={"username": "snake", "name": "bad-name", "password": "1234"},
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/api/auth/register",
                json={"username": "snake", "name": "123", "password": "1234"},
            ).status_code
            == 201
        )
        assert (
            client.post(
                "/api/auth/register",
                json={"username": "SNAKE", "name": "456", "password": "1234"},
            ).status_code
            == 409
        )
        assert (
            client.post(
                "/api/auth/login", json={"username": "snake", "password": "wrong"}
            ).status_code
            == 401
        )


def test_team_name_allowed_characters_and_length(tmp_path):
    with TestClient(create_app(tmp_path / "test.db")) as client:
        for index, name in enumerate(
            ["Змейка_Ёж123", "ABC_123", "123456789012345", "команда 1", "A  B"]
        ):
            response = client.post(
                "/api/auth/register",
                json={"username": f"team{index}", "name": name, "password": "1234"},
            )
            assert response.status_code == 201
            assert response.json()["name"] == name
        for name in ["", "   ", "team-1", "é", "1234567890123456", "a\tb"]:
            response = client.post(
                "/api/auth/register",
                json={"username": "invalid", "name": name, "password": "1234"},
            )
            assert response.status_code == 422


def test_origin_guard_accepts_same_origin_and_rejects_other_origins(tmp_path):
    with TestClient(
        create_app(tmp_path / "test.db"), base_url="http://localhost:5173"
    ) as client:
        data = {"username": "team", "name": "Команда", "password": "1234"}
        assert (
            client.post(
                "/api/auth/register",
                json=data,
                headers={"Origin": "http://example.com"},
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/api/auth/register",
                json=data,
                headers={"Origin": "http://localhost:5173"},
            ).status_code
            == 201
        )


def test_existing_database_and_session_remain_usable(tmp_path):
    import hashlib
    import sqlite3
    import time

    from argon2 import PasswordHasher

    path = tmp_path / "existing.db"
    token = "existing-session-token"
    with sqlite3.connect(path) as db:
        db.executescript("""
            CREATE TABLE teams (id INTEGER PRIMARY KEY, username TEXT NOT NULL COLLATE NOCASE UNIQUE, name TEXT NOT NULL, password_hash TEXT NOT NULL);
            CREATE TABLE sessions (token_hash TEXT PRIMARY KEY, team_id INTEGER NOT NULL REFERENCES teams(id), expires REAL NOT NULL);
        """)
        db.execute(
            "INSERT INTO teams VALUES (?, ?, ?, ?)",
            (1, "OldTeam", "123", PasswordHasher().hash("pass")),
        )
        db.execute(
            "INSERT INTO sessions VALUES (?, ?, ?)",
            (hashlib.sha256(token.encode()).hexdigest(), 1, time.time() + 3600),
        )
    with TestClient(create_app(path)) as client:
        client.cookies.set("session", token)
        assert client.get("/api/auth/me").json() == {
            "username": "OldTeam",
            "name": "123",
        }
        assert (
            client.post(
                "/api/auth/login", json={"username": "oldteam", "password": "pass"}
            ).status_code
            == 200
        )
        assert (
            client.post(
                "/api/auth/register",
                json={"username": "OLDTEAM", "name": "456", "password": "1234"},
            ).status_code
            == 409
        )


def test_local_proxy_separates_client_limits(tmp_path):
    with TestClient(
        create_app(tmp_path / "test.db"), client=("127.0.0.1", 12345)
    ) as client:
        data = {"username": "missing", "password": "wrong"}
        headers = {"X-Snake-Client-IP": "192.0.2.1"}
        for _ in range(20):
            assert (
                client.post("/api/auth/login", json=data, headers=headers).status_code
                == 401
            )
        assert (
            client.post("/api/auth/login", json=data, headers=headers).status_code
            == 429
        )
        assert (
            client.post(
                "/api/auth/login", json=data, headers={"X-Snake-Client-IP": "192.0.2.2"}
            ).status_code
            == 401
        )


def test_external_client_cannot_change_limit_with_proxy_header(tmp_path):
    with TestClient(
        create_app(tmp_path / "test.db"), client=("192.0.2.1", 12345)
    ) as client:
        data = {"username": "missing", "password": "wrong"}
        for index in range(20):
            assert (
                client.post(
                    "/api/auth/login",
                    json=data,
                    headers={"X-Snake-Client-IP": f"198.51.100.{index}"},
                ).status_code
                == 401
            )
        assert (
            client.post(
                "/api/auth/login",
                json=data,
                headers={"X-Snake-Client-IP": "198.51.100.99"},
            ).status_code
            == 429
        )


def test_invalid_proxy_address_uses_connection_limit(tmp_path):
    with TestClient(
        create_app(tmp_path / "test.db"), client=("127.0.0.1", 12345)
    ) as client:
        data = {"username": "missing", "password": "wrong"}
        for index in range(20):
            assert (
                client.post(
                    "/api/auth/login",
                    json=data,
                    headers={"X-Snake-Client-IP": f"invalid-{index}"},
                ).status_code
                == 401
            )
        assert client.post("/api/auth/login", json=data).status_code == 429


def test_ipv4_mapped_address_shares_ipv4_limit(tmp_path):
    with TestClient(create_app(tmp_path / "test.db"), client=("::1", 12345)) as client:
        data = {"username": "missing", "password": "wrong"}
        for _ in range(20):
            assert (
                client.post(
                    "/api/auth/login",
                    json=data,
                    headers={"X-Snake-Client-IP": "::ffff:192.0.2.1"},
                ).status_code
                == 401
            )
        assert (
            client.post(
                "/api/auth/login", json=data, headers={"X-Snake-Client-IP": "192.0.2.1"}
            ).status_code
            == 429
        )
