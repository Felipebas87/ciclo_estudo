from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, or_

from app.database import get_db
from app.models.edital import Edital
from app.models.topico import Topico
from app.models.configuracao_prova import ConfiguracaoPainelProva
from app.models.tec_taxonomia import TecTaxonomia, TopicoEstudoTecDePara
from app.schemas.tec_integracao import (
    TecNoTaxonomiaResponse,
    TecVinculoTopicoPayload,
    TecVincularManualRequest,
    TecSincronizarRequest,
    TecAssociarCadernoRequest,
    TecConfigAutenticacaoRequest,
)
from app.services.tec_scraper_service import sincronizar_taxonomia_tec, TEC_BASE_URL
from app.services.tec_matching_service import (
    executar_matching_edital,
    montar_dados_vinculo_topico,
    normalizar_texto_topico,
    expandir_termos_topico,
    obter_slugs_tec_para_disciplina,
    calcular_similaridade_topico_no_tec,
    _preparar_catalogo_nos_tec,
)
from app.services.tec_caderno_automator import (
    obter_status_sessao_tec,
    iniciar_login_interativo_tec,
    autenticar_por_credenciais_tec,
    associar_caderno_manualmente,
    gerar_caderno_topico_playwright,
)

router = APIRouter(prefix="/api/tec", tags=["Integração TEC Concursos"])


def _serializar_no_tec(no: TecTaxonomia) -> Dict[str, Any]:
    slug_limpo = (no.slug_url or "").lstrip("/")
    url_assunto = f"{TEC_BASE_URL}/materias/{slug_limpo}" if slug_limpo else f"{TEC_BASE_URL}/materias"
    if no.is_materia:
        url_caderno = f"{TEC_BASE_URL}/questoes/cadernos/novo/?materia_ids[]={no.tec_id}"
    else:
        url_caderno = f"{TEC_BASE_URL}/questoes/cadernos/novo/?assunto_ids[]={no.tec_id}"
    return {
        "id": no.id,
        "tec_id": no.tec_id,
        "is_materia": bool(no.is_materia),
        "materia_tec_id": no.materia_tec_id,
        "nome": no.nome,
        "parent_id": no.parent_id,
        "nivel_profundidade": no.nivel_profundidade,
        "hierarquia_tec": no.hierarquia_tec,
        "caminho_completo": no.caminho_completo,
        "slug_url": no.slug_url,
        "total_questoes": no.total_questoes or 0,
        "ativo": bool(no.ativo),
        "url_assunto": url_assunto,
        "url_caderno": url_caderno,
    }


@router.get("/estatisticas")
def obter_estatisticas_tec(
    edital_id: Optional[int] = Query(None),
    db: Session = Depends(get_db)
):
    total_materias = db.query(func.count(TecTaxonomia.id)).filter(
        TecTaxonomia.is_materia == True,
        TecTaxonomia.ativo == True
    ).scalar() or 0
    total_assuntos = db.query(func.count(TecTaxonomia.id)).filter(
        TecTaxonomia.is_materia == False,
        TecTaxonomia.ativo == True
    ).scalar() or 0
    ultima_sync = db.query(func.max(TecTaxonomia.updated_at)).scalar()

    query_vinculos = db.query(TopicoEstudoTecDePara)
    if edital_id is not None:
        query_vinculos = (
            query_vinculos
            .join(Topico, Topico.id == TopicoEstudoTecDePara.topico_id)
            .join(Topico.disciplina)
            .filter_by(edital_id=edital_id)
        )
    vinculos = query_vinculos.all()
    total_vinculos = len(vinculos)
    manuais = sum(1 for v in vinculos if v.tipo_vinculo == "MANUAL")
    exatos = sum(1 for v in vinculos if v.tipo_vinculo == "AUTOMATICO_EXATO")
    ia = sum(1 for v in vinculos if v.tipo_vinculo == "AUTOMATICO_IA")
    fuzzy = sum(1 for v in vinculos if v.tipo_vinculo == "AUTOMATICO_FUZZY")
    alta_confianca = sum(1 for v in vinculos if (v.confianca_score or 0.0) >= 0.85 or v.tipo_vinculo == "MANUAL")

    return {
        "total_materias": total_materias,
        "total_assuntos": total_assuntos,
        "total_nos": total_materias + total_assuntos,
        "ultima_sincronizacao": ultima_sync.isoformat() if ultima_sync else None,
        "total_vinculos": total_vinculos,
        "vinculos_manuais": manuais,
        "vinculos_exatos": exatos,
        "vinculos_ia": ia,
        "vinculos_fuzzy": fuzzy,
        "alta_confianca": alta_confianca,
    }


@router.get("/materias", response_model=List[TecNoTaxonomiaResponse])
def listar_materias_tec(db: Session = Depends(get_db)):
    """Lista todas as disciplinas/matérias (Nível 1) sincronizadas na árvore do TEC Concursos."""
    materias = (
        db.query(TecTaxonomia)
        .filter(TecTaxonomia.is_materia == True, TecTaxonomia.ativo == True)
        .order_by(TecTaxonomia.nome.asc())
        .all()
    )
    return [_serializar_no_tec(m) for m in materias]


@router.get("/arvore", response_model=List[TecNoTaxonomiaResponse])
def buscar_na_arvore_tec(
    q: Optional[str] = Query(None, description="Texto para buscar no nome ou caminho completo"),
    materia_tec_id: Optional[int] = Query(None, description="Filtrar por ID da matéria no TEC"),
    disciplina_nome: Optional[str] = Query(None, description="Nome da disciplina do edital para priorizar matérias correlatas"),
    apenas_assuntos: bool = Query(False, description="Se True, oculta os nós raiz de matéria"),
    limite: int = Query(60, ge=1, le=300),
    db: Session = Depends(get_db)
):
    """
    Endpoint de busca na árvore `tec_taxonomia` para o Modal de Validação/Associação Manual.
    Suporta busca sem acento e prioriza assuntos com mais questões.
    """
    query = db.query(TecTaxonomia).filter(TecTaxonomia.ativo == True)
    if apenas_assuntos:
        query = query.filter(TecTaxonomia.is_materia == False)
    if materia_tec_id is not None:
        query = query.filter(TecTaxonomia.materia_tec_id == materia_tec_id)
    elif disciplina_nome and not q:
        slugs = obter_slugs_tec_para_disciplina(disciplina_nome)
        if slugs:
            filtros_slug = [TecTaxonomia.slug_url.like(f"{s}%") for s in slugs]
            query = query.filter(or_(*filtros_slug))

    if q and q.strip():
        termo = q.strip()
        palavras = [p for p in termo.split() if len(p) >= 2]
        for pal in palavras[:5]:
            query = query.filter(
                or_(
                    TecTaxonomia.caminho_completo.ilike(f"%{pal}%"),
                    TecTaxonomia.nome.ilike(f"%{pal}%"),
                    TecTaxonomia.slug_url.ilike(f"%{normalizar_texto_topico(pal, manter_stop_words=True).replace(' ', '-')}%"),
                )
            )

    resultados = (
        query
        .order_by(
            TecTaxonomia.is_materia.asc(),
            TecTaxonomia.total_questoes.desc(),
            TecTaxonomia.nivel_profundidade.asc()
        )
        .limit(limite)
        .all()
    )
    return [_serializar_no_tec(r) for r in resultados]


@router.get("/topico/{topico_id}/link")
def obter_link_e_sugestoes_topico(
    topico_id: int,
    incluir_sugestoes: bool = Query(True),
    db: Session = Depends(get_db)
):
    """
    Retorna a URL dinâmica montada para o tópico (`url_tec`, `url_assunto`, `url_caderno`,
    `url_fallback_busca`), metadados de confiança do vínculo e até 8 sugestões da árvore do TEC.
    """
    topico = db.query(Topico).filter(Topico.id == topico_id).first()
    if not topico:
        raise HTTPException(status_code=404, detail="Tópico não encontrado")

    dados_vinculo = montar_dados_vinculo_topico(topico, topico.vinculo_tec)

    sugestoes = []
    if incluir_sugestoes:
        disc_nome = topico.disciplina.nome if topico.disciplina else ""
        slugs = obter_slugs_tec_para_disciplina(disc_nome)
        q_cand = db.query(TecTaxonomia).filter(TecTaxonomia.ativo == True, TecTaxonomia.is_materia == False)
        if slugs:
            q_cand = q_cand.filter(or_(*[TecTaxonomia.slug_url.like(f"{s}%") for s in slugs]))
        nos_cand = q_cand.all()
        if not nos_cand:
            nos_cand = db.query(TecTaxonomia).filter(TecTaxonomia.ativo == True, TecTaxonomia.is_materia == False).limit(500).all()

        catalogo = _preparar_catalogo_nos_tec(nos_cand)
        norm_t = normalizar_texto_topico(topico.titulo)
        exp_t = expandir_termos_topico(topico.titulo, norm_t)
        tok_t = set(norm_t.split())
        tok_exp = set(exp_t.split())

        avaliados = []
        for c in catalogo:
            sc, tp = calcular_similaridade_topico_no_tec(
                titulo_topico=topico.titulo,
                norm_topico=norm_t,
                expandido_topico=exp_t,
                tokens_topico=tok_t,
                tokens_expandidos=tok_exp,
                no_tec=c
            )
            if sc > 0.15:
                avaliados.append((sc, tp, c["obj"]))

        avaliados.sort(key=lambda x: (-x[0], -(x[2].total_questoes or 0)))
        for sc, tp, obj in avaliados[:8]:
            item_s = _serializar_no_tec(obj)
            item_s["confianca_score"] = round(sc, 4)
            item_s["tipo_vinculo_sugerido"] = tp
            sugestoes.append(item_s)

    return {
        "topico": {
            "id": topico.id,
            "titulo": topico.titulo,
            "disciplina_id": topico.disciplina_id,
            "disciplina_nome": topico.disciplina.nome if topico.disciplina else None,
        },
        "vinculo": dados_vinculo,
        "sugestoes": sugestoes,
    }


@router.post("/topico/{topico_id}/vincular", response_model=TecVinculoTopicoPayload)
def vincular_topico_manualmente(
    topico_id: int,
    dados: TecVincularManualRequest,
    db: Session = Depends(get_db)
):
    """
    Fixa manualmente o vínculo De-Para entre um tópico do edital e um nó da árvore do TEC Concursos
    (`tipo_vinculo = MANUAL`, `confianca_score = 1.0`, `validado = True`).
    """
    topico = db.query(Topico).filter(Topico.id == topico_id).first()
    if not topico:
        raise HTTPException(status_code=404, detail="Tópico não encontrado")

    no_tec = db.query(TecTaxonomia).filter(TecTaxonomia.id == dados.tec_taxonomia_id).first()
    if not no_tec:
        raise HTTPException(status_code=404, detail="Nó da taxonomia TEC não encontrado")

    now = datetime.now(timezone.utc)
    vinculo = db.query(TopicoEstudoTecDePara).filter(TopicoEstudoTecDePara.topico_id == topico_id).first()
    if not vinculo:
        vinculo = TopicoEstudoTecDePara(
            topico_id=topico_id,
            tec_taxonomia_id=no_tec.id,
            tipo_vinculo="MANUAL",
            confianca_score=1.0,
            validado=True,
            updated_at=now
        )
        db.add(vinculo)
    else:
        vinculo.tec_taxonomia_id = no_tec.id
        vinculo.tipo_vinculo = "MANUAL"
        vinculo.confianca_score = 1.0
        vinculo.validado = True
        vinculo.updated_at = now

    db.commit()
    db.refresh(vinculo)
    return montar_dados_vinculo_topico(topico, vinculo)


@router.delete("/topico/{topico_id}/vincular")
def desvincular_topico(topico_id: int, db: Session = Depends(get_db)):
    """Remove o vínculo De-Para de um tópico do edital."""
    topico = db.query(Topico).filter(Topico.id == topico_id).first()
    if not topico:
        raise HTTPException(status_code=404, detail="Tópico não encontrado")

    vinculo = db.query(TopicoEstudoTecDePara).filter(TopicoEstudoTecDePara.topico_id == topico_id).first()
    if vinculo:
        db.delete(vinculo)
        db.commit()

    return {
        "mensagem": "Vínculo removido com sucesso.",
        "vinculo": montar_dados_vinculo_topico(topico, None)
    }


@router.post("/reconciliar/{edital_id}")
async def reconciliar_edital_endpoint(
    edital_id: int,
    sobrescrever_manuais: bool = Query(False),
    usar_ia: bool = Query(True),
    db: Session = Depends(get_db)
):
    """
    Executa o motor de Matching De-Para (Heurística + Fuzzy + IA Gemini) para todos os tópicos do edital.
    Se a árvore do TEC ainda estiver vazia no banco, sincroniza automaticamente antes.
    """
    total_nos = db.query(func.count(TecTaxonomia.id)).scalar() or 0
    resumo_sync = None
    if total_nos == 0:
        resumo_sync = await sincronizar_taxonomia_tec(db, delay_entre_requisicoes=0.15)

    try:
        resumo_match = await executar_matching_edital(
            db=db,
            edital_id=edital_id,
            sobrescrever_manuais=sobrescrever_manuais,
            usar_ia_se_necessario=usar_ia
        )
        return {
            "mensagem": "Mapeamento De-Para com o TEC Concursos concluído com sucesso!",
            "sincronizacao": resumo_sync,
            "matching": resumo_match
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/sincronizar")
async def sincronizar_arvore_tec_endpoint(
    req: TecSincronizarRequest,
    db: Session = Depends(get_db)
):
    """
    Executa o Scraping Job da árvore de taxonomia do TEC Concursos e, opcionalmente,
    roda o Matching Engine De-Para no edital informado (ou em todos os editais ativos).
    """
    resumo_sync = await sincronizar_taxonomia_tec(
        db=db,
        slugs_adicionais=req.slugs_adicionais,
        delay_entre_requisicoes=0.15
    )

    resultados_matching = []
    if req.executar_matching:
        if req.edital_id is not None:
            editais = db.query(Edital).filter(Edital.id == req.edital_id).all()
        else:
            editais = db.query(Edital).filter(Edital.encerrado == False).all()

        for ed in editais:
            res_m = await executar_matching_edital(
                db=db,
                edital_id=ed.id,
                sobrescrever_manuais=False,
                usar_ia_se_necessario=req.usar_ia_se_necessario
            )
            resultados_matching.append(res_m)

    return {
        "mensagem": "Árvore de taxonomia do TEC Concursos sincronizada com sucesso!",
        "sincronizacao": resumo_sync,
        "matching": resultados_matching
    }


# ==============================================================================
# AUTOMAÇÃO DE CADERNOS REAIS E SESSÃO NO TEC CONCURSOS
# ==============================================================================

@router.get("/status-sessao")
def status_sessao_tec(db: Session = Depends(get_db)):
    """Retorna o status da sessão/cookies salvos do TEC Concursos e credenciais cadastradas."""
    status = obter_status_sessao_tec()
    cfg = db.query(ConfiguracaoPainelProva).first()
    status["email_configurado"] = cfg.tec_email if cfg else "fbasantos10@gmail.com"
    status["tem_senha_configurada"] = bool(cfg.tec_senha) if cfg else False
    status["pasta_padrao"] = cfg.tec_pasta_padrao if cfg and cfg.tec_pasta_padrao else "Sefaz Alagoas Auditor TI"
    return status


@router.post("/autenticar-interativo")
def autenticar_interativo_tec(timeout_segundos: int = Query(120)):
    """
    Abre o navegador Playwright para que o usuário faça login no TEC Concursos.
    Ao concluir o login, os cookies de sessão são salvos para automação em segundo plano.
    """
    res = iniciar_login_interativo_tec(timeout_segundos=timeout_segundos)
    if not res.get("sucesso"):
        raise HTTPException(status_code=400, detail=res.get("mensagem", "Falha na autenticação interativa"))
    return res


@router.post("/autenticar-credenciais")
def autenticar_credenciais_tec(req: TecConfigAutenticacaoRequest, db: Session = Depends(get_db)):
    """
    Realiza login headless usando e-mail e senha no TEC Concursos e salva a sessão.
    """
    cfg = db.query(ConfiguracaoPainelProva).first()
    email = req.tec_email or (cfg.tec_email if cfg else None) or "fbasantos10@gmail.com"
    senha = req.tec_senha or (cfg.tec_senha if cfg else None)

    if not senha:
        raise HTTPException(status_code=400, detail="Senha do TEC Concursos não informada.")

    res = autenticar_por_credenciais_tec(email=email, senha=senha)
    if not res.get("sucesso"):
        raise HTTPException(status_code=400, detail=res.get("mensagem", "Falha no login automatizado"))

    if cfg:
        cfg.tec_email = email
        cfg.tec_senha = senha
        if req.tec_pasta_padrao:
            cfg.tec_pasta_padrao = req.tec_pasta_padrao
        db.commit()

    return res


@router.post("/config-autenticacao")
def salvar_config_autenticacao(req: TecConfigAutenticacaoRequest, db: Session = Depends(get_db)):
    """Salva e-mail, senha e nome da pasta padrão nas configurações."""
    cfg = db.query(ConfiguracaoPainelProva).first()
    if not cfg:
        cfg = ConfiguracaoPainelProva()
        db.add(cfg)

    if req.tec_email is not None:
        cfg.tec_email = req.tec_email
    if req.tec_senha is not None:
        cfg.tec_senha = req.tec_senha
    if req.tec_pasta_padrao is not None:
        cfg.tec_pasta_padrao = req.tec_pasta_padrao

    db.commit()
    return {
        "mensagem": "Configurações do TEC Concursos salvas com sucesso!",
        "tec_email": cfg.tec_email,
        "tec_pasta_padrao": cfg.tec_pasta_padrao
    }


@router.post("/topico/{topico_id}/gerar-caderno")
def gerar_caderno_endpoint(
    topico_id: int,
    pasta_nome: Optional[str] = Query(None),
    headless: bool = Query(False),
    db: Session = Depends(get_db)
):
    """
    Gera o caderno no TEC Concursos para o tópico especificado na pasta configurada
    (ex: 'Sefaz Alagoas Auditor TI'), captura o ID e a URL gerada e associa permanentemente.
    """
    topico = db.query(Topico).filter(Topico.id == topico_id).first()
    if not topico:
        raise HTTPException(status_code=404, detail="Tópico não encontrado")

    res = gerar_caderno_topico_playwright(
        topico_id=topico_id,
        nome_pasta=pasta_nome,
        db=db,
        headless=headless
    )
    if not res.get("sucesso"):
        raise HTTPException(
            status_code=400,
            detail=res.get("mensagem", "Não foi possível gerar o caderno no TEC Concursos")
        )
    return res


@router.post("/topico/{topico_id}/associar-caderno")
def associar_caderno_endpoint(
    topico_id: int,
    req: TecAssociarCadernoRequest,
    db: Session = Depends(get_db)
):
    """
    Permite associar diretamente o número ou a URL de um caderno já existente no TEC Concursos
    (ex: '107798461' ou 'https://www.tecconcursos.com.br/questoes/cadernos/107798461').
    """
    topico = db.query(Topico).filter(Topico.id == topico_id).first()
    if not topico:
        raise HTTPException(status_code=404, detail="Tópico não encontrado")

    try:
        res = associar_caderno_manualmente(
            topico_id=topico_id,
            caderno_url_ou_id=req.caderno_url_ou_id,
            pasta_nome=req.pasta_nome,
            db=db
        )
        return res
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/topico/{topico_id}/caderno")
def desassociar_caderno_endpoint(topico_id: int, db: Session = Depends(get_db)):
    """
    Remove a associação do caderno manual deste tópico,
    revertendo o link para a matéria com a banca filtrada no TEC.
    """
    topico = db.query(Topico).filter(Topico.id == topico_id).first()
    if not topico:
        raise HTTPException(status_code=404, detail="Tópico não encontrado")

    vinculo = db.query(TopicoEstudoTecDePara).filter(TopicoEstudoTecDePara.topico_id == topico_id).first()
    if vinculo:
        vinculo.caderno_id = None
        vinculo.url_caderno_criado = None
        vinculo.pasta_tec_nome = None
        vinculo.data_geracao_caderno = None
        vinculo.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(vinculo)

    return {
        "sucesso": True,
        "mensagem": "Caderno manual removido com sucesso. O tópico voltará a abrir o link de questões da matéria no TEC.",
        "vinculo": montar_dados_vinculo_topico(topico, vinculo)
    }
