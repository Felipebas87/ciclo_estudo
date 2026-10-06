from sqlalchemy import Column, Integer, String, Float, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from app.database import Base

class Disciplina(Base):
    __tablename__ = "disciplinas"

    id = Column(Integer, primary_key=True, index=True)
    edital_id = Column(Integer, ForeignKey("editais.id", ondelete="CASCADE"), nullable=False)
    nome = Column(String(150), nullable=False)
    categoria = Column(String(50), default="TEORICA_DIREITO")  # EXATAS_LOGICA ou TEORICA_DIREITO
    grupo_conhecimento = Column(String(50), default="BASICOS")  # BASICOS ou ESPECIFICOS
    peso_prova = Column(Float, default=1.0)
    relevancia_dificuldade = Column(Integer, default=3)  # Escala 1 a 5
    incluir_no_ciclo = Column(Boolean, default=False)
    qtd_questoes_prova = Column(Integer, nullable=True)

    edital = relationship("Edital", back_populates="disciplinas")
    topicos = relationship("Topico", back_populates="disciplina", cascade="all, delete-orphan")
    blocos = relationship("BlocoCiclo", back_populates="disciplina", cascade="all, delete-orphan")
    sessoes = relationship("SessaoEstudo", back_populates="disciplina", cascade="all, delete-orphan")
