import hashlib
import re
import secrets
import sqlite3
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, field_validator


class Login(BaseModel):
    username: str
    password: str


class Registration(Login):
    name: str

    @field_validator('username')
    @classmethod
    def valid_username(cls, value):
        if not re.fullmatch(r'[A-Za-z0-9_]{1,15}', value):
            raise ValueError('Некорректный username')
        return value

    @field_validator('name')
    @classmethod
    def valid_name(cls, value):
        value = value.strip()
        if not re.fullmatch(r'[0-9]{1,15}', value):
            raise ValueError('Название должно содержать только цифры')
        return value

    @field_validator('password')
    @classmethod
    def valid_password(cls, value):
        if len(value) < 4:
            raise ValueError('Пароль должен содержать минимум 4 символа')
        return value


def create_app(db_path=Path('data/snake-arena.db')):
    db_path = Path(db_path)
    hasher = PasswordHasher()
    attempts = defaultdict(deque)

    def connect():
        db = sqlite3.connect(db_path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    @asynccontextmanager
    async def lifespan(_app):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS teams (id INTEGER PRIMARY KEY, username TEXT NOT NULL COLLATE NOCASE UNIQUE, name TEXT NOT NULL, password_hash TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY, team_id INTEGER NOT NULL REFERENCES teams(id), expires REAL NOT NULL);
            ''')
        yield

    app = FastAPI(lifespan=lifespan)

    @app.middleware('http')
    async def guard(request: Request, call_next):
        if request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
            origin = request.headers.get('origin')
            if origin and urlparse(origin).netloc != request.headers.get('host'):
                return Response(status_code=403)
            if request.url.path in ('/api/auth/login', '/api/auth/register'):
                key = request.client.host if request.client else 'unknown'
                now = time.monotonic()
                queue = attempts[key]
                while queue and queue[0] < now - 60:
                    queue.popleft()
                if len(queue) >= 20:
                    return Response(status_code=429)
                queue.append(now)
        return await call_next(request)

    def set_session(db, team_id, response):
        token = secrets.token_urlsafe(32)
        db.execute('INSERT INTO sessions VALUES (?, ?, ?)', (hashlib.sha256(token.encode()).hexdigest(), team_id, time.time() + 604800))
        response.set_cookie('session', token, max_age=604800, httponly=True, samesite='lax', secure=False, path='/')

    @app.post('/api/auth/register', status_code=201)
    def register(data: Registration, response: Response):
        with connect() as db:
            try:
                cur = db.execute('INSERT INTO teams (username, name, password_hash) VALUES (?, ?, ?)', (data.username, data.name, hasher.hash(data.password)))
            except sqlite3.IntegrityError:
                raise HTTPException(409, 'Username уже занят')
            set_session(db, cur.lastrowid, response)
        return {'username': data.username, 'name': data.name}

    @app.post('/api/auth/login')
    def login(data: Login, response: Response):
        with connect() as db:
            team = db.execute('SELECT * FROM teams WHERE username = ?', (data.username,)).fetchone()
            try:
                valid = team and hasher.verify(team['password_hash'], data.password)
            except VerifyMismatchError:
                valid = False
            if not valid:
                raise HTTPException(401, 'Неверный username или пароль')
            set_session(db, team['id'], response)
            return {'username': team['username'], 'name': team['name']}

    @app.get('/api/auth/me')
    def me(request: Request):
        token = request.cookies.get('session', '')
        with connect() as db:
            team = db.execute('SELECT teams.username, teams.name FROM sessions JOIN teams ON teams.id = sessions.team_id WHERE token_hash = ? AND expires > ?', (hashlib.sha256(token.encode()).hexdigest(), time.time())).fetchone()
        if not team:
            raise HTTPException(401, 'Требуется вход')
        return dict(team)

    @app.post('/api/auth/logout', status_code=204)
    def logout(request: Request, response: Response):
        token = request.cookies.get('session', '')
        with connect() as db:
            db.execute('DELETE FROM sessions WHERE token_hash = ?', (hashlib.sha256(token.encode()).hexdigest(),))
        response.delete_cookie('session', path='/')

    return app


app = create_app()
