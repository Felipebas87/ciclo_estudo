from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base

class ResultadoDisciplina(Base):
    __tablename__ = "resultados_disciplinas"

    id = Column(Integer, primary_key=True, index=True)
    resultado_concurso_id = Column(Integer, ForeignKey("resultados_concurso.id", ondelete="CASCADE"), nullable=False)
    disciplina_id = Column(Integer, ForeignKey("disciplinas.id", ondelete="CASCADE"), nullable=False)
    acertos = Column(Integer, default=0)
    erros = Column(Integer, default=0)

    resultado_concurso = relationship("ResultadoConcurso", back_populates="disciplinas_resultado")
    disciplina = relationship("Disciplina")

class ResultadoConcurso(Base):
    __tablename__ = "resultados_concurso"

    id = Column(Integer, primary_key=True, index=True)
    edital_id = Column(Integer, ForeignKey("editais.id", ondelete="CASCADE"), nullable=False, unique=True)
    
    # Entradas do Usuário
    nota_final = Column(Float, nullable=False)
    nota_corte = Column(Float, nullable=False)
    total_pontos_prova = Column(Float, nullable=True)
    nota_minima_aprovados = Column(Float, nullable=False)
    nota_maxima_aprovados = Column(Float, nullable=False)
    posicao = Column(Integer, nullable=False)
    total_vagas = Column(Integer, nullable=False)
    
    # Detalhamento de Prova
    acertos_basicos = Column(Integer, default=0)
    erros_basicos = Column(Integer, default=0)
    nota_basicos = Column(Float, default=0.0)
    acertos_especificos = Column(Integer, default=0)
    erros_especificos = Column(Integer, default=0)
    nota_especificos = Column(Float, default=0.0)
    nota_discursiva = Column(Float, default=0.0)
    resultado_final = Column(String(50), nullable=False) # Aprovado, Reprovado, Lista de Espera
    
    # Dados Estatísticos Consolidados no Momento do Encerramento
    total_horas = Column(Float, default=0.0)
    total_topicos = Column(Integer, default=0)
    cobertura_edital_perc = Column(Float, default=0.0)
    total_questoes = Column(Integer, default=0)
    acerto_geral_perc = Column(Float, default=0.0)
    data_inicio = Column(DateTime, nullable=True)
    data_encerramento = Column(DateTime, default=datetime.utcnow)

    edital = relationship("Edital", back_populates="resultado")
    disciplinas_resultado = relationship("ResultadoDisciplina", back_populates="resultado_concurso", cascade="all, delete-orphan")
