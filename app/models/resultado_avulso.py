from sqlalchemy import Column, Integer, String, Float
from app.database import Base

class ResultadoAvulsoDB(Base):
    __tablename__ = "resultados_avulsos"

    id = Column(Integer, primary_key=True, index=True)
    nome_prova = Column(String, nullable=False)
    banca = Column(String, nullable=True)
    data_prova = Column(String, nullable=True)
    nota_final = Column(Float, nullable=False)
    nota_corte = Column(Float, nullable=True)
    total_pontos_prova = Column(Float, nullable=True)
    acertos_basicos = Column(Integer, nullable=True)
    erros_basicos = Column(Integer, nullable=True)
    nota_basicos = Column(Float, nullable=True)
    acertos_especificos = Column(Integer, nullable=True)
    erros_especificos = Column(Integer, nullable=True)
    nota_especificos = Column(Float, nullable=True)
    nota_discursiva = Column(Float, nullable=True)
    posicao = Column(Integer, nullable=True)
    resultado_final = Column(String, nullable=False)
