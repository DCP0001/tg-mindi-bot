import datetime
from sqlalchemy import BigInteger, Boolean, Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import relationship
from mindi.database.db import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False, index=True)
    username = Column(String(100), nullable=True)
    display_name = Column(String(150), nullable=False)
    
    # ELO and Stats
    rating = Column(Integer, default=1000, nullable=False)
    highest_rating = Column(Integer, default=1000, nullable=False)
    games_played = Column(Integer, default=0, nullable=False)
    wins = Column(Integer, default=0, nullable=False)
    losses = Column(Integer, default=0, nullable=False)
    win_rate = Column(Float, default=0.0, nullable=False)
    total_points = Column(Integer, default=0, nullable=False)  # Cumulative Mindis captured
    
    # Relationships
    match_participations = relationship("MatchPlayer", back_populates="user")

    def update_stats(self, won: bool, rating_change: int, mindis_captured: int):
        self.games_played += 1
        if won:
            self.wins += 1
        else:
            self.losses += 1
        self.win_rate = float(self.wins) / self.games_played
        self.rating += rating_change
        if self.rating > self.highest_rating:
            self.highest_rating = self.rating
        if self.rating < 100:  # Prevent rating from dropping below 100
            self.rating = 100
        self.total_points += mindis_captured


class Match(Base):
    __tablename__ = "matches"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    mode = Column(String(50), default="casual", nullable=False)  # casual, ranked, private
    status = Column(String(50), default="lobby", nullable=False)  # lobby, playing, completed
    
    winner_team = Column(Integer, nullable=True)  # 1 or 2
    trump_suit = Column(String(10), nullable=True)
    trump_mode = Column(String(20), default="open", nullable=False)  # open, hidden
    is_trump_revealed = Column(Boolean, default=False, nullable=False)
    group_chat_id = Column(BigInteger, nullable=True)  # Chat ID where match lobby was created
    
    # Relationships
    players = relationship("MatchPlayer", back_populates="match", cascade="all, delete-orphan")


class MatchPlayer(Base):
    __tablename__ = "match_players"

    id = Column(Integer, primary_key=True, index=True)
    match_id = Column(Integer, ForeignKey("matches.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)  # Null if AI player
    
    # In Mindi, players are grouped in teams:
    # Team 1: Seats 0 and 2
    # Team 2: Seats 1 and 3
    team = Column(Integer, nullable=False)  # 1 or 2
    seat_index = Column(Integer, nullable=False)  # 0 to 3
    is_ai = Column(Boolean, default=False, nullable=False)
    ai_level = Column(String(20), default="medium", nullable=True)  # easy, medium, hard
    is_connected = Column(Boolean, default=True, nullable=False)

    # Relationships
    match = relationship("Match", back_populates="players")
    user = relationship("User", back_populates="match_participations")
