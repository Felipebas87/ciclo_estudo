from pydantic import BaseModel, ConfigDict
from typing import Optional, Any
from datetime import datetime

class ConfiguracaoPainelProvaBase(BaseModel):
    concurso: Optional[str] = "SEFAZ ALAGOAS"
    area_concurso: Optional[str] = "Fiscal"
    cargo: Optional[str] = "Auditor Fiscal da Receita Estadual"
    especialidade: Optional[str] = "Tecnologia da Informação"
    banca: Optional[str] = "Cebraspe"
    estilo_banca: Optional[str] = "Certo / Errado (1 anula 1)"
    data_prova: Optional[str] = "2026-11-29"
    nota_corte: Optional[float] = 78.5
    total_vagas: Optional[str] = "35 vagas (28 AC | 7 Cotas)"
    local_prova: Optional[str] = "Maceió - AL"
    formato_prova: Optional[str] = "160 itens + Discursiva"
    status_edital: Optional[str] = "Pós-Edital (Edital Publicado)"
    marcos_alertados: Optional[str] = "{}"
    ultimo_insight_ia: Optional[str] = None
    data_insight_ia: Optional[datetime] = None
    gemini_api_key: Optional[str] = None
    tec_email: Optional[str] = "fbasantos10@gmail.com"
    tec_senha: Optional[str] = None
    tec_pasta_padrao: Optional[str] = "Sefaz Alagoas Auditor TI"

class ConfiguracaoPainelProvaResponse(ConfiguracaoPainelProvaBase):
    id: Optional[int] = 1
    model_config = ConfigDict(from_attributes=True)

