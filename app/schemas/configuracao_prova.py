from pydantic import BaseModel, ConfigDict
from typing import Optional

class ConfiguracaoPainelProvaBase(BaseModel):
    concurso: Optional[str] = "SEFAZ ALAGOAS"
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
    data_insight_ia: Optional[str] = None

class ConfiguracaoPainelProvaResponse(ConfiguracaoPainelProvaBase):
    id: Optional[int] = 1
    model_config = ConfigDict(from_attributes=True)

