from sqlalchemy import Column, Integer, String, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base

class Topico(Base):
    __tablename__ = "topicos"

    id = Column(Integer, primary_key=True, index=True)
    disciplina_id = Column(Integer, ForeignKey("disciplinas.id", ondelete="CASCADE"), nullable=False)
    titulo = Column(String(300), nullable=False)
    ordem = Column(Integer, default=0)
    concluido = Column(Boolean, default=False)

    disciplina = relationship("Disciplina", back_populates="topicos")
    sessoes = relationship("SessaoEstudo", back_populates="topico")
