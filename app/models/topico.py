from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.database import Base

class Topico(Base):
    __tablename__ = "topicos"

    id = Column(Integer, primary_key=True, index=True)
    disciplina_id = Column(Integer, ForeignKey("disciplinas.id", ondelete="CASCADE"), nullable=False)
    titulo = Column(Text, nullable=False)
    ordem = Column(Integer, default=0)
    concluido = Column(Boolean, default=False)
    mais_cobrado = Column(Boolean, default=False)
    prioridade = Column(Integer, nullable=True)  # 1 (Alta/P1), 2 (Média/P2), 3 (Baixa/P3) ou None

    disciplina = relationship("Disciplina", back_populates="topicos")
    sessoes = relationship("SessaoEstudo", back_populates="topico")
