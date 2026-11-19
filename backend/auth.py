import hashlib
from time import time

from sqlmodel import Session, select

from backend.models import AuthSession, Team


def session_key(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def find_session(db: Session, key: str) -> tuple[Team, AuthSession] | None:
    return db.exec(
        select(Team, AuthSession)
        .join(AuthSession, Team.id == AuthSession.team_id)
        .where(AuthSession.token_hash == key, AuthSession.expires > time())
    ).first()
