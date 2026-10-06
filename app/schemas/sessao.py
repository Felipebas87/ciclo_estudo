from typing import Optional
from datetime import date, datetime
from pydantic import BaseModel, ConfigDict, Field

class SessaoEstudoCreate(BaseModel):
    disciplina_id: int
    bloco_ciclo_id: Optional[int] = None
    topico_id: Optional[int] = None
    data: Optional[date] = None
    tempo_estudado_minutos: int = Field(default=60, ge=1)
    qtd_questoes_total: int = Field(default=0, ge=0)
    qtd_acertos: int = Field(default=0, ge=0)
    qtd_erros: int = Field(default=0, ge=0)
    observacoes: Optional[str] = None
    avancar_ciclo: bool = True
    is_revisao_anki: bool = False

class SessaoEstudoResponse(BaseModel):
    id: int
    ciclo_id: Optional[int] = None
    disciplina_id: int
    bloco_ciclo_id: Optional[int] = None
    topico_id: Optional[int] = None
    data: date
    data_criacao: datetime
    tempo_estudado_minutos: int
    qtd_questoes_total: int
    qtd_acertos: int
    qtd_erros: int
    percentual_acerto: float
    observacoes: Optional[str] = None
    is_revisao_anki: bool = False
    volta_ciclo: int = 0
    model_config = ConfigDict(from_attributes=True)
