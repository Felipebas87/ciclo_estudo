from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from app.database import Base

def utc_now():
    return datetime.now(timezone.utc)

class CicloEstudos(Base):
    __tablename__ = "ciclos_estudo"

    id = Column(Integer, primary_key=True, index=True)
    edital_id = Column(Integer, ForeignKey("editais.id", ondelete="CASCADE"), nullable=False)
    nome = Column(String(150), nullable=False)
    carga_horaria_semanal = Column(Float, default=20.0)
    duracao_bloco_minutos = Column(Integer, default=60)
    bloco_atual_index = Column(Integer, default=0)
    ativo = Column(Boolean, default=True)
    numero_ciclo = Column(Integer, default=1)
    cor_hex = Column(String(20), default="#10b981")
    data_criacao = Column(DateTime, default=utc_now)
    voltas_completas = Column(Integer, default=0)

    edital = relationship("Edital", back_populates="ciclos")
    blocos = relationship("BlocoCiclo", back_populates="ciclo", cascade="all, delete-orphan", order_by="BlocoCiclo.ordem")
    sessoes = relationship("SessaoEstudo", back_populates="ciclo", cascade="all, delete-orphan")

class BlocoCiclo(Base):
    __tablename__ = "blocos_ciclo"

    id = Column(Integer, primary_key=True, index=True)
    ciclo_id = Column(Integer, ForeignKey("ciclos_estudo.id", ondelete="CASCADE"), nullable=False)
    disciplina_id = Column(Integer, ForeignKey("disciplinas.id", ondelete="CASCADE"), nullable=False)
    ordem = Column(Integer, nullable=False)
    duracao_minutos = Column(Integer, default=60)
    concluido = Column(Boolean, default=False)

    ciclo = relationship("CicloEstudos", back_populates="blocos")
    disciplina = relationship("Disciplina", back_populates="blocos")
    sessoes = relationship("SessaoEstudo", back_populates="bloco")
