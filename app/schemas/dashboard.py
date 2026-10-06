from typing import List, Dict, Any, Optional
from pydantic import BaseModel

class MetricasGerais(BaseModel):
    tempo_total_minutos: int
    tempo_total_horas: float
    total_sessoes: int
    total_questoes: int
    total_acertos: int
    total_erros: int
    percentual_acerto_geral: float

class RendimentoPorDisciplina(BaseModel):
    disciplina_id: int
    disciplina_nome: str
    categoria: str
    tempo_minutos: int
    tempo_horas: float
    total_questoes: int
    acertos: int
    erros: int
    percentual_acerto: float

class RendimentoPorTopico(BaseModel):
    topico_id: int
    topico_titulo: str
    disciplina_nome: str
    total_questoes: int
    acertos: int
    erros: int
    percentual_acerto: float

class RendimentoPorData(BaseModel):
    data: str
    tempo_minutos: int
    total_questoes: int
    acertos: int
    erros: int
    percentual_acerto: float

class DashboardResponse(BaseModel):
    metricas_gerais: MetricasGerais
    rendimento_disciplinas: List[RendimentoPorDisciplina]
    top_topicos_rendimento: List[RendimentoPorTopico]
    rendimento_historico_diario: List[RendimentoPorData]
    rendimento_semanal: List[Dict[str, Any]]
