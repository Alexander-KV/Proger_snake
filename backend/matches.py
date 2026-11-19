from time import time
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StrictInt, StringConstraints, field_validator
from sqlalchemy import func, text
from sqlmodel import Session, select

from backend import game
from backend.models import (
    AlgorithmSelection,
    AlgorithmVersion,
    Match,
    MatchMembership,
    MatchPreparation,
    MatchRound,
    Team,
)
from backend.training import versions
from backend.training.protocol import SOURCE_LIMIT
from backend.training.state import arena_view, decode_state, encode_state

MINIMUM_PLAYERS = 2

MatchId = Annotated[StrictInt, Field(gt=0, le=2**63 - 1)]


class CreateMatch(BaseModel):
    capacity: Literal[2, 3, 4]
    board_size: Literal[16, 24, 32]
    organizer_role: Literal["organizer_observer", "organizer_player"]


class MatchTarget(BaseModel):
    match_id: MatchId


class StartPreparation(MatchTarget):
    preparation_minutes: Annotated[StrictInt, Field(ge=1, le=120)]


class SubmitVersion(MatchTarget):
    source: str = Field(max_length=SOURCE_LIMIT)

    @field_validator("source")
    @classmethod
    def utf8(cls, value):
        if not value.strip() or len(value.encode()) > SOURCE_LIMIT:
            raise ValueError("Добавьте исходный код размером до 8000 байт.")
        return value


class SelectVersion(MatchTarget):
    version_id: MatchId


class RenameVersion(SelectVersion):
    name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)
    ]


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
            .where(Match.status.in_(("waiting", "preparing", "countdown", "running")))
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
    preparation = db.get(MatchPreparation, match.id)
    game_data = round_data.game if round_data else {}
    modern = game_data.get("format") == versions.ROUND_FORMAT
    if match.status == "finished":
        assert round_data is not None
        players = (
            preparation.participants
            if modern and preparation
            else [
                {"id": snake["team_id"], "name": snake["name"]}
                for snake in game_data["snakes"]
            ]
        )
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
    preparing = match.status == "preparing" and round_data is not None
    return {
        **summarize(match, len(players)),
        "organizer": {"id": organizer.id, "name": organizer.name},
        "participants": players,
        "my_role": role,
        "my_team_id": team_id,
        "minimum_players": MINIMUM_PLAYERS,
        "starts_at": round_data.next_at
        if match.status == "countdown" and round_data
        else None,
        "server_time": time(),
        "preparation_ends_at": round_data.next_at if preparing else None,
        "versions": versions.personal_versions(db, match.id, team_id)
        if preparing and role != "organizer_observer"
        else [],
        "game": game_data
        if match.status in ("running", "finished") and not modern
        else None,
        "arena": arena_view(decode_state(game_data["state"])) if modern else None,
        "skipped": game_data.get("skipped", []),
        "finish_reason": game_data.get("finish_reason"),
        "version_names": game_data.get("version_names", {}),
        "algorithm_error": game_data.get("errors", {}).get(str(team_id)),
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

    if action == "start_preparation":
        assert isinstance(data, StartPreparation)
        require_waiting(match)
        players = participants(db, match.id)
        if len(players) < MINIMUM_PLAYERS:
            raise MatchError(
                "not_enough_players", "Для старта нужны минимум две команды."
            )
        match.status = "preparing"
        db.merge(
            MatchPreparation(
                match_id=match.id,
                participants=[{"id": id, "name": name} for id, name in players],
            )
        )
        db.add(
            MatchRound(
                match_id=match.id,
                next_at=time() + 60 * data.preparation_minutes,
                game={},
            )
        )
    elif action == "cancel_preparation":
        pending = db.get(MatchRound, match.id)
        if match.status != "preparing" or pending is None or pending.next_at <= time():
            raise MatchError("no_preparation", "Сейчас нет активной подготовки.")
        match.status = "waiting"
        db.delete(pending)
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
            .where(Match.status.in_(("countdown", "preparing", "running")))
        )
    )


def advance_round(db: Session, match_id: int) -> tuple[float | None, bool, bool]:
    db.execute(text("BEGIN IMMEDIATE"))
    match = db.get_one(Match, match_id)
    round_data = db.get(MatchRound, match_id)
    if round_data is None or match.status not in ("countdown", "preparing", "running"):
        return None, False, False
    now = time()
    if round_data.next_at > now:
        return round_data.next_at, False, False
    if match.status == "preparing":
        running = versions.freeze(db, round_data, match.board_size)
        match.status = "running" if running else "finished"
        round_data.next_at = now
        if not running:
            clear_memberships(db, match_id)
        db.commit()
        return (now if running else None), True, True
    if round_data.game.get("format") == versions.ROUND_FORMAT:
        return now + game.TICK_SECONDS, False, False
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


def change_version(
    db: Session, team_id: int, data: SubmitVersion | SelectVersion, key: str
):
    match = require_match(db, data.match_id)
    if isinstance(data, SubmitVersion):
        previous = versions.find_request(db, data.match_id, team_id, key)
        if previous:
            if previous.source != data.source:
                raise MatchError(
                    "request_id_reused",
                    "Эта попытка уже использована с другим исходником.",
                )
            return False
    membership = db.get(MatchMembership, team_id)
    if (
        membership is None
        or membership.match_id != data.match_id
        or membership.role == "organizer_observer"
    ):
        raise MatchError("forbidden", "Действие доступно только команде-участнице.")
    pending = db.get(MatchRound, data.match_id)
    now = time()
    if match.status != "preparing" or pending is None or pending.next_at <= now:
        raise MatchError("preparation_ended", "Подготовка завершена.")
    if isinstance(data, SubmitVersion):
        versions.submit(db, data.match_id, team_id, data.source, key, now)
        return True
    version = db.get(AlgorithmVersion, data.version_id)
    if (
        version is None
        or version.team_id != team_id
        or version.match_id != data.match_id
    ):
        raise MatchError("version_not_found", "Версия не найдена.")
    if isinstance(data, RenameVersion):
        version.name = data.name
    else:
        db.merge(
            AlgorithmSelection(
                match_id=data.match_id, team_id=team_id, version_id=data.version_id
            )
        )
    return True


def load_online_turn(db: Session, match_id: int):
    match = db.get_one(Match, match_id)
    rd = db.get(MatchRound, match_id)
    if (
        match.status != "running"
        or rd is None
        or rd.game.get("format") != versions.ROUND_FORMAT
        or rd.next_at > time()
    ):
        return None
    state = decode_state(rd.game["state"])
    sources = {
        s.id: db.get_one(AlgorithmVersion, rd.game["versions"][str(s.id)]).source
        for s in state.snakes
        if s.alive
    }
    return state, sources, rd.game["memories"]


def save_online_turn(db: Session, match_id: int, previous_tick: int, turn):
    db.execute(text("BEGIN IMMEDIATE"))
    match = db.get_one(Match, match_id)
    rd = db.get(MatchRound, match_id)
    if (
        match.status != "running"
        or rd is None
        or rd.game.get("format") != versions.ROUND_FORMAT
    ):
        return None, False, False
    if rd.game["state"]["tick"] != previous_tick:
        return rd.next_at, False, False
    state, memories, errors = turn
    rd.game = {
        **rd.game,
        "state": encode_state(state),
        "memories": memories,
        "errors": {**rd.game["errors"], **errors},
    }
    if state.finished:
        match.status = "finished"
        clear_memberships(db, match_id)
    rd.next_at = time() + game.TICK_SECONDS
    db.commit()
    return (None if state.finished else rd.next_at), True, state.finished


def mutate(db: Session, team_id: int, action: str, payload: dict, key: str):
    model = {
        "create_match": CreateMatch,
        "start_preparation": StartPreparation,
        "submit_version": SubmitVersion,
        "select_version": SelectVersion,
        "rename_version": RenameVersion,
    }.get(action, MatchTarget)
    data = model.model_validate(payload)
    db.execute(text("BEGIN IMMEDIATE"))
    if isinstance(data, CreateMatch):
        match_id, changed = create_match(db, team_id, data, key)
    else:
        match_id = data.match_id
        if isinstance(data, (SubmitVersion, SelectVersion)):
            changed = change_version(db, team_id, data, key)
        else:
            changed = update_match(db, team_id, action, data)
    next_at = None
    if action == "start_preparation":
        next_at = db.get_one(MatchRound, match_id).next_at
    db.commit()
    return match_id, changed, next_at
