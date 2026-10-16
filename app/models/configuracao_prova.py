from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Float, DateTime, Text
from app.database import Base

def utc_now():
    return datetime.now(timezone.utc)

class ConfiguracaoPainelProva(Base):
    __tablename__ = "configuracao_painel_prova"

    id = Column(Integer, primary_key=True, index=True)
    concurso = Column(String(200), nullable=True, default="SEFAZ ALAGOAS")
    cargo = Column(String(200), nullable=True, default="Auditor Fiscal da Receita Estadual")
    especialidade = Column(String(200), nullable=True, default="Tecnologia da Informação")
    banca = Column(String(100), nullable=True, default="Cebraspe")
    estilo_banca = Column(String(100), nullable=True, default="Certo / Errado (1 anula 1)")
    data_prova = Column(String(50), nullable=True, default="2026-11-29")
    nota_corte = Column(Float, nullable=True, default=78.5)
    total_vagas = Column(String(100), nullable=True, default="35 vagas (28 AC | 7 Cotas)")
    local_prova = Column(String(100), nullable=True, default="Maceió - AL")
    formato_prova = Column(String(100), nullable=True, default="160 itens + Discursiva")
    status_edital = Column(String(100), nullable=True, default="Pós-Edital (Edital Publicado)")
    marcos_alertados = Column(Text, nullable=True, default="{}")
    data_atualizacao = Column(DateTime, default=utc_now, onupdate=utc_now)
