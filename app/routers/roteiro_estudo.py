from typing import Optional, Dict, Any, List
from pydantic import BaseModel
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.roteiro_estudo_service import (
    calcular_roteiro_estudo,
    salvar_preferencias_roteiro,
)
from app.services.gamificacao_service import (
    calcular_gamificacao_aluno,
    marcar_medalhas_como_vistas,
    resgatar_desafio_diario_xp,
)

router = APIRouter(prefix="/api/roteiro-estudo", tags=["Roteiro de Estudo"])


class ParametrosRoteiroPayload(BaseModel):
    edital_id: Optional[int] = None
    horas_por_dia: float = 2.0
    dias_por_semana: int = 6
    questoes_por_hora: Optional[float] = None
    data_prova: Optional[str] = None


@router.get("")
def obter_roteiro_estudo(
    edital_id: Optional[int] = Query(None),
    horas_por_dia: Optional[float] = Query(None),
    dias_por_semana: Optional[int] = Query(None),
    questoes_por_hora: Optional[float] = Query(None),
    data_prova: Optional[str] = Query(None),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    return calcular_roteiro_estudo(
        db=db,
        edital_id=edital_id,
        horas_por_dia_override=horas_por_dia,
        dias_por_semana_override=dias_por_semana,
        questoes_por_hora_override=questoes_por_hora,
        data_prova_override=data_prova,
    )


@router.put("/parametros")
def atualizar_parametros_roteiro(
    payload: ParametrosRoteiroPayload,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    salvar_preferencias_roteiro(
        db=db,
        horas_por_dia=payload.horas_por_dia,
        dias_por_semana=payload.dias_por_semana,
        questoes_por_hora=payload.questoes_por_hora,
        data_prova=payload.data_prova,
    )
    return calcular_roteiro_estudo(
        db=db,
        edital_id=payload.edital_id,
        horas_por_dia_override=payload.horas_por_dia,
        dias_por_semana_override=payload.dias_por_semana,
        questoes_por_hora_override=payload.questoes_por_hora,
        data_prova_override=payload.data_prova,
    )


class MarcarMedalhasVistasPayload(BaseModel):
    medalha_ids: List[str]


@router.get("/gamificacao")
def obter_gamificacao_endpoint(
    edital_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    return calcular_gamificacao_aluno(db=db, edital_id=edital_id)


@router.post("/gamificacao/marcar-vistas")
def marcar_medalhas_vistas_endpoint(
    payload: MarcarMedalhasVistasPayload,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    return marcar_medalhas_como_vistas(db=db, medalha_ids=payload.medalha_ids)


@router.post("/gamificacao/resgatar-desafio")
def resgatar_desafio_diario_endpoint(
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    return resgatar_desafio_diario_xp(db=db)
