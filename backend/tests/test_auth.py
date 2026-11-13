from fastapi.testclient import TestClient
from backend.main import create_app


def test_registration_session_and_logout(tmp_path):
    with TestClient(create_app(tmp_path / 'test.db')) as client:
        response = client.post('/api/auth/register', json={'username': 'Snake_1', 'name': '123', 'password': '1234'})
        assert response.status_code == 201
        assert client.get('/api/auth/me').json()['name'] == '123'
        assert client.post('/api/auth/logout').status_code == 204
        assert client.get('/api/auth/me').status_code == 401
        assert client.post('/api/auth/login', json={'username': 'snake_1', 'password': '1234'}).status_code == 200


def test_validation_and_unique_username(tmp_path):
    with TestClient(create_app(tmp_path / 'test.db')) as client:
        assert client.post('/api/auth/register', json={'username': 'bad name', 'name': '123', 'password': '1234'}).status_code == 422
        assert client.post('/api/auth/register', json={'username': 'snake', 'name': 'abc', 'password': '1234'}).status_code == 422
        assert client.post('/api/auth/register', json={'username': 'snake', 'name': '123', 'password': '1234'}).status_code == 201
        assert client.post('/api/auth/register', json={'username': 'SNAKE', 'name': '456', 'password': '1234'}).status_code == 409
        assert client.post('/api/auth/login', json={'username': 'snake', 'password': 'wrong'}).status_code == 401


def test_existing_database_and_session_remain_usable(tmp_path):
    import hashlib
    import sqlite3
    import time

    from argon2 import PasswordHasher

    path = tmp_path / 'existing.db'
    token = 'existing-session-token'
    with sqlite3.connect(path) as db:
        db.executescript('''
            CREATE TABLE teams (id INTEGER PRIMARY KEY, username TEXT NOT NULL COLLATE NOCASE UNIQUE, name TEXT NOT NULL, password_hash TEXT NOT NULL);
            CREATE TABLE sessions (token_hash TEXT PRIMARY KEY, team_id INTEGER NOT NULL REFERENCES teams(id), expires REAL NOT NULL);
        ''')
        db.execute('INSERT INTO teams VALUES (?, ?, ?, ?)', (1, 'OldTeam', '123', PasswordHasher().hash('pass')))
        db.execute('INSERT INTO sessions VALUES (?, ?, ?)', (hashlib.sha256(token.encode()).hexdigest(), 1, time.time() + 3600))
    with TestClient(create_app(path)) as client:
        client.cookies.set('session', token)
        assert client.get('/api/auth/me').json() == {'username': 'OldTeam', 'name': '123'}
        assert client.post('/api/auth/login', json={'username': 'oldteam', 'password': 'pass'}).status_code == 200
        assert client.post('/api/auth/register', json={'username': 'OLDTEAM', 'name': '456', 'password': '1234'}).status_code == 409
