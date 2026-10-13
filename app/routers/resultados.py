from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime

from app.database import get_db
from app.models.edital import Edital
from app.models.resultado import ResultadoConcurso, ResultadoDisciplina
from app.models.sessao import SessaoEstudo
from app.models.disciplina import Disciplina
from app.models.topico import Topico
from app.schemas.resultado import ResultadoConcursoCreate, ResultadoConcursoResponse, DisciplinaDesempenho, ResultadoDisciplinaResponse

router = APIRouter(prefix="/api/resultados", tags=["Resultados"])

def calcular_estatisticas_edital(db: Session, edital_id: int):
    # Calcular stats a partir das sessoes do edital
    sessoes = db.query(SessaoEstudo).join(Disciplina).filter(Disciplina.edital_id == edital_id).all()
    
    total_minutos = sum(s.tempo_estudado_minutos for s in sessoes)
    total_horas = total_minutos / 60.0
    
    total_questoes_certas = sum(s.qtd_acertos for s in sessoes if s.qtd_acertos)
    total_questoes_erradas = sum(s.qtd_erros for s in sessoes if s.qtd_erros)
    total_questoes = total_questoes_certas + total_questoes_erradas
    
    acerto_geral_perc = (total_questoes_certas / total_questoes * 100) if total_questoes > 0 else 0.0
    data_inicio = min([s.data for s in sessoes]) if sessoes else None
    
    # Desempenho por Disciplina
    disciplinas = db.query(Disciplina).filter(Disciplina.edital_id == edital_id).all()
    desempenho_disciplinas = []
    
    topicos_totais_edital = 0
    topicos_vistos_edital_ids = set()
    
    for disc in disciplinas:
        if disc.categoria == 'REVISAO_ANKI':
            continue
        sessoes_disc = [s for s in sessoes if s.disciplina_id == disc.id]
        minutos_disc = sum(s.tempo_estudado_minutos for s in sessoes_disc)
        q_certas = sum(s.qtd_acertos for s in sessoes_disc if s.qtd_acertos)
        q_erradas = sum(s.qtd_erros for s in sessoes_disc if s.qtd_erros)
        q_totais = q_certas + q_erradas
        acerto_disc = (q_certas / q_totais * 100) if q_totais > 0 else 0.0
        
        # Tópicos vistos: tópicos associados a sessões OU marcados como concluídos
        t_totais = len(disc.topicos)
        topicos_totais_edital += t_totais
        
        vistos_disc = set([s.topico_id for s in sessoes_disc if s.topico_id is not None]).union(
            set([t.id for t in disc.topicos if t.concluido])
        )
        for t_id in vistos_disc:
            topicos_vistos_edital_ids.add(t_id)
            
        cob_disc = (len(vistos_disc) / t_totais * 100) if t_totais > 0 else (100.0 if minutos_disc > 0 else 0.0)
        
        # Contagem de revisões para a disciplina
        revs_disc = sum(1 for s in sessoes_disc if s.is_revisao_anki or (hasattr(s, 'tipo') and s.tipo == 'revisao'))
        
        desempenho_disciplinas.append(DisciplinaDesempenho(
            disciplina_id=disc.id,
            nome=disc.nome,
            percentual_acerto=round(acerto_disc, 2),
            percentual_visto=round(cob_disc, 2),
            horas_dedicadas=round(minutos_disc / 60.0, 2),
            questoes_resolvidas=q_totais,
            revisoes=revs_disc
        ))
    
    cobertura_perc = (len(topicos_vistos_edital_ids) / topicos_totais_edital * 100) if topicos_totais_edital > 0 else (100.0 if total_horas > 0 else 0.0)
    
    return {
        "total_horas": total_horas,
        "total_topicos": topicos_totais_edital,
        "cobertura_edital_perc": round(cobertura_perc, 2),
        "total_questoes": total_questoes,
        "acerto_geral_perc": acerto_geral_perc,
        "data_inicio": data_inicio,
        "desempenho_disciplinas": desempenho_disciplinas,
        "eficiencia_horaria": (total_questoes_certas / total_horas) if total_horas > 0 else 0.0
    }

@router.get("", response_model=List[Dict[str, Any]])
@router.get("/encerrados", response_model=List[Dict[str, Any]])
def listar_resultados_encerrados(db: Session = Depends(get_db)):
    editais_encerrados = db.query(Edital).filter(Edital.encerrado == True).all()
    resultados = []
    for edital in editais_encerrados:
        if edital.resultado:
            res = edital.resultado
            resultados.append({
                "id": res.id,
                "edital_id": edital.id,
                "nome_edital": edital.nome,
                "orgao": edital.orgao,
                "cargo": edital.cargo,
                "nota_final": res.nota_final,
                "nota_corte": res.nota_corte,
                "nota_minima_aprovados": getattr(res, "nota_minima_aprovados", 0.0),
                "nota_maxima_aprovados": getattr(res, "nota_maxima_aprovados", 0.0),
                "total_pontos_prova": getattr(res, "total_pontos_prova", None),
                "posicao": res.posicao,
                "resultado_final": res.resultado_final,
                "data_encerramento": res.data_encerramento,
                "total_horas": res.total_horas,
                "acerto_geral_perc": res.acerto_geral_perc,
                "cobertura_edital_perc": res.cobertura_edital_perc,
                "total_questoes": res.total_questoes,
                "acertos_basicos": res.acertos_basicos,
                "acertos_especificos": res.acertos_especificos
            })
    return resultados

@router.get("/{edital_id}", response_model=ResultadoConcursoResponse)
def obter_resultado(edital_id: int, db: Session = Depends(get_db)):
    edital = db.query(Edital).filter(Edital.id == edital_id).first()
    if not edital:
        raise HTTPException(status_code=404, detail="Edital não encontrado")
    
    stats = calcular_estatisticas_edital(db, edital_id)
    
    if edital.resultado:
        # Ja tem resultado salvo (encerrado)
        res = edital.resultado
        # Preenche acertos_prova_perc de cada disciplina a partir do resultado oficial
        for d in stats["desempenho_disciplinas"]:
            rd = next((x for x in res.disciplinas_resultado if x.disciplina_id == d.disciplina_id), None)
            if rd:
                tot_prova = (rd.acertos or 0) + (rd.erros or 0)
                if tot_prova > 0:
                    d.acertos_prova_perc = round(((rd.acertos or 0) / tot_prova * 100), 2)
                    
        # Atualiza métricas calculadas das sessões
        cob_edital = stats["cobertura_edital_perc"]
        if res.cobertura_edital_perc != cob_edital or res.total_horas != stats["total_horas"]:
            res.cobertura_edital_perc = cob_edital
            res.total_horas = stats["total_horas"]
            res.total_questoes = stats["total_questoes"]
            res.acerto_geral_perc = stats["acerto_geral_perc"]
            db.commit()

        return ResultadoConcursoResponse(
            id=res.id,
            edital_id=res.edital_id,
            nota_final=res.nota_final,
            nota_corte=res.nota_corte,
            total_pontos_prova=getattr(res, "total_pontos_prova", None),
            nota_minima_aprovados=res.nota_minima_aprovados,
            nota_maxima_aprovados=res.nota_maxima_aprovados,
            posicao=res.posicao,
            total_vagas=res.total_vagas,
            resultado_final=res.resultado_final,
            total_horas=res.total_horas,
            total_topicos=res.total_topicos or stats["total_topicos"],
            cobertura_edital_perc=cob_edital,
            total_questoes=res.total_questoes,
            acerto_geral_perc=res.acerto_geral_perc,
            data_inicio=res.data_inicio,
            data_encerramento=res.data_encerramento,
            disciplinas_resultado=[
                ResultadoDisciplinaResponse(
                    id=x.id,
                    resultado_concurso_id=x.resultado_concurso_id,
                    disciplina_id=x.disciplina_id,
                    acertos=x.acertos or 0,
                    erros=x.erros or 0
                ) for x in res.disciplinas_resultado
            ],
            desempenho_disciplinas=stats["desempenho_disciplinas"],
            eficiencia_horaria=(res.acerto_geral_perc / 100 * res.total_questoes / res.total_horas) if res.total_horas > 0 else 0.0
        )
    else:
        # Nao tem resultado ainda, retorna um "draft" com base nas stats atuais
        return ResultadoConcursoResponse(
            id=0,
            edital_id=edital_id,
            nota_final=0.0,
            nota_corte=0.0,
            nota_minima_aprovados=0.0,
            nota_maxima_aprovados=0.0,
            posicao=0,
            total_vagas=0,
            resultado_final="Pendente",
            total_horas=stats["total_horas"],
            total_topicos=stats["total_topicos"],
            cobertura_edital_perc=stats["cobertura_edital_perc"],
            total_questoes=stats["total_questoes"],
            acerto_geral_perc=stats["acerto_geral_perc"],
            data_inicio=stats["data_inicio"],
            data_encerramento=None,
            desempenho_disciplinas=stats["desempenho_disciplinas"],
            eficiencia_horaria=stats["eficiencia_horaria"]
        )

@router.post("/encerrar_preparacao", response_model=ResultadoConcursoResponse)
def encerrar_preparacao_query(edital_id: int, dados: ResultadoConcursoCreate, db: Session = Depends(get_db)):
    return encerrar_preparacao(edital_id, dados, db)

@router.post("/{edital_id}/encerrar", response_model=ResultadoConcursoResponse)
def encerrar_preparacao(edital_id: int, dados: ResultadoConcursoCreate, db: Session = Depends(get_db)):
    edital = db.query(Edital).filter(Edital.id == edital_id).first()
    if not edital:
        raise HTTPException(status_code=404, detail="Edital não encontrado")
        
    stats = calcular_estatisticas_edital(db, edital_id)
    
    resultado = db.query(ResultadoConcurso).filter(ResultadoConcurso.edital_id == edital_id).first()
    if not resultado:
        resultado = ResultadoConcurso(
            edital_id=edital_id,
            nota_final=dados.nota_final,
            nota_corte=dados.nota_corte,
            total_pontos_prova=dados.total_pontos_prova,
            nota_minima_aprovados=dados.nota_minima_aprovados,
            nota_maxima_aprovados=dados.nota_maxima_aprovados,
            posicao=dados.posicao,
            total_vagas=dados.total_vagas,
            resultado_final=dados.resultado_final,
            acertos_basicos=dados.acertos_basicos,
            erros_basicos=dados.erros_basicos,
            nota_basicos=dados.nota_basicos,
            acertos_especificos=dados.acertos_especificos,
            erros_especificos=dados.erros_especificos,
            nota_especificos=dados.nota_especificos,
            nota_discursiva=dados.nota_discursiva,
            total_horas=stats["total_horas"],
            total_topicos=stats["total_topicos"],
            cobertura_edital_perc=stats["cobertura_edital_perc"],
            total_questoes=stats["total_questoes"],
            acerto_geral_perc=stats["acerto_geral_perc"],
            data_inicio=stats["data_inicio"],
            data_encerramento=datetime.utcnow()
        )
        db.add(resultado)
        db.flush()
    else:
        resultado.nota_final = dados.nota_final
        resultado.nota_corte = dados.nota_corte
        resultado.total_pontos_prova = dados.total_pontos_prova
        resultado.nota_minima_aprovados = dados.nota_minima_aprovados
        resultado.nota_maxima_aprovados = dados.nota_maxima_aprovados
        resultado.posicao = dados.posicao
        resultado.total_vagas = dados.total_vagas
        resultado.resultado_final = dados.resultado_final
        resultado.acertos_basicos = dados.acertos_basicos
        resultado.erros_basicos = dados.erros_basicos
        resultado.nota_basicos = dados.nota_basicos
        resultado.acertos_especificos = dados.acertos_especificos
        resultado.erros_especificos = dados.erros_especificos
        resultado.nota_especificos = dados.nota_especificos
        resultado.nota_discursiva = dados.nota_discursiva
        resultado.total_horas = stats["total_horas"]
        resultado.total_topicos = stats["total_topicos"]
        resultado.cobertura_edital_perc = stats["cobertura_edital_perc"]
        resultado.total_questoes = stats["total_questoes"]
        resultado.acerto_geral_perc = stats["acerto_geral_perc"]
        resultado.data_encerramento = datetime.utcnow()

    # Salva o desempenho nas disciplinas da prova oficial
    db.query(ResultadoDisciplina).filter(ResultadoDisciplina.resultado_concurso_id == resultado.id).delete()
    if dados.disciplinas:
        for d in dados.disciplinas:
            rd = ResultadoDisciplina(
                resultado_concurso_id=resultado.id,
                disciplina_id=d.disciplina_id,
                acertos=d.acertos,
                erros=d.erros
            )
            db.add(rd)

    edital.encerrado = True
    db.commit()
    db.refresh(resultado)
    return obter_resultado(edital_id, db)


@router.put("/{edital_id}", response_model=ResultadoConcursoResponse)
def editar_resultado_concurso(edital_id: int, dados: ResultadoConcursoCreate, db: Session = Depends(get_db)):
    edital = db.query(Edital).filter(Edital.id == edital_id).first()
    if not edital:
        raise HTTPException(status_code=404, detail="Edital não encontrado")
        
    resultado = db.query(ResultadoConcurso).filter(ResultadoConcurso.edital_id == edital_id).first()
    if not resultado:
        raise HTTPException(status_code=404, detail="Resultado não encontrado")
        
    resultado.nota_final = dados.nota_final
    resultado.nota_corte = dados.nota_corte
    resultado.total_pontos_prova = dados.total_pontos_prova
    resultado.nota_minima_aprovados = dados.nota_minima_aprovados
    resultado.nota_maxima_aprovados = dados.nota_maxima_aprovados
    resultado.posicao = dados.posicao
    resultado.total_vagas = dados.total_vagas
    resultado.acertos_basicos = dados.acertos_basicos
    resultado.erros_basicos = dados.erros_basicos
    resultado.nota_basicos = dados.nota_basicos
    resultado.acertos_especificos = dados.acertos_especificos
    resultado.erros_especificos = dados.erros_especificos
    resultado.nota_especificos = dados.nota_especificos
    resultado.nota_discursiva = dados.nota_discursiva
    resultado.resultado_final = dados.resultado_final

    # Atualiza as disciplinas
    db.query(ResultadoDisciplina).filter(ResultadoDisciplina.resultado_concurso_id == resultado.id).delete()
    for d_dados in dados.disciplinas:
        d_res = ResultadoDisciplina(
            resultado_concurso_id=resultado.id,
            disciplina_id=d_dados.disciplina_id,
            acertos=d_dados.acertos,
            erros=d_dados.erros
        )
        db.add(d_res)
        
    db.commit()
    db.refresh(resultado)
    return obter_resultado(edital_id, db)

@router.delete("/{edital_id}")
def excluir_resultado_concurso(edital_id: int, db: Session = Depends(get_db)):
    edital = db.query(Edital).filter(Edital.id == edital_id).first()
    if not edital:
        raise HTTPException(status_code=404, detail="Edital não encontrado")
        
    resultado = db.query(ResultadoConcurso).filter(ResultadoConcurso.edital_id == edital_id).first()
    if not resultado:
        raise HTTPException(status_code=404, detail="Resultado não encontrado")
        
    db.delete(resultado)
    edital.encerrado = False
    db.commit()
    return {"message": "Ciclo reaberto com sucesso."}
