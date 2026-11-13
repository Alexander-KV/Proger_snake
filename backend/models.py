from sqlalchemy import Column, Float, Integer, Text
from sqlmodel import Field, SQLModel


class Team(SQLModel, table=True):
    __tablename__ = 'teams'

    id: int | None = Field(default=None, primary_key=True)
    username: str = Field(sa_column=Column(Text(collation='NOCASE'), nullable=False, unique=True))
    name: str
    password_hash: str


class AuthSession(SQLModel, table=True):
    __tablename__ = 'sessions'

    token_hash: str = Field(sa_column=Column(Text, primary_key=True))
    team_id: int = Field(foreign_key='teams.id', sa_type=Integer, nullable=False)
    expires: float = Field(sa_type=Float, nullable=False)
