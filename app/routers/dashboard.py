from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.services.dashboard_service import (
    get_matriz_semanal,
    get_calendario_estudos,
    get_edital_verticalizado
)

from app.models.sessao import SessaoEstudo
from app.models.disciplina import Disciplina
from sqlalchemy import func

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])

@router.get("")
def get_dashboard_geral(db: Session = Depends(get_db)):
    # Estatísticas globais do usuário
    sessoes = db.query(SessaoEstudo).all()
    tempo_total_minutos = sum((s.tempo_estudado_minutos or 0) for s in sessoes)
    total_sessoes = len(sessoes)
    total_questoes = sum((s.qtd_questoes_total or 0) for s in sessoes)
    total_acertos = sum((s.qtd_acertos or 0) for s in sessoes)
    total_erros = sum((s.qtd_erros or 0) for s in sessoes)
    perc = round((total_acertos / total_questoes * 100), 1) if total_questoes > 0 else 0.0

    metricas_gerais = {
        "tempo_total_minutos": tempo_total_minutos,
        "tempo_total_horas": round(tempo_total_minutos / 60, 1),
        "total_sessoes": total_sessoes,
        "total_questoes": total_questoes,
        "total_acertos": total_acertos,
        "total_erros": total_erros,
        "percentual_acerto_geral": perc
    }

    # Rendimento por Disciplina
    rendimento_disciplinas = []
    disciplinas = db.query(Disciplina).all()
    for d in disciplinas:
        if d.categoria == 'REVISAO_ANKI':
            continue
        sd = [s for s in sessoes if s.disciplina_id == d.id]
        if not sd: continue
        t = sum((s.tempo_estudado_minutos or 0) for s in sd)
        q = sum((s.qtd_questoes_total or 0) for s in sd)
        a = sum((s.qtd_acertos or 0) for s in sd)
        p = round((a / q * 100), 1) if q > 0 else 0.0
        rendimento_disciplinas.append({
            "disciplina_id": d.id,
            "disciplina_nome": d.nome,
            "tempo_horas": round(t / 60, 1),
            "total_questoes": q,
            "acertos": a,
            "percentual_acerto": p
        })

    # Historico Diario (Mock simplificado, mas atende aos graficos)
    diario = {}
    for s in sessoes:
        data_str = s.data.isoformat()
        if data_str not in diario:
            diario[data_str] = {"c": 0, "q": 0}
        diario[data_str]["c"] += (s.qtd_acertos or 0)
        diario[data_str]["q"] += (s.qtd_questoes_total or 0)
    
    historico = []
    for d_str in sorted(diario.keys()):
        p = round((diario[d_str]["c"] / diario[d_str]["q"] * 100), 1) if diario[d_str]["q"] > 0 else 0
        historico.append({
            "data": d_str,
            "percentual_acerto": p
        })

    return {
        "metricas_gerais": metricas_gerais,
        "rendimento_disciplinas": rendimento_disciplinas,
        "top_topicos_rendimento": [],
        "rendimento_historico_diario": historico,
        "rendimento_semanal": []
    }

@router.get("/matriz-semanal")
def matriz_semanal(edital_id: int = Query(...), db: Session = Depends(get_db)):
    return get_matriz_semanal(db, edital_id)

@router.get("/calendario-estudos")
def calendario_estudos(edital_id: int = Query(...), dias: int = Query(30), db: Session = Depends(get_db)):
    return get_calendario_estudos(db, edital_id, dias)

@router.get("/edital-verticalizado")
def edital_verticalizado(edital_id: int = Query(...), db: Session = Depends(get_db)):
    return get_edital_verticalizado(db, edital_id)
