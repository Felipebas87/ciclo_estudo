from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class TecNoTaxonomiaResponse(BaseModel):
    id: int
    tec_id: int
    is_materia: bool = False
    materia_tec_id: Optional[int] = None
    nome: str
    parent_id: Optional[int] = None
    nivel_profundidade: int = 1
    hierarquia_tec: Optional[str] = None
    caminho_completo: str
    slug_url: Optional[str] = None
    total_questoes: int = 0
    ativo: bool = True
    url_assunto: Optional[str] = None
    url_caderno: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class TecVinculoTopicoPayload(BaseModel):
    vinculado: bool = False
    topico_id: int
    tec_taxonomia_id: Optional[int] = None
    tec_id: Optional[int] = None
    is_materia: Optional[bool] = False
    nome_assunto_tec: Optional[str] = None
    caminho_completo: Optional[str] = None
    hierarquia_tec: Optional[str] = None
    tipo_vinculo: Optional[str] = None
    confianca_score: float = 0.0
    validado: bool = False
    total_questoes: int = 0
    banca_nome: Optional[str] = None
    banca_tec_id: Optional[int] = None
    caderno_id: Optional[str] = None
    url_caderno_criado: Optional[str] = None
    pasta_tec_nome: Optional[str] = None
    tem_caderno_gerado: bool = False
    url_tec: str
    url_assunto: str
    url_caderno: str
    url_fallback_busca: str


class TecAssociarCadernoRequest(BaseModel):
    caderno_url_ou_id: str
    pasta_nome: Optional[str] = None


class TecConfigAutenticacaoRequest(BaseModel):
    tec_email: Optional[str] = None
    tec_senha: Optional[str] = None
    tec_pasta_padrao: Optional[str] = None


class TecVincularManualRequest(BaseModel):
    tec_taxonomia_id: int


class TecSincronizarRequest(BaseModel):
    edital_id: Optional[int] = None
    slugs_adicionais: Optional[List[str]] = None
    executar_matching: bool = True
    usar_ia_se_necessario: bool = True
