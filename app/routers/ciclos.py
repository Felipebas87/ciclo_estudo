from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.ciclo import CicloEstudos, BlocoCiclo
from app.models.sessao import SessaoEstudo
from app.models.disciplina import Disciplina
from app.schemas.ciclo import CicloResponse, CicloGerarRequest, AvancarCicloResponse, BlocoCicloResponse
from app.services.ciclo_service import gerar_ciclo_para_edital
from app.services.trilha_ia_service import obter_proximo_topico_trilha_disciplina

router = APIRouter(prefix="/api/ciclos", tags=["Ciclos de Estudo"])

def _enriquecer_ciclo_com_topicos_trilha(db: Session, ciclo: Optional[CicloEstudos]) -> Optional[CicloEstudos]:
    if not ciclo or not ciclo.blocos:
        return ciclo
    sessoes = (
        db.query(SessaoEstudo.topico_id)
        .join(Disciplina)
        .filter(Disciplina.edital_id == ciclo.edital_id, SessaoEstudo.topico_id != None)
        .all()
    )
    topicos_vistos_ids = set(r[0] for r in sessoes if r[0] is not None)
    for b in ciclo.blocos:
        if b.disciplina and b.disciplina.categoria != "REVISAO_ANKI":
            b.proximo_topico = obter_proximo_topico_trilha_disciplina(b.disciplina, topicos_vistos_ids)
        else:
            b.proximo_topico = None
    return ciclo

@router.get("", response_model=List[CicloResponse])
def listar_ciclos(db: Session = Depends(get_db)):
    ciclos = db.query(CicloEstudos).order_by(CicloEstudos.data_criacao.desc()).all()
    for c in ciclos:
        _enriquecer_ciclo_com_topicos_trilha(db, c)
    return ciclos

@router.get("/ativo", response_model=Optional[CicloResponse])
def obter_ciclo_ativo(db: Session = Depends(get_db)):
    """Retorna o ciclo de estudos atualmente ativo já com o próximo tópico da Trilha IA apontado em cada bloco"""
    ciclo = db.query(CicloEstudos).filter(CicloEstudos.ativo == True).first()
    return _enriquecer_ciclo_com_topicos_trilha(db, ciclo)

@router.get("/{ciclo_id}", response_model=CicloResponse)
def obter_ciclo(ciclo_id: int, db: Session = Depends(get_db)):
    ciclo = db.query(CicloEstudos).filter(CicloEstudos.id == ciclo_id).first()
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
    ciclo = db.query(CicloEstudos).filter(CicloEstudos.id == ciclo_id).first()
    if not ciclo:
        raise HTTPException(status_code=404, detail="Ciclo não encontrado")

    total_blocos = len(ciclo.blocos)
    if total_blocos == 0:
        raise HTTPException(status_code=400, detail="Ciclo não possui blocos")

    antigo_index = ciclo.bloco_atual_index
    novo_index = (antigo_index + 1) % total_blocos
    if novo_index == 0:
        ciclo.voltas_completas += 1
    ciclo.bloco_atual_index = novo_index
    db.commit()
    db.refresh(ciclo)
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
