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
    tipo_data_prova: Optional[str] = "Confirmada"
    nota_corte: Optional[float] = 78.5
    total_vagas: Optional[str] = "35 vagas (28 AC | 7 Cotas)"
    local_prova: Optional[str] = "Maceió - AL"
    formato_prova: Optional[str] = "160 itens + Discursiva"
    status_edital: Optional[str] = "Pós-Edital (Edital Publicado)"
    qtd_questoes_total_prova: Optional[int] = 160
    nota_minima_geral: Optional[float] = 60.0
    nota_minima_basicos: Optional[float] = 50.0
    nota_minima_especificos: Optional[float] = 60.0
    nota_minima_disciplina: Optional[float] = 0.0
    nao_zerar_disciplina: Optional[bool] = True
    fator_penalidade_erro: Optional[float] = 0.0
    meta_conclusao_edital: Optional[float] = 85.0
    dias_disponiveis_semana: Optional[int] = 6
    horas_estudo_dia: Optional[float] = 4.0
    horas_por_topico: Optional[float] = 1.5
    dias_antecedencia_revisao: Optional[int] = 21
    horas_simulado_semana: Optional[float] = 4.0
    ultimo_mapa_ia: Optional[str] = None
    data_mapa_ia: Optional[datetime] = None
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


