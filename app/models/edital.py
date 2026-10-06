from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, Boolean
from sqlalchemy.orm import relationship
from app.database import Base

def utc_now():
    return datetime.now(timezone.utc)

class Edital(Base):
    __tablename__ = "editais"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(200), nullable=False)
    orgao = Column(String(100), nullable=True)
    cargo = Column(String(100), nullable=True)
    ativo = Column(Boolean, default=True)
    data_criacao = Column(DateTime, default=utc_now)

    disciplinas = relationship("Disciplina", back_populates="edital", cascade="all, delete-orphan")
    ciclos = relationship("CicloEstudos", back_populates="edital", cascade="all, delete-orphan")
