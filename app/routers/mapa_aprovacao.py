from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.configuracao_prova import ConfiguracaoPainelProva
from app.models.disciplina import Disciplina
from app.services.mapa_aprovacao_service import (
    calcular_mapa_aprovacao,
    gerar_analise_ia_mapa_aprovacao
)
from app.routers.ia_insights import obter_chave_gemini

router = APIRouter(prefix="/api/mapa-aprovacao", tags=["Mapa da Aprovação"])


class DisciplinaPesoItem(BaseModel):
    id: int
    peso_prova: Optional[float] = None
    qtd_questoes_prova: Optional[int] = None
    grupo_conhecimento: Optional[str] = None


class ConfiguracaoMapaPayload(BaseModel):
    edital_id: Optional[int] = None
    concurso: Optional[str] = None
    area_concurso: Optional[str] = None
    cargo: Optional[str] = None
    especialidade: Optional[str] = None
    banca: Optional[str] = None
    estilo_banca: Optional[str] = None
    data_prova: Optional[str] = None
    tipo_data_prova: Optional[str] = None
    nota_corte: Optional[float] = None
    nota_minima_geral: Optional[float] = None
    nota_minima_basicos: Optional[float] = None
    nota_minima_especificos: Optional[float] = None
    nota_minima_disciplina: Optional[float] = None
    nao_zerar_disciplina: Optional[bool] = None
    fator_penalidade_erro: Optional[float] = None
    meta_conclusao_edital: Optional[float] = None
    dias_disponiveis_semana: Optional[int] = None
    horas_estudo_dia: Optional[float] = None
    horas_por_topico: Optional[float] = None
    dias_antecedencia_revisao: Optional[int] = None
    horas_simulado_semana: Optional[float] = None
    disciplinas: Optional[List[DisciplinaPesoItem]] = None


@router.get("")
async def obter_mapa_aprovacao(
    edital_id: Optional[int] = Query(None),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    mapa = calcular_mapa_aprovacao(db, edital_id)
    if "erro" in mapa:
        return mapa
    config = db.query(ConfiguracaoPainelProva).first()
    chave_ativa = obter_chave_gemini(config)
    analise_atual = mapa.get("analise_ia") or {}
    origem_atual = str(analise_atual.get("modelo_origem", ""))
    if chave_ativa and "Google Gemini" not in origem_atual:
        try:
            nova_ia = await gerar_analise_ia_mapa_aprovacao(db, edital_id)
            if isinstance(nova_ia, dict) and "Google Gemini" in str(nova_ia.get("modelo_origem", "")):
                mapa = calcular_mapa_aprovacao(db, edital_id)
        except Exception as e:
            print(f"[MAPA APROVACAO] Aviso ao atualizar parecer IA automático: {e}")
    return mapa


@router.put("/configurar")
def salvar_configuracao_mapa(
    payload: ConfiguracaoMapaPayload,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    config = db.query(ConfiguracaoPainelProva).first()
    if not config:
        config = ConfiguracaoPainelProva(id=1)
        db.add(config)

    campos_config = [
        "concurso", "area_concurso", "cargo", "especialidade", "banca", "estilo_banca",
        "data_prova", "tipo_data_prova", "nota_corte",
        "nota_minima_geral", "nota_minima_basicos", "nota_minima_especificos",
        "nota_minima_disciplina", "nao_zerar_disciplina", "fator_penalidade_erro",
        "meta_conclusao_edital", "dias_disponiveis_semana", "horas_estudo_dia",
        "horas_por_topico", "dias_antecedencia_revisao", "horas_simulado_semana"
    ]
    dados_dict = payload.model_dump(exclude_unset=True)
    for campo in campos_config:
        if campo in dados_dict and dados_dict[campo] is not None:
            setattr(config, campo, dados_dict[campo])

    if payload.disciplinas:
        for item in payload.disciplinas:
            disc = db.query(Disciplina).filter(Disciplina.id == item.id).first()
            if disc:
                if item.peso_prova is not None:
                    disc.peso_prova = max(0.1, float(item.peso_prova))
                if item.qtd_questoes_prova is not None:
                    disc.qtd_questoes_prova = max(0, int(item.qtd_questoes_prova))
                if item.grupo_conhecimento in ("BASICOS", "ESPECIFICOS"):
                    disc.grupo_conhecimento = item.grupo_conhecimento

    db.commit()
    db.refresh(config)
    return calcular_mapa_aprovacao(db, payload.edital_id)


@router.post("/analisar-ia")
async def analisar_mapa_com_ia(
    edital_id: Optional[int] = Query(None),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    return await gerar_analise_ia_mapa_aprovacao(db, edital_id)
