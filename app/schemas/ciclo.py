from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, ConfigDict
from app.schemas.edital import DisciplinaBase

class BlocoCicloResponse(BaseModel):
    id: int
    ciclo_id: int
    disciplina_id: int
    ordem: int
    duracao_minutos: int
    concluido: bool
    disciplina: DisciplinaBase
    model_config = ConfigDict(from_attributes=True)

class CicloGerarRequest(BaseModel):
    edital_id: int
    nome: Optional[str] = None
    carga_horaria_semanal: float = 20.0
    duracao_bloco_minutos: int = 60

class CicloResponse(BaseModel):
    id: int
    edital_id: int
    nome: str
    carga_horaria_semanal: float
    duracao_bloco_minutos: int
    bloco_atual_index: int
    ativo: bool
    numero_ciclo: int
    cor_hex: str
    voltas_completas: int
    data_criacao: datetime
    blocos: List[BlocoCicloResponse] = []
    model_config = ConfigDict(from_attributes=True)

class AvancarCicloResponse(BaseModel):
    ciclo_id: int
    bloco_anterior_index: int
    bloco_atual_index: int
    bloco_atual: Optional[BlocoCicloResponse] = None
