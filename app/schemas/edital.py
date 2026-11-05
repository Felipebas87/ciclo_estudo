from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, ConfigDict

class TopicoBase(BaseModel):
    titulo: str
    ordem: int = 0
    concluido: bool = False
    mais_cobrado: bool = False
    prioridade: Optional[int] = None
    ordem_trilha: Optional[int] = None
    motivo_ia: Optional[str] = None

class TopicoCreate(TopicoBase):
    pass

class TopicoUpdate(BaseModel):
    titulo: Optional[str] = None
    ordem: Optional[int] = None
    concluido: Optional[bool] = None
    mais_cobrado: Optional[bool] = None
    prioridade: Optional[int] = None
    ordem_trilha: Optional[int] = None
    motivo_ia: Optional[str] = None

class TopicoResponse(TopicoBase):
    id: int
    disciplina_id: int
    tec_vinculo: Optional[dict] = None
    model_config = ConfigDict(from_attributes=True)

class DisciplinaBase(BaseModel):
    nome: str
    categoria: str = "TEORICA_DIREITO"
    grupo_conhecimento: str = "BASICOS"
    peso_prova: float = 1.0
    relevancia_dificuldade: int = 3
    incluir_no_ciclo: bool = False
    qtd_questoes_prova: Optional[int] = None
    ordem_trilha: Optional[int] = None
    pre_requisitos_ia: Optional[str] = None
    justificativa_trilha_ia: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)

class DisciplinaCreate(DisciplinaBase):
    topicos: Optional[List[TopicoCreate]] = None

class DisciplinaUpdate(BaseModel):
    nome: Optional[str] = None
    categoria: Optional[str] = None
    grupo_conhecimento: Optional[str] = None
    peso_prova: Optional[float] = None
    relevancia_dificuldade: Optional[int] = None
    incluir_no_ciclo: Optional[bool] = None
    qtd_questoes_prova: Optional[int] = None
    ordem_trilha: Optional[int] = None
    pre_requisitos_ia: Optional[str] = None
    justificativa_trilha_ia: Optional[str] = None

class DisciplinaResponse(DisciplinaBase):
    id: int
    edital_id: int
    topicos: List[TopicoResponse] = []
    model_config = ConfigDict(from_attributes=True)

class EditalBase(BaseModel):
    nome: str
    orgao: Optional[str] = None
    cargo: Optional[str] = None

class EditalTextoPuro(BaseModel):
    nome: str
    texto_basicos: str
    texto_especificos: str

class EditalCreate(EditalBase):
    disciplinas: Optional[List[DisciplinaCreate]] = None

class EditalResponse(EditalBase):
    id: int
    ativo: bool
    data_criacao: datetime
    ia_trilha_analisada: Optional[bool] = False
    ia_trilha_data: Optional[datetime] = None
    ia_trilha_banca: Optional[str] = None
    ia_trilha_resumo: Optional[str] = None
    disciplinas: List[DisciplinaResponse] = []
    model_config = ConfigDict(from_attributes=True)
