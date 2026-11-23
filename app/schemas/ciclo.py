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
    disciplina_id: Optional[int] = None
    disciplina_nome: Optional[str] = None
    taxa_acerto_perc: Optional[float] = None
    retencao_estimada_perc: Optional[float] = None
    estagio_revisao: Optional[str] = None
    tecnica_recomendada: Optional[str] = None
    eh_revisao_anki: bool = False
    ultima_observacao: Optional[str] = None
    ultima_observacao_data: Optional[str] = None
    ultima_observacao_sessao_id: Optional[int] = None

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
    config_ciclo_json: Optional[str] = None
    blocos: List[BlocoCicloResponse] = []
    model_config = ConfigDict(from_attributes=True)

class BlocoConfigItem(BaseModel):
    disciplina_id: int
    duracao_minutos: int = 60

class AlternanciaDisciplinasItem(BaseModel):
    disc_a_id: int
    disc_b_id: int

class CicloConfigurarRequest(BaseModel):
    itens: List[BlocoConfigItem]
    qtd_revisoes_anki: int = 1
    duracao_revisao_anki: int = 30
    alternancias: List[AlternanciaDisciplinasItem] = []

class AvancarCicloResponse(BaseModel):
    ciclo_id: int
    bloco_anterior_index: int
    bloco_atual_index: int
    bloco_atual: Optional[BlocoCicloResponse] = None
