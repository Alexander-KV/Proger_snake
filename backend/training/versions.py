from sqlalchemy import func
from sqlmodel import Session, select

from backend.models import (
    AlgorithmSelection,
    AlgorithmVersion,
    MatchPreparation,
    MatchRound,
)
from backend.training.maps import ArenaConfig, generate_map
from backend.training.state import ArenaState, encode_state

ROUND_FORMAT = 2


def personal_versions(db: Session, match_id: int, team_id: int):
    selected = db.get(AlgorithmSelection, (match_id, team_id))
    return [
        {
            "id": v.id,
            "name": v.name,
            "source": v.source,
            "submitted_at": v.submitted_at,
            "selected": selected is not None and selected.version_id == v.id,
        }
        for v in db.exec(
            select(AlgorithmVersion)
            .where(
                AlgorithmVersion.match_id == match_id,
                AlgorithmVersion.team_id == team_id,
            )
            .order_by(AlgorithmVersion.number.desc())
        )
    ][::-1]


def find_request(db, match_id, team_id, key):
    return db.exec(
        select(AlgorithmVersion).where(
            AlgorithmVersion.match_id == match_id,
            AlgorithmVersion.team_id == team_id,
            AlgorithmVersion.request_id == key,
        )
    ).first()


def submit(db, match_id, team_id, source, key, now):
    number = (
        db.exec(
            select(func.max(AlgorithmVersion.number)).where(
                AlgorithmVersion.match_id == match_id,
                AlgorithmVersion.team_id == team_id,
            )
        ).one()
        or 0
    )
    db.add(
        AlgorithmVersion(
            match_id=match_id,
            team_id=team_id,
            number=number + 1,
            name=f"Версия #{number + 1}",
            source=source,
            submitted_at=now,
            request_id=key,
        )
    )


def freeze(db: Session, round_data: MatchRound, board_size: int) -> bool:
    preparation = db.get_one(MatchPreparation, round_data.match_id)
    versions, names = {}, {}
    players, skipped = [], []
    for player in preparation.participants:
        team_id = player["id"]
        chosen = db.get(AlgorithmSelection, (round_data.match_id, team_id))
        version = (
            db.get(AlgorithmVersion, chosen.version_id)
            if chosen
            else db.exec(
                select(AlgorithmVersion)
                .where(
                    AlgorithmVersion.match_id == round_data.match_id,
                    AlgorithmVersion.team_id == team_id,
                )
                .order_by(AlgorithmVersion.number.desc())
                .limit(1)
            ).first()
        )
        if version is None:
            skipped.append(player)
        else:
            players.append((team_id, player["name"]))
            versions[str(team_id)] = version.id
            names[str(team_id)] = version.name

    enough = len(players) >= 2
    state = (
        generate_map(
            ArenaConfig(width=board_size, height=board_size, snake_count=len(players)),
            round_data.match_id,
            players,
        )
        if enough
        else ArenaState(width=board_size, height=board_size, snakes=())
    )
    round_data.game = {
        "format": ROUND_FORMAT,
        "state": encode_state(state),
        "versions": versions,
        "version_names": names,
        "memories": {},
        "errors": {},
        "skipped": skipped,
        "finish_reason": None if enough else "not_enough_algorithms",
    }
    return enough
