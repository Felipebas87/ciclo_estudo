from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime

class DisciplinaDesempenho(BaseModel):
    disciplina_id: int
    nome: str
    percentual_acerto: float
    percentual_visto: float
    horas_dedicadas: float
    questoes_resolvidas: int
    revisoes: int = 0
    acertos_prova_perc: float = 0.0

class ResultadoDisciplinaBase(BaseModel):
    disciplina_id: int
    acertos: int
    erros: int

class ResultadoDisciplinaCreate(ResultadoDisciplinaBase):
    pass

class ResultadoDisciplinaResponse(ResultadoDisciplinaBase):
    id: int
    resultado_concurso_id: int

    model_config = ConfigDict(from_attributes=True)

class ResultadoConcursoBase(BaseModel):
    nota_final: float
    nota_corte: float
    total_pontos_prova: Optional[float] = None
    nota_minima_aprovados: float
    nota_maxima_aprovados: float
    posicao: int
    total_vagas: int
    resultado_final: str
    acertos_basicos: int = 0
    erros_basicos: int = 0
    nota_basicos: float = 0.0
    acertos_especificos: int = 0
    erros_especificos: int = 0
    nota_especificos: float = 0.0
    nota_discursiva: float = 0.0

class ResultadoConcursoCreate(ResultadoConcursoBase):
    disciplinas: Optional[List[ResultadoDisciplinaCreate]] = []

class ResultadoConcursoResponse(ResultadoConcursoBase):
    disciplinas_resultado: List[ResultadoDisciplinaResponse] = []
    id: int
    edital_id: int
    total_horas: float
    total_topicos: int
    cobertura_edital_perc: float
    total_questoes: int
    acerto_geral_perc: float
    data_inicio: Optional[datetime]
    data_encerramento: Optional[datetime]
    
    # Extra fields added dynamically by the API
    desempenho_disciplinas: List[DisciplinaDesempenho] = []
    eficiencia_horaria: float = 0.0

    model_config = ConfigDict(from_attributes=True)
