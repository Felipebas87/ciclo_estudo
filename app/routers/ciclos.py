from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, selectinload, joinedload
from app.database import get_db
from app.models.ciclo import CicloEstudos, BlocoCiclo
from app.models.sessao import SessaoEstudo
from app.models.disciplina import Disciplina
from app.models.topico import Topico
from app.models.tec_taxonomia import TopicoEstudoTecDePara
from app.schemas.ciclo import CicloResponse, CicloGerarRequest, AvancarCicloResponse, BlocoCicloResponse, CicloConfigurarRequest
from app.services.ciclo_service import (
    gerar_ciclo_para_edital,
    configurar_ciclo_personalizado,
    aplicar_alternancia_volta_ciclo,
    avancar_bloco_ciclo,
    reparar_progresso_volta_ciclo,
)
from app.services.trilha_ia_service import obter_proximo_topico_trilha_disciplina
from app.services.revisoes_service import mapear_topicos_para_blocos_anki_do_ciclo

router = APIRouter(prefix="/api/ciclos", tags=["Ciclos de Estudo"])

def _ciclo_eager_options():
    return (
        selectinload(CicloEstudos.blocos)
        .joinedload(BlocoCiclo.disciplina)
        .selectinload(Disciplina.topicos)
        .joinedload(Topico.vinculo_tec)
        .joinedload(TopicoEstudoTecDePara.tec_taxonomia)
    )

def _enriquecer_ciclo_com_topicos_trilha(db: Session, ciclo: Optional[CicloEstudos]) -> Optional[CicloEstudos]:
    if not ciclo or not ciclo.blocos:
        return ciclo
    reparar_progresso_volta_ciclo(db, ciclo)
    sessoes = (
        db.query(
            SessaoEstudo.topico_id,
            SessaoEstudo.observacoes,
            SessaoEstudo.data,
            SessaoEstudo.id,
        )
        .join(Disciplina)
        .filter(Disciplina.edital_id == ciclo.edital_id, SessaoEstudo.topico_id != None)
        .order_by(SessaoEstudo.data.desc(), SessaoEstudo.id.desc())
        .all()
    )
    topicos_vistos_ids = set(r[0] for r in sessoes if r[0] is not None)
    ultimas_obs_por_topico = {}
    for top_id, obs_txt, dt_sess, s_id in sessoes:
        if top_id is not None and top_id not in ultimas_obs_por_topico:
            txt_limpo = (obs_txt or "").strip()
            if txt_limpo:
                ultimas_obs_por_topico[top_id] = {
                    "ultima_observacao": txt_limpo,
                    "ultima_observacao_data": dt_sess.isoformat() if dt_sess else None,
                    "ultima_observacao_sessao_id": s_id,
                }
    mapa_anki = mapear_topicos_para_blocos_anki_do_ciclo(db, ciclo)
    for b in ciclo.blocos:
        if b.disciplina and b.disciplina.categoria != "REVISAO_ANKI":
            prox = obter_proximo_topico_trilha_disciplina(b.disciplina, topicos_vistos_ids)
        else:
            prox = mapa_anki.get(b.id)
        if prox and isinstance(prox, dict):
            obs_info = ultimas_obs_por_topico.get(prox.get("id"))
            if obs_info:
                prox["ultima_observacao"] = obs_info["ultima_observacao"]
                prox["ultima_observacao_data"] = obs_info["ultima_observacao_data"]
                prox["ultima_observacao_sessao_id"] = obs_info["ultima_observacao_sessao_id"]
        b.proximo_topico = prox
    return ciclo

@router.get("", response_model=List[CicloResponse])
def listar_ciclos(db: Session = Depends(get_db)):
    ciclos = (
        db.query(CicloEstudos)
        .options(_ciclo_eager_options())
        .order_by(CicloEstudos.data_criacao.desc())
        .all()
    )
    for c in ciclos:
        _enriquecer_ciclo_com_topicos_trilha(db, c)
    return ciclos

@router.get("/ativo", response_model=Optional[CicloResponse])
def obter_ciclo_ativo(db: Session = Depends(get_db)):
    """Retorna o ciclo de estudos atualmente ativo já com o próximo tópico da Trilha IA apontado em cada bloco"""
    ciclo = (
        db.query(CicloEstudos)
        .options(_ciclo_eager_options())
        .filter(CicloEstudos.ativo == True)
        .first()
    )
    return _enriquecer_ciclo_com_topicos_trilha(db, ciclo)

@router.get("/{ciclo_id}", response_model=CicloResponse)
def obter_ciclo(ciclo_id: int, db: Session = Depends(get_db)):
    ciclo = (
        db.query(CicloEstudos)
        .options(_ciclo_eager_options())
        .filter(CicloEstudos.id == ciclo_id)
        .first()
    )
    if not ciclo:
        raise HTTPException(status_code=404, detail="Ciclo não encontrado")
    return _enriquecer_ciclo_com_topicos_trilha(db, ciclo)

@router.post("/gerar", response_model=CicloResponse)
def gerar_ciclo(dados: CicloGerarRequest, db: Session = Depends(get_db)):
    """
    RF03: Geração Automática do Ciclo de Estudos com base em pesos, tópicos, trilha IA e intercalação cognitiva.
    """
    try:
        ciclo = gerar_ciclo_para_edital(
            db=db,
            edital_id=dados.edital_id,
            nome_ciclo=dados.nome,
            carga_horaria_semanal=dados.carga_horaria_semanal,
            duracao_bloco_minutos=dados.duracao_bloco_minutos
        )
        return _enriquecer_ciclo_com_topicos_trilha(db, ciclo)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro interno ao gerar ciclo: {str(e)}")

@router.post("/{ciclo_id}/avancar", response_model=AvancarCicloResponse)
def avancar_bloco(ciclo_id: int, db: Session = Depends(get_db)):
    """
    Avança a esteira circular do ciclo para o próximo bloco.
    """
    ciclo = (
        db.query(CicloEstudos)
        .options(_ciclo_eager_options())
        .filter(CicloEstudos.id == ciclo_id)
        .first()
    )
    if not ciclo:
        raise HTTPException(status_code=404, detail="Ciclo não encontrado")

    total_blocos = len(ciclo.blocos)
    if total_blocos == 0:
        raise HTTPException(status_code=400, detail="Ciclo não possui blocos")

    antigo_index, novo_index = avancar_bloco_ciclo(db, ciclo, marcar_atual_concluido=True)
    db.commit()
    ciclo = (
        db.query(CicloEstudos)
        .options(_ciclo_eager_options())
        .filter(CicloEstudos.id == ciclo_id)
        .first()
    )
    _enriquecer_ciclo_com_topicos_trilha(db, ciclo)

    bloco_atual = ciclo.blocos[novo_index] if novo_index < total_blocos else None

    return AvancarCicloResponse(
        ciclo_id=ciclo.id,
        bloco_anterior_index=antigo_index,
        bloco_atual_index=novo_index,
        bloco_atual=bloco_atual
    )

@router.post("/{ciclo_id}/selecionar-bloco/{ordem_index}")
def selecionar_bloco(ciclo_id: int, ordem_index: int, db: Session = Depends(get_db)):
    """Permite ao usuário pular diretamente para um bloco específico da esteira"""
    ciclo = db.query(CicloEstudos).filter(CicloEstudos.id == ciclo_id).first()
    if not ciclo:
        raise HTTPException(status_code=404, detail="Ciclo não encontrado")
    if ordem_index < 0 or ordem_index >= len(ciclo.blocos):
        raise HTTPException(status_code=400, detail="Índice de bloco inválido")

    ciclo.bloco_atual_index = ordem_index
    db.commit()
    return {"mensagem": "Bloco atualizado", "bloco_atual_index": ordem_index}


@router.put("/{ciclo_id}/configuracao", response_model=CicloResponse)
def configurar_ciclo(ciclo_id: int, dados: CicloConfigurarRequest, db: Session = Depends(get_db)):
    """
    Reconfigura visualmente o ciclo ativo: ordem das disciplinas, quantidade de blocos de Revisão Anki
    e regras de alternância de 2 disciplinas por volta.
    """
    try:
        configurar_ciclo_personalizado(
            db=db,
            ciclo_id=ciclo_id,
            itens=[{"disciplina_id": it.disciplina_id, "duracao_minutos": it.duracao_minutos} for it in dados.itens],
            qtd_revisoes_anki=dados.qtd_revisoes_anki,
            duracao_revisao_anki=dados.duracao_revisao_anki,
            alternancias=[{"disc_a_id": a.disc_a_id, "disc_b_id": a.disc_b_id} for a in dados.alternancias],
        )
        ciclo_atualizado = (
            db.query(CicloEstudos)
            .options(_ciclo_eager_options())
            .filter(CicloEstudos.id == ciclo_id)
            .first()
        )
        return _enriquecer_ciclo_com_topicos_trilha(db, ciclo_atualizado)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao configurar ciclo: {str(e)}")
