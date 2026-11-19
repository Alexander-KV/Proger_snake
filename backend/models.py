from sqlalchemy import JSON, Column, Float, Integer, Text, UniqueConstraint
from sqlmodel import Field, SQLModel


class Team(SQLModel, table=True):
    __tablename__ = "teams"

    id: int | None = Field(default=None, primary_key=True)
    username: str = Field(
        sa_column=Column(Text(collation="NOCASE"), nullable=False, unique=True)
    )
    name: str
    password_hash: str


class AuthSession(SQLModel, table=True):
    __tablename__ = "sessions"

    token_hash: str = Field(sa_column=Column(Text, primary_key=True))
    team_id: int = Field(foreign_key="teams.id", sa_type=Integer, nullable=False)
    expires: float = Field(sa_type=Float, nullable=False)


class Match(SQLModel, table=True):
    __tablename__ = "matches"
    __table_args__ = (UniqueConstraint("organizer_team_id", "request_id"),)

    id: int | None = Field(default=None, primary_key=True)
    organizer_team_id: int = Field(foreign_key="teams.id")
    organizer_role: str
    capacity: int
    board_size: int
    status: str = "waiting"
    created_at: float
    request_id: str


class MatchMembership(SQLModel, table=True):
    __tablename__ = "match_memberships"

    team_id: int = Field(primary_key=True, foreign_key="teams.id")
    match_id: int = Field(foreign_key="matches.id", index=True)
    role: str


class MatchRound(SQLModel, table=True):
    __tablename__ = "match_rounds"

    match_id: int = Field(primary_key=True, foreign_key="matches.id")
    next_at: float = Field(sa_type=Float)
    game: dict = Field(sa_column=Column(JSON, nullable=False))


class TrainingMap(SQLModel, table=True):
    __tablename__ = "training_maps"

    id: int | None = Field(default=None, primary_key=True)
    team_id: int = Field(foreign_key="teams.id", index=True)
    name: str
    data: dict = Field(sa_column=Column(JSON, nullable=False))


class MatchPreparation(SQLModel, table=True):
    __tablename__ = "match_preparations"

    match_id: int = Field(primary_key=True, foreign_key="matches.id")
    participants: list = Field(sa_column=Column(JSON, nullable=False))


class AlgorithmVersion(SQLModel, table=True):
    __tablename__ = "algorithm_versions"
    __table_args__ = (
        UniqueConstraint("match_id", "team_id", "number"),
        UniqueConstraint("match_id", "team_id", "request_id"),
    )

    id: int | None = Field(default=None, primary_key=True)
    match_id: int = Field(foreign_key="matches.id")
    team_id: int = Field(foreign_key="teams.id")
    number: int
    name: str
    source: str
    submitted_at: float = Field(sa_type=Float)
    request_id: str


class AlgorithmSelection(SQLModel, table=True):
    __tablename__ = "algorithm_selections"

    match_id: int = Field(primary_key=True, foreign_key="matches.id")
    team_id: int = Field(primary_key=True, foreign_key="teams.id")
    version_id: int = Field(foreign_key="algorithm_versions.id")
