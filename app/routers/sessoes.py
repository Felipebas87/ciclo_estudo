from typing import List, Optional
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.sessao import SessaoEstudo
from app.models.ciclo import CicloEstudos, BlocoCiclo
from app.models.disciplina import Disciplina
from app.schemas.sessao import SessaoEstudoCreate, SessaoEstudoResponse

router = APIRouter(prefix="/api/sessoes", tags=["Sessões de Estudo & Questões"])

@router.get("", response_model=List[SessaoEstudoResponse])
def listar_sessoes(
    disciplina_id: Optional[int] = Query(None),
    limite: int = Query(50, le=200),
    db: Session = Depends(get_db)
):
    query = db.query(SessaoEstudo)
    if disciplina_id:
        query = query.filter(SessaoEstudo.disciplina_id == disciplina_id)
    return query.order_by(SessaoEstudo.data.desc(), SessaoEstudo.id.desc()).limit(limite).all()

@router.post("", response_model=SessaoEstudoResponse)
def registrar_sessao(dados: SessaoEstudoCreate, db: Session = Depends(get_db)):
    """
    RF04 & RF05: Registro de Check-in de estudo e resolução de questões.
    Calcula percentual de acerto automaticamente e avança a esteira se solicitado.
    """
    disc = db.query(Disciplina).filter(Disciplina.id == dados.disciplina_id).first()
    if not disc:
        raise HTTPException(status_code=404, detail="Disciplina não encontrada")

    # Validação e cálculo das questões
    total_q = dados.qtd_questoes_total
    acertos = dados.qtd_acertos
    erros = dados.qtd_erros

    if total_q == 0 and (acertos > 0 or erros > 0):
        total_q = acertos + erros
    elif total_q > 0 and (acertos + erros) == 0:
        pass
    elif (acertos + erros) > total_q:
        total_q = acertos + erros

    perc_acerto = round((acertos / total_q * 100), 2) if total_q > 0 else 0.0

    # Inferir o ciclo ativo
    ciclo_id_val = None
    volta_ciclo_val = 0
    if dados.bloco_ciclo_id:
        bloco = db.query(BlocoCiclo).filter(BlocoCiclo.id == dados.bloco_ciclo_id).first()
        if bloco:
            ciclo_id_val = bloco.ciclo_id
            ciclo_ativo = db.query(CicloEstudos).filter(CicloEstudos.id == ciclo_id_val).first()
            if ciclo_ativo:
                volta_ciclo_val = ciclo_ativo.voltas_completas
    else:
        # Se nao passou bloco, pega o ciclo ativo do edital da disciplina
        ciclo_ativo = db.query(CicloEstudos).filter(CicloEstudos.edital_id == disc.edital_id, CicloEstudos.ativo == True).first()
        if ciclo_ativo:
            ciclo_id_val = ciclo_ativo.id
            volta_ciclo_val = ciclo_ativo.voltas_completas

    sessao = SessaoEstudo(
        disciplina_id=dados.disciplina_id,
        ciclo_id=ciclo_id_val,
        bloco_ciclo_id=dados.bloco_ciclo_id,
        topico_id=dados.topico_id,
        data=dados.data or date.today(),
        tempo_estudado_minutos=dados.tempo_estudado_minutos,
        qtd_questoes_total=total_q,
        qtd_acertos=acertos,
        qtd_erros=erros,
        percentual_acerto=perc_acerto,
        observacoes=dados.observacoes,
        is_revisao_anki=dados.is_revisao_anki,
        volta_ciclo=volta_ciclo_val
    )
    db.add(sessao)

    # Marca bloco como concluído se informado e avança ciclo
    if dados.bloco_ciclo_id:
        bloco = db.query(BlocoCiclo).filter(BlocoCiclo.id == dados.bloco_ciclo_id).first()
        if bloco:
            bloco.concluido = True
            if dados.avancar_ciclo and bloco.ciclo:
                ciclo = bloco.ciclo
                total_blocos = len(ciclo.blocos)
                if total_blocos > 0:
                    next_index = (ciclo.bloco_atual_index + 1) % total_blocos
                    if next_index == 0:
                        ciclo.voltas_completas += 1
                    ciclo.bloco_atual_index = next_index

    db.commit()
    db.refresh(sessao)
    return sessao


@router.delete("/todas")
def excluir_todas_sessoes(db: Session = Depends(get_db)):
    db.query(SessaoEstudo).delete()
    db.commit()
    return {"mensagem": "Todas as sessões foram excluídas."}

@router.delete("/{sessao_id}")

def excluir_sessao(sessao_id: int, db: Session = Depends(get_db)):
    sessao = db.query(SessaoEstudo).filter(SessaoEstudo.id == sessao_id).first()
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    db.delete(sessao)
    db.commit()
    return {"mensagem": "Sessão excluída com sucesso"}

@router.put("/{sessao_id}", response_model=SessaoEstudoResponse)
def editar_sessao(sessao_id: int, dados: SessaoEstudoCreate, db: Session = Depends(get_db)):
    sessao = db.query(SessaoEstudo).filter(SessaoEstudo.id == sessao_id).first()
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")

    total_q = dados.qtd_questoes_total
    acertos = dados.qtd_acertos
    erros = dados.qtd_erros
    if total_q == 0 and (acertos > 0 or erros > 0):
        total_q = acertos + erros
    elif (acertos + erros) > total_q:
        total_q = acertos + erros
    
    perc_acerto = round((acertos / total_q * 100), 2) if total_q > 0 else 0.0

    sessao.disciplina_id = dados.disciplina_id
    sessao.topico_id = dados.topico_id
    sessao.data = dados.data or date.today()
    sessao.tempo_estudado_minutos = dados.tempo_estudado_minutos
    sessao.qtd_questoes_total = total_q
    sessao.qtd_acertos = acertos
    sessao.qtd_erros = erros
    sessao.percentual_acerto = perc_acerto

    db.commit()
    db.refresh(sessao)
    return sessao
