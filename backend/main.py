import hashlib
import re
import secrets
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, field_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.engine import URL
from sqlmodel import Session, SQLModel, create_engine, select

from backend.models import AuthSession, Team


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

    engine = create_engine(URL.create('sqlite', database=str(db_path)), connect_args={'timeout': 10, 'check_same_thread': False})

    @asynccontextmanager
    async def lifespan(_app):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        SQLModel.metadata.create_all(engine)
        yield
        engine.dispose()

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

    def set_session(db: Session, team_id: int, response: Response):
        token = secrets.token_urlsafe(32)
        db.add(AuthSession(token_hash=hashlib.sha256(token.encode()).hexdigest(), team_id=team_id, expires=time.time() + 604800))
        response.set_cookie('session', token, max_age=604800, httponly=True, samesite='lax', secure=False, path='/')

    @app.post('/api/auth/register', status_code=201)
    def register(data: Registration, response: Response):
        with Session(engine) as db:
            team = Team(username=data.username, name=data.name, password_hash=hasher.hash(data.password))
            db.add(team)
            try:
                db.flush()
            except IntegrityError:
                db.rollback()
                raise HTTPException(409, 'Username уже занят')
            assert team.id is not None
            set_session(db, team.id, response)
            db.commit()
        return {'username': data.username, 'name': data.name}

    @app.post('/api/auth/login')
    def login(data: Login, response: Response):
        with Session(engine) as db:
            team = db.exec(select(Team).where(Team.username == data.username)).first()
            try:
                valid = team and hasher.verify(team.password_hash, data.password)
            except VerifyMismatchError:
                valid = False
            if not valid or team is None:
                raise HTTPException(401, 'Неверный username или пароль')
            assert team.id is not None
            set_session(db, team.id, response)
            db.commit()
            return {'username': team.username, 'name': team.name}

    @app.get('/api/auth/me')
    def me(request: Request):
        token = request.cookies.get('session', '')
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        with Session(engine) as db:
            team = db.exec(select(Team).join(AuthSession, Team.id == AuthSession.team_id).where(AuthSession.token_hash == token_hash, AuthSession.expires > time.time())).first()
            if not team:
                raise HTTPException(401, 'Требуется вход')
            return {'username': team.username, 'name': team.name}

    @app.post('/api/auth/logout', status_code=204)
    def logout(request: Request, response: Response):
        token = request.cookies.get('session', '')
        with Session(engine) as db:
            session = db.get(AuthSession, hashlib.sha256(token.encode()).hexdigest())
            if session:
                db.delete(session)
                db.commit()
        response.delete_cookie('session', path='/')

    return app


app = create_app()
