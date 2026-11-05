from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, ConfigDict
from app.schemas.edital import DisciplinaBase

class TopicoApontadoCiclo(BaseModel):
    id: int
    titulo: str
    ordem: int = 0
    ordem_trilha: Optional[int] = None
    prioridade: Optional[int] = None
    mais_cobrado: bool = False
    motivo_ia: Optional[str] = None
    concluido: bool = False
    visto: bool = False
    tec_vinculo: Optional[Dict[str, Any]] = None

class BlocoCicloResponse(BaseModel):
    id: int
    ciclo_id: int
    disciplina_id: int
    ordem: int
    duracao_minutos: int
    concluido: bool
    disciplina: DisciplinaBase
    proximo_topico: Optional[TopicoApontadoCiclo] = None
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
