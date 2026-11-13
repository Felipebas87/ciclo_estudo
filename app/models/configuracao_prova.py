from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Float, DateTime, Text, Boolean
from app.database import Base

def utc_now():
    return datetime.now(timezone.utc)

class ConfiguracaoPainelProva(Base):
    __tablename__ = "configuracao_painel_prova"

    id = Column(Integer, primary_key=True, index=True)
    concurso = Column(String(200), nullable=True, default="SEFAZ ALAGOAS")
    area_concurso = Column(String(100), nullable=True, default="Fiscal")
    cargo = Column(String(200), nullable=True, default="Auditor Fiscal da Receita Estadual")
    especialidade = Column(String(200), nullable=True, default="Tecnologia da Informação")
    banca = Column(String(100), nullable=True, default="Cebraspe")
    estilo_banca = Column(String(100), nullable=True, default="Certo / Errado (1 anula 1)")
    data_prova = Column(String(50), nullable=True, default="2026-11-29")
    tipo_data_prova = Column(String(50), nullable=True, default="Confirmada")
    nota_corte = Column(Float, nullable=True, default=78.5)
    total_vagas = Column(String(100), nullable=True, default="35 vagas (28 AC | 7 Cotas)")
    local_prova = Column(String(100), nullable=True, default="Maceió - AL")
    formato_prova = Column(String(100), nullable=True, default="160 itens + Discursiva")
    status_edital = Column(String(100), nullable=True, default="Pós-Edital (Edital Publicado)")

    # Parâmetros do Mapa da Aprovação (Critérios Eliminatórios & Gestão Temporal)
    qtd_questoes_total_prova = Column(Integer, nullable=True, default=160)
    nota_minima_geral = Column(Float, nullable=True, default=60.0)
    nota_minima_basicos = Column(Float, nullable=True, default=50.0)
    nota_minima_especificos = Column(Float, nullable=True, default=60.0)
    nota_minima_disciplina = Column(Float, nullable=True, default=0.0)
    nao_zerar_disciplina = Column(Boolean, nullable=True, default=True)
    fator_penalidade_erro = Column(Float, nullable=True, default=0.0)
    meta_conclusao_edital = Column(Float, nullable=True, default=85.0)
    dias_disponiveis_semana = Column(Integer, nullable=True, default=6)
    horas_estudo_dia = Column(Float, nullable=True, default=4.0)
    horas_por_topico = Column(Float, nullable=True, default=1.5)
    dias_antecedencia_revisao = Column(Integer, nullable=True, default=21)
    horas_simulado_semana = Column(Float, nullable=True, default=4.0)
    ultimo_mapa_ia = Column(Text, nullable=True)
    data_mapa_ia = Column(DateTime, nullable=True)

    marcos_alertados = Column(Text, nullable=True, default="{}")
    ultimo_insight_ia = Column(Text, nullable=True)
    data_insight_ia = Column(DateTime, nullable=True)
    gemini_api_key = Column(String(255), nullable=True)
    tec_email = Column(String(150), nullable=True, default="fbasantos10@gmail.com")
    tec_senha = Column(String(200), nullable=True)
    tec_pasta_padrao = Column(String(150), nullable=True, default="Sefaz Alagoas Auditor TI")
    data_atualizacao = Column(DateTime, default=utc_now, onupdate=utc_now)


