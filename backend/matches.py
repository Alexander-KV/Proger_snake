from time import time
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StrictInt
from sqlalchemy import func, text
from sqlmodel import Session, select

from backend.models import Match, MatchMembership, Team

MatchId = Annotated[StrictInt, Field(gt=0, le=2**63 - 1)]


class CreateMatch(BaseModel):
    capacity: Literal[2, 3, 4]
    board_size: Literal[16, 24, 32]
    organizer_role: Literal["organizer_observer", "organizer_player"]


class MatchTarget(BaseModel):
    match_id: MatchId


class Subscription(BaseModel):
    view: Literal["list", "lobby"]
    match_id: MatchId | None = None


class MatchError(Exception):
    def __init__(self, code: str, message: str, match_id: int | None = None):
        super().__init__(message)
        self.code = code
        self.match_id = match_id


def require_match(db: Session, match_id: int) -> Match:
    match = db.get(Match, match_id)
    if match is None:
        raise MatchError("match_not_found", "Матч не найден.")
    return match


def require_waiting(match: Match):
    if match.status == "closed":
        raise MatchError("match_closed", "Организатор закрыл лобби.")
    if match.status != "waiting":
        raise MatchError("match_not_waiting", "Матч уже начался.")


def player_count(db: Session, match_id: int) -> int:
    return db.exec(
        select(func.count())
        .select_from(MatchMembership)
        .where(
            MatchMembership.match_id == match_id,
            MatchMembership.role != "organizer_observer",
        )
    ).one()


def summarize(match: Match, count: int) -> dict:
    return {
        "id": match.id,
        "capacity": match.capacity,
        "board_size": match.board_size,
        "participant_count": count,
        "status": match.status,
    }


def snapshot(db: Session, team_id: int, view: Subscription) -> dict:
    membership = db.get(MatchMembership, team_id)
    if view.view == "list":
        counts = (
            select(MatchMembership.match_id, func.count().label("players"))
            .where(MatchMembership.role != "organizer_observer")
            .group_by(MatchMembership.match_id)
            .subquery()
        )
        rows = db.exec(
            select(Match, func.coalesce(counts.c.players, 0))
            .outerjoin(counts, Match.id == counts.c.match_id)
            .where(Match.status != "closed")
            .order_by(Match.created_at.desc(), Match.id.desc())
        )
        return {
            "current_match_id": membership.match_id if membership else None,
            "matches": [summarize(match, count) for match, count in rows],
        }

    if view.match_id is None:
        raise MatchError("invalid_request", "Выберите матч.")
    match = require_match(db, view.match_id)
    if match.status == "closed":
        raise MatchError("match_closed", "Организатор закрыл лобби.")
    if membership is None or membership.match_id != match.id:
        raise MatchError("forbidden", "Лобби доступно организатору и участникам.")

    organizer = db.get(Team, match.organizer_team_id)
    assert organizer is not None
    participants = db.exec(
        select(Team.id, Team.name)
        .join(MatchMembership, Team.id == MatchMembership.team_id)
        .where(
            MatchMembership.match_id == match.id,
            MatchMembership.role != "organizer_observer",
        )
        .order_by(Team.id)
    )
    players = [{"id": player_id, "name": name} for player_id, name in participants]
    return {
        **summarize(match, len(players)),
        "organizer": {"id": organizer.id, "name": organizer.name},
        "participants": players,
        "my_role": membership.role,
    }


def require_available(membership: MatchMembership | None):
    if membership is not None:
        raise MatchError(
            "active_match", "Ваша команда уже в матче.", membership.match_id
        )


def create_match(
    db: Session, team_id: int, data: CreateMatch, request_id: str
) -> tuple[int, bool]:
    previous = db.exec(
        select(Match).where(
            Match.organizer_team_id == team_id, Match.request_id == request_id
        )
    ).first()
    if previous is not None:
        if any(
            getattr(previous, key) != value for key, value in data.model_dump().items()
        ):
            raise MatchError(
                "request_id_reused",
                "Эта попытка уже использована с другими настройками.",
            )
        assert previous.id is not None
        return previous.id, False

    require_available(db.get(MatchMembership, team_id))
    match = Match(
        **data.model_dump(),
        organizer_team_id=team_id,
        request_id=request_id,
        created_at=time(),
    )
    db.add(match)
    db.flush()
    assert match.id is not None
    db.add(
        MatchMembership(team_id=team_id, match_id=match.id, role=data.organizer_role)
    )
    return match.id, True


def update_match(db: Session, team_id: int, action: str, match_id: int) -> bool:
    match = require_match(db, match_id)
    membership = db.get(MatchMembership, team_id)
    is_member = membership is not None and membership.match_id == match_id

    if action == "join_match":
        if is_member:
            return False
        require_waiting(match)
        require_available(membership)
        if player_count(db, match_id) >= match.capacity:
            raise MatchError("match_full", "Все места в этом лобби заняты.")
        db.add(MatchMembership(team_id=team_id, match_id=match_id, role="participant"))
    elif action == "leave_match":
        if team_id == match.organizer_team_id:
            raise MatchError("forbidden", "Организатор может закрыть лобби.")
        if not is_member:
            return False
        require_waiting(match)
        db.delete(membership)
    else:
        if team_id != match.organizer_team_id:
            raise MatchError("forbidden", "Только организатор может закрыть лобби.")
        if match.status == "closed":
            return False
        require_waiting(match)
        match.status = "closed"
        for member in db.exec(
            select(MatchMembership).where(MatchMembership.match_id == match_id)
        ):
            db.delete(member)
    return True


def mutate(db: Session, team_id: int, action: str, payload: dict, key: str):
    data = (
        CreateMatch.model_validate(payload)
        if action == "create_match"
        else MatchTarget.model_validate(payload)
    )
    db.execute(text("BEGIN IMMEDIATE"))
    if isinstance(data, CreateMatch):
        match_id, changed = create_match(db, team_id, data, key)
    else:
        match_id = data.match_id
        changed = update_match(db, team_id, action, match_id)
    db.commit()
    return match_id, changed
