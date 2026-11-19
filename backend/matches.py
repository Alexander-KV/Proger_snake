from time import time
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StrictInt
from sqlalchemy import func, text
from sqlmodel import Session, select

from backend import game
from backend.models import Match, MatchMembership, MatchRound, Team

MINIMUM_PLAYERS = 2

MatchId = Annotated[StrictInt, Field(gt=0, le=2**63 - 1)]


class CreateMatch(BaseModel):
    capacity: Literal[2, 3, 4]
    board_size: Literal[16, 24, 32]
    organizer_role: Literal["organizer_observer", "organizer_player"]


class MatchTarget(BaseModel):
    match_id: MatchId


class StartMatch(MatchTarget):
    countdown_seconds: Annotated[StrictInt, Field(ge=0, le=60)]


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
        raise MatchError("match_closed", "Организатор отменил матч.")
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
            .where(Match.status.in_(("waiting", "countdown", "running")))
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
        raise MatchError("match_closed", "Организатор отменил матч.")
    round_data = db.get(MatchRound, match.id)
    if match.status == "finished":
        assert round_data is not None
        players = [
            {"id": snake["team_id"], "name": snake["name"]}
            for snake in round_data.game["snakes"]
        ]
        if team_id == match.organizer_team_id:
            role = match.organizer_role
        elif any(player["id"] == team_id for player in players):
            role = "participant"
        else:
            raise MatchError("forbidden", "Матч доступен организатору и участникам.")
    elif membership is not None and membership.match_id == match.id:
        role = membership.role
        players = [
            {"id": player_id, "name": name}
            for player_id, name in participants(db, match.id)
        ]
    else:
        raise MatchError("forbidden", "Лобби доступно организатору и участникам.")

    organizer = db.get(Team, match.organizer_team_id)
    assert organizer is not None
    return {
        **summarize(match, len(players)),
        "organizer": {"id": organizer.id, "name": organizer.name},
        "participants": players,
        "my_role": role,
        "minimum_players": MINIMUM_PLAYERS,
        "starts_at": round_data.next_at
        if match.status == "countdown" and round_data
        else None,
        "server_time": time(),
        "game": round_data.game
        if match.status in ("running", "finished") and round_data
        else None,
    }


def participants(db: Session, match_id: int) -> list[tuple[int, str]]:
    rows = db.exec(
        select(Team.id, Team.name)
        .join(MatchMembership, Team.id == MatchMembership.team_id)
        .where(
            MatchMembership.match_id == match_id,
            MatchMembership.role != "organizer_observer",
        )
        .order_by(Team.id)
    )
    return [(team_id, name) for team_id, name in rows]


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


def update_match(db: Session, team_id: int, action: str, data: MatchTarget) -> bool:
    match_id = data.match_id
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
        return organize(db, team_id, match, action, data)
    return True


def clear_memberships(db: Session, match_id: int):
    for member in db.exec(
        select(MatchMembership).where(MatchMembership.match_id == match_id)
    ):
        db.delete(member)


def organize(db: Session, team_id: int, match: Match, action: str, data: MatchTarget):
    if team_id != match.organizer_team_id:
        raise MatchError("forbidden", "Действие доступно только организатору.")
    assert match.id is not None

    if action == "start_match":
        assert isinstance(data, StartMatch)
        require_waiting(match)
        players = participants(db, match.id)
        if len(players) < MINIMUM_PLAYERS:
            raise MatchError(
                "not_enough_players", "Для старта нужны минимум две команды."
            )
        match.status = "countdown" if data.countdown_seconds else "running"
        db.add(
            MatchRound(
                match_id=match.id,
                next_at=time() + (data.countdown_seconds or game.TICK_SECONDS),
                game=game.new_game(match.board_size, players, match.id),
            )
        )
    elif action == "cancel_countdown":
        if match.status != "countdown":
            raise MatchError("no_countdown", "Сейчас нет активного отсчёта.")
        match.status = "waiting"
        db.delete(db.get_one(MatchRound, match.id))
    elif action == "close_match":
        if match.status == "closed":
            return False
        if match.status == "finished":
            raise MatchError("match_finished", "Матч уже завершён.")
        match.status = "closed"
        round_data = db.get(MatchRound, match.id)
        if round_data is not None:
            db.delete(round_data)
        clear_memberships(db, match.id)
    return True


def active_rounds(db: Session) -> list[tuple[int, float]]:
    return list(
        db.exec(
            select(MatchRound.match_id, MatchRound.next_at)
            .join(Match, Match.id == MatchRound.match_id)
            .where(Match.status.in_(("countdown", "running")))
        )
    )


def advance_round(db: Session, match_id: int) -> tuple[float | None, bool, bool]:
    db.execute(text("BEGIN IMMEDIATE"))
    match = db.get_one(Match, match_id)
    round_data = db.get(MatchRound, match_id)
    if round_data is None or match.status not in ("countdown", "running"):
        return None, False, False
    now = time()
    if round_data.next_at > now:
        return round_data.next_at, False, False
    status_changed = match.status == "countdown"
    if status_changed:
        match.status = "running"
    else:
        state = game.restore_game(round_data.game)
        round_data.game, finished = game.advance(state, match.board_size, match_id)
        if finished:
            match.status = "finished"
            clear_memberships(db, match_id)
            db.commit()
            return None, True, True
    next_at = now + game.TICK_SECONDS
    round_data.next_at = next_at
    db.commit()
    return next_at, True, status_changed


def mutate(db: Session, team_id: int, action: str, payload: dict, key: str):
    model = {"create_match": CreateMatch, "start_match": StartMatch}.get(
        action, MatchTarget
    )
    data = model.model_validate(payload)
    db.execute(text("BEGIN IMMEDIATE"))
    if isinstance(data, CreateMatch):
        match_id, changed = create_match(db, team_id, data, key)
    else:
        match_id = data.match_id
        changed = update_match(db, team_id, action, data)
    next_at = None
    if action == "start_match":
        next_at = db.get_one(MatchRound, match_id).next_at
    db.commit()
    return match_id, changed, next_at
