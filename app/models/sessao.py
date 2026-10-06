from datetime import date, datetime, timezone
from sqlalchemy import Column, Integer, Float, Date, DateTime, Text, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from app.database import Base

def utc_now():
    return datetime.now(timezone.utc)

class SessaoEstudo(Base):
    __tablename__ = "sessoes_estudo"

    id = Column(Integer, primary_key=True, index=True)
    ciclo_id = Column(Integer, ForeignKey("ciclos_estudo.id", ondelete="SET NULL"), nullable=True)
    bloco_ciclo_id = Column(Integer, ForeignKey("blocos_ciclo.id", ondelete="SET NULL"), nullable=True)
    disciplina_id = Column(Integer, ForeignKey("disciplinas.id", ondelete="CASCADE"), nullable=False)
    topico_id = Column(Integer, ForeignKey("topicos.id", ondelete="SET NULL"), nullable=True)
    
    data = Column(Date, default=date.today, nullable=False)
    data_criacao = Column(DateTime, default=utc_now)
    tempo_estudado_minutos = Column(Integer, default=60)
    qtd_questoes_total = Column(Integer, default=0)
    qtd_acertos = Column(Integer, default=0)
    qtd_erros = Column(Integer, default=0)
    percentual_acerto = Column(Float, default=0.0)
    observacoes = Column(Text, nullable=True)
    is_revisao_anki = Column(Boolean, default=False)
    volta_ciclo = Column(Integer, default=0)

    ciclo = relationship("CicloEstudos", back_populates="sessoes")
    bloco = relationship("BlocoCiclo", back_populates="sessoes")
    disciplina = relationship("Disciplina", back_populates="sessoes")
    topico = relationship("Topico", back_populates="sessoes")
