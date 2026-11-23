import json
import math
from datetime import date, datetime, timedelta
from collections import defaultdict
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy.orm import Session, selectinload, joinedload

from app.models.configuracao_prova import ConfiguracaoPainelProva
from app.models.edital import Edital
from app.models.disciplina import Disciplina
from app.models.topico import Topico
from app.models.ciclo import CicloEstudos, BlocoCiclo
from app.models.sessao import SessaoEstudo
from app.services.gamificacao_service import calcular_gamificacao_aluno
from app.services.revisoes_service import mapear_topicos_para_blocos_anki_do_ciclo


DIAS_SEMANA_NOMES_CURTOS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
DIAS_SEMANA_NOMES_COMPLETOS = [
    "Segunda-feira",
    "Terça-feira",
    "Quarta-feira",
    "Quinta-feira",
    "Sexta-feira",
    "Sábado",
    "Domingo",
]
MESES_NOMES = [
    "",
    "Janeiro",
    "Fevereiro",
    "Março",
    "Abril",
    "Maio",
    "Junho",
    "Julho",
    "Agosto",
    "Setembro",
    "Outubro",
    "Novembro",
    "Dezembro",
]


def _garantir_config(db: Session) -> ConfiguracaoPainelProva:
    config = db.query(ConfiguracaoPainelProva).first()
    if not config:
        config = ConfiguracaoPainelProva(id=1)
        db.add(config)
        db.commit()
        db.refresh(config)
    return config


def _carregar_preferencias_roteiro(config: ConfiguracaoPainelProva) -> Dict[str, Any]:
    try:
        dados = json.loads(config.marcos_alertados or "{}")
        if isinstance(dados, dict) and isinstance(dados.get("roteiro_estudo_config"), dict):
            return dados["roteiro_estudo_config"]
    except Exception:
        pass
    return {}


def salvar_preferencias_roteiro(
    db: Session,
    horas_por_dia: float = 2.0,
    dias_por_semana: int = 6,
    questoes_por_hora: Optional[float] = None,
    data_prova: Optional[str] = None,
) -> Dict[str, Any]:
    config = _garantir_config(db)
    try:
        dados = json.loads(config.marcos_alertados or "{}")
        if not isinstance(dados, dict):
            dados = {}
    except Exception:
        dados = {}

    pref = dados.get("roteiro_estudo_config")
    if not isinstance(pref, dict):
        pref = {}

    pref["horas_por_dia"] = round(max(1.0, min(12.0, float(horas_por_dia or 2.0))), 1)
    pref["dias_por_semana"] = max(1, min(7, int(dias_por_semana or 6)))
    if questoes_por_hora is not None and float(questoes_por_hora) > 0:
        pref["questoes_por_hora"] = round(max(1.0, min(100.0, float(questoes_por_hora))), 1)
    if data_prova:
        pref["data_prova"] = str(data_prova).strip()[:10]
        config.data_prova = str(data_prova).strip()[:10]
    pref["atualizado_em"] = datetime.now().strftime("%d/%m/%Y %H:%M")

    dados["roteiro_estudo_config"] = pref
    config.marcos_alertados = json.dumps(dados, ensure_ascii=False)
    db.commit()
    return pref


def _ordenar_topicos_verticalizado(topicos: List[Topico]) -> List[Topico]:
    """
    Ordena os tópicos seguindo exatamente a Trilha do Edital Verticalizado:
    1) ordem_trilha (definida pela Trilha IA / Pareto)
    2) Peso de prioridade (P1 -> P2 + Mais Cobrado -> P2 -> Mais Cobrado -> P3 -> Demais)
    3) Ordem natural do edital (ordem, id)
    """
    def peso_prioridade(t: Topico) -> int:
        if t.prioridade == 1:
            return 1
        if t.mais_cobrado and t.prioridade == 2:
            return 2
        if t.prioridade == 2:
            return 3
        if t.mais_cobrado:
            return 4
        if t.prioridade == 3:
            return 5
        return 6

    return sorted(
        topicos,
        key=lambda t: (
            t.ordem_trilha if t.ordem_trilha is not None else 999999,
            peso_prioridade(t),
            t.ordem if t.ordem is not None else (t.id or 999999),
            t.id or 0,
        ),
    )


def _serializar_topico_resumo(t: Topico, visto: bool) -> Dict[str, Any]:
    return {
        "id": t.id,
        "titulo": t.titulo,
        "ordem": t.ordem if t.ordem is not None else 0,
        "ordem_trilha": t.ordem_trilha,
        "prioridade": t.prioridade,
        "mais_cobrado": bool(t.mais_cobrado),
        "concluido": bool(t.concluido),
        "visto": visto,
        "eh_alta_prioridade_ou_mais_cobrado": bool(t.prioridade == 1 or t.mais_cobrado),
    }


def calcular_roteiro_estudo(
    db: Session,
    edital_id: Optional[int] = None,
    horas_por_dia_override: Optional[float] = None,
    dias_por_semana_override: Optional[int] = None,
    questoes_por_hora_override: Optional[float] = None,
    data_prova_override: Optional[str] = None,
    hoje_ref: Optional[date] = None,
) -> Dict[str, Any]:
    """
    Gera o Roteiro de Estudo completo baseado no Ciclo Atual e no Edital Verticalizado:
      - Assume por padrão 2 horas de estudo por dia, onde cada 1 hora = 1 missão (1 disciplina + 1 tópico do ciclo).
      - Sincroniza automaticamente a Agenda do Dia com as sessões registradas hoje no Ciclo.
      - Projeta o que será estudado na Semana, no Mês (Calendário) e Até a Prova.
      - Calcula % de cobertura do edital até a prova, probabilidade/cobertura dos tópicos Mais Cobrados e P1,
        e projeção do total de questões resolvidas mantendo o ritmo.
    """
    hoje = hoje_ref or date.today()
    config = _garantir_config(db)
    prefs = _carregar_preferencias_roteiro(config)

    # 1. Localiza o Ciclo Ativo e o Edital correspondente
    ciclo_query = (
        db.query(CicloEstudos)
        .options(
            selectinload(CicloEstudos.blocos)
            .joinedload(BlocoCiclo.disciplina)
            .selectinload(Disciplina.topicos)
        )
    )
    if edital_id:
        ciclo = ciclo_query.filter(CicloEstudos.edital_id == edital_id, CicloEstudos.ativo == True).first()
    else:
        ciclo = ciclo_query.filter(CicloEstudos.ativo == True).first()

    if ciclo:
        edital = (
            db.query(Edital)
            .options(selectinload(Edital.disciplinas).selectinload(Disciplina.topicos))
            .filter(Edital.id == ciclo.edital_id)
            .first()
        )
    else:
        edital_q = db.query(Edital).options(selectinload(Edital.disciplinas).selectinload(Disciplina.topicos))
        if edital_id:
            edital = edital_q.filter(Edital.id == edital_id).first()
        else:
            edital = edital_q.filter(Edital.encerrado == False).order_by(Edital.id.desc()).first()
            if not edital:
                edital = edital_q.order_by(Edital.id.desc()).first()

    if not edital:
        return {"erro": "Nenhum edital encontrado para gerar o roteiro."}

    # 2. Parâmetros de horas por dia (padrão: 2h/dia, onde 1h = 1 disciplina + 1 tópico) e dias por semana
    horas_por_dia = float(
        horas_por_dia_override
        if horas_por_dia_override is not None
        else prefs.get("horas_por_dia", 2.0)
    )
    horas_por_dia = round(max(1.0, min(12.0, horas_por_dia)), 1)
    missoes_por_dia = max(1, int(round(horas_por_dia)))  # Cada 1 hora = 1 disciplina e 1 tópico

    dias_por_semana = int(
        dias_por_semana_override
        if dias_por_semana_override is not None
        else prefs.get("dias_por_semana", int(config.dias_disponiveis_semana or 6))
    )
    dias_por_semana = max(1, min(7, dias_por_semana))

    # 3. Data da prova e dias restantes
    data_prova_obj: Optional[date] = None
    for cand_str in (data_prova_override, prefs.get("data_prova"), config.data_prova, getattr(edital, "data_prova", None)):
        if cand_str:
            try:
                cand_dt = date.fromisoformat(str(cand_str).strip()[:10])
                if cand_dt > hoje:
                    data_prova_obj = cand_dt
                    break
            except Exception:
                continue

    if not data_prova_obj or data_prova_obj <= hoje:
        # Se a data da prova não estiver definida ou já tiver passado, projeta horizonte padrão de 90 dias
        data_prova_obj = hoje + timedelta(days=90)
        tipo_data_prova = "Horizonte Projetado (90 dias)"
    else:
        tipo_data_prova = config.tipo_data_prova or "Confirmada"

    dias_corridos_ate_prova = max(1, (data_prova_obj - hoje).days)

    # 4. Histórico de sessões do edital (para saber tópicos já vistos, sessões de hoje e ritmo real de questões)
    todas_sessoes = (
        db.query(SessaoEstudo)
        .join(Disciplina, SessaoEstudo.disciplina_id == Disciplina.id)
        .filter(Disciplina.edital_id == edital.id)
        .order_by(SessaoEstudo.data.asc(), SessaoEstudo.id.asc())
        .all()
    )

    topicos_vistos_ids = set(s.topico_id for s in todas_sessoes if s.topico_id is not None)
    sessoes_hoje = [s for s in todas_sessoes if s.data == hoje]
    ultimas_obs_por_topico: Dict[int, Dict[str, Any]] = {}
    for s_ob in reversed(todas_sessoes):
        if s_ob.topico_id is not None and s_ob.topico_id not in ultimas_obs_por_topico:
            txt_ob = (s_ob.observacoes or "").strip()
            if txt_ob:
                ultimas_obs_por_topico[s_ob.topico_id] = {
                    "ultima_observacao": txt_ob,
                    "ultima_observacao_data": s_ob.data.isoformat() if s_ob.data else None,
                    "ultima_observacao_sessao_id": s_ob.id,
                }

    total_questoes_ja_resolvidas = sum(int(s.qtd_questoes_total or 0) for s in todas_sessoes)
    total_minutos_ja_estudados = sum(int(s.tempo_estudado_minutos or 0) for s in todas_sessoes)
    horas_ja_estudadas = round(total_minutos_ja_estudados / 60.0, 1)

    # Ritmo histórico de questões por hora (com piso realista de 15 questões/h caso histórico seja inicial)
    if horas_ja_estudadas >= 2.0 and total_questoes_ja_resolvidas > 0:
        ritmo_historico_q_por_hora = round(total_questoes_ja_resolvidas / horas_ja_estudadas, 1)
    else:
        ritmo_historico_q_por_hora = 18.0

    questoes_por_hora = float(
        questoes_por_hora_override
        if questoes_por_hora_override is not None
        else prefs.get("questoes_por_hora", ritmo_historico_q_por_hora)
    )
    questoes_por_hora = round(max(5.0, min(80.0, questoes_por_hora)), 1)

    # 5. Disciplinas e filas de tópicos ordenadas pelo Edital Verticalizado (Edital Completo)
    disciplinas_validas = [
        d for d in edital.disciplinas
        if d.categoria != "REVISAO_ANKI" and d.nome != "REVISÃO ANKI"
    ]
    disciplinas_validas.sort(key=lambda d: (d.ordem_trilha if d.ordem_trilha is not None else 999, d.id))
    mapa_disc = {d.id: d for d in disciplinas_validas}

    filas_pendentes_por_disc: Dict[int, List[Topico]] = {}
    filas_todos_por_disc: Dict[int, List[Topico]] = {}
    todos_topicos_edital: List[Topico] = []

    for d in disciplinas_validas:
        ordenados = _ordenar_topicos_verticalizado(list(d.topicos or []))
        filas_todos_por_disc[d.id] = ordenados
        pendentes = [t for t in ordenados if not (bool(t.concluido) or (t.id in topicos_vistos_ids))]
        filas_pendentes_por_disc[d.id] = pendentes
        todos_topicos_edital.extend(ordenados)

    mapa_topico_obj = {t.id: t for t in todos_topicos_edital}

    # Estatísticas globais atuais do Edital Verticalizado
    total_topicos_edital = len(todos_topicos_edital)
    topicos_concluidos_hoje_set = {
        t.id for t in todos_topicos_edital if bool(t.concluido) or (t.id in topicos_vistos_ids)
    }
    qtd_vistos_atual = len(topicos_concluidos_hoje_set)
    perc_edital_atual = round((qtd_vistos_atual / total_topicos_edital) * 100.0, 1) if total_topicos_edital > 0 else 0.0

    topicos_p1_lista = [t for t in todos_topicos_edital if t.prioridade == 1]
    topicos_mc_lista = [t for t in todos_topicos_edital if bool(t.mais_cobrado)]
    topicos_elite_lista = [t for t in todos_topicos_edital if t.prioridade == 1 or bool(t.mais_cobrado)]

    vistos_p1_atual = sum(1 for t in topicos_p1_lista if t.id in topicos_concluidos_hoje_set)
    vistos_mc_atual = sum(1 for t in topicos_mc_lista if t.id in topicos_concluidos_hoje_set)
    vistos_elite_atual = sum(1 for t in topicos_elite_lista if t.id in topicos_concluidos_hoje_set)

    # 6. Sequência da Esteira do Ciclo Atual (incluindo blocos de Revisão Anki na ordem exata da esteira)
    sequencia_blocos: List[Dict[str, Any]] = []
    if ciclo and ciclo.blocos:
        mapa_anki = mapear_topicos_para_blocos_anki_do_ciclo(db, ciclo)
        blocos_ordenados = sorted(ciclo.blocos, key=lambda b: b.ordem)
        idx_inicial = (ciclo.bloco_atual_index or 0) % len(blocos_ordenados)
        # Rotaciona a lista para começar exatamente do bloco_atual_index da esteira
        blocos_rotacionados = blocos_ordenados[idx_inicial:] + blocos_ordenados[:idx_inicial]
        for b in blocos_rotacionados:
            if not b.disciplina:
                continue
            eh_anki = b.disciplina.categoria == "REVISAO_ANKI" or b.disciplina.nome == "REVISÃO ANKI"
            if eh_anki:
                anki_info = mapa_anki.get(b.id)
                sequencia_blocos.append({
                    "bloco_id": b.id,
                    "ordem_ciclo": b.ordem,
                    "disciplina_id": anki_info["disciplina_id"] if anki_info else b.disciplina_id,
                    "disciplina_nome": f"REVISÃO ANKI • {anki_info['disciplina_nome']}" if anki_info else "REVISÃO ANKI",
                    "grupo_conhecimento": b.disciplina.grupo_conhecimento,
                    "peso_prova": b.disciplina.peso_prova,
                    "is_revisao_anki": True,
                    "anki_info": anki_info,
                    "duracao_minutos": int(b.duracao_minutos or 30),
                })
            else:
                sequencia_blocos.append({
                    "bloco_id": b.id,
                    "ordem_ciclo": b.ordem,
                    "disciplina_id": b.disciplina_id,
                    "disciplina_nome": b.disciplina.nome,
                    "grupo_conhecimento": b.disciplina.grupo_conhecimento,
                    "peso_prova": b.disciplina.peso_prova,
                    "is_revisao_anki": False,
                    "anki_info": None,
                    "duracao_minutos": int(b.duracao_minutos or 60),
                })

    if not sequencia_blocos:
        discs_fallback = [d for d in disciplinas_validas if getattr(d, "incluir_no_ciclo", True)] or disciplinas_validas
        for idx_d, d in enumerate(discs_fallback):
            sequencia_blocos.append({
                "bloco_id": None,
                "ordem_ciclo": idx_d,
                "disciplina_id": d.id,
                "disciplina_nome": d.nome,
                "grupo_conhecimento": d.grupo_conhecimento,
                "peso_prova": d.peso_prova,
            })

    # 7. Monta as Missões do Dia (Agenda de Hoje) sincronizadas com os estudos já marcados hoje no ciclo
    missoes_hoje: List[Dict[str, Any]] = []
    for idx_s, s_hoje in enumerate(sessoes_hoje, start=1):
        d_obj = mapa_disc.get(s_hoje.disciplina_id)
        t_obj = mapa_topico_obj.get(s_hoje.topico_id) if s_hoje.topico_id else None
        missoes_hoje.append({
            "id": f"hoje-concluida-{s_hoje.id}",
            "ordem_dia": idx_s,
            "data_iso": hoje.isoformat(),
            "data_fmt": hoje.strftime("%d/%m/%Y"),
            "hora_referencia": f"{idx_s}ª Hora do Dia",
            "duracao_minutos": int(s_hoje.tempo_estudado_minutos or 60),
            "bloco_ciclo_id": s_hoje.bloco_ciclo_id,
            "disciplina_id": s_hoje.disciplina_id,
            "disciplina_nome": (f"REVISÃO ANKI • {d_obj.nome}" if (s_hoje.is_revisao_anki and d_obj) else (d_obj.nome if d_obj else "Revisão / Anki")),
            "grupo_conhecimento": d_obj.grupo_conhecimento if d_obj else "BASICOS",
            "topico_id": t_obj.id if t_obj else None,
            "topico_titulo": t_obj.titulo if t_obj else "Revisão Geral / Questões",
            "prioridade": t_obj.prioridade if t_obj else None,
            "mais_cobrado": bool(t_obj.mais_cobrado) if t_obj else False,
            "modo_estudo": "Revisão Anki Concluída" if s_hoje.is_revisao_anki else "Concluído no Ciclo",
            "is_revisao_anki": bool(s_hoje.is_revisao_anki),
            "concluida": True,
            "sessao_id": s_hoje.id,
            "questoes_realizadas": int(s_hoje.qtd_questoes_total or 0),
            "acertos_obtidos": int(s_hoje.qtd_acertos or 0),
            "questoes_estimadas": int(s_hoje.qtd_questoes_total or round(questoes_por_hora)),
            "ultima_observacao": (s_hoje.observacoes or "").strip() or (ultimas_obs_por_topico.get(t_obj.id, {}).get("ultima_observacao") if t_obj else None),
            "ultima_observacao_data": s_hoje.data.isoformat() if (s_hoje.observacoes or "").strip() else (ultimas_obs_por_topico.get(t_obj.id, {}).get("ultima_observacao_data") if t_obj else None),
        })

    # Ponteiros de simulação da fila verticalizada por disciplina
    cursor_pendentes: Dict[int, int] = {d.id: 0 for d in disciplinas_validas}
    cursor_revisao: Dict[int, int] = {d.id: 0 for d in disciplinas_validas}
    ponteiro_esteira = 0

    def _alocar_proxima_missao(data_alvo: date, ordem_no_dia: int) -> Dict[str, Any]:
        nonlocal ponteiro_esteira
        item_ciclo = sequencia_blocos[ponteiro_esteira % len(sequencia_blocos)]
        ponteiro_esteira += 1

        did = item_ciclo["disciplina_id"]
        is_anki = bool(item_ciclo.get("is_revisao_anki"))

        if is_anki:
            anki_info = item_ciclo.get("anki_info")
            topico_id_esc = anki_info["id"] if anki_info else None
            topico_titulo_esc = anki_info["titulo"] if anki_info else "Revisão Espaçada Anki (SM-2 / Ebbinghaus)"
            prioridade_esc = anki_info.get("prioridade") if anki_info else None
            mais_cobrado_esc = bool(anki_info.get("mais_cobrado")) if anki_info else False
            ordem_trilha_esc = anki_info.get("ordem_trilha") if anki_info else None
            tecnica_nome = anki_info.get("tecnica_recomendada") if anki_info else None
            modo = f"Revisão Anki • {tecnica_nome}" if tecnica_nome else "Revisão Anki (SM-2 / Ebbinghaus)"
            inedito = False
            duracao_min = int(item_ciclo.get("duracao_minutos") or 30)
            questoes_est = max(5, int(round(questoes_por_hora * (duracao_min / 60.0))))
        else:
            fila_pend = filas_pendentes_por_disc.get(did, [])
            fila_todos = filas_todos_por_disc.get(did, [])
            idx_p = cursor_pendentes.get(did, 0)

            if idx_p < len(fila_pend):
                topico_escolhido = fila_pend[idx_p]
                cursor_pendentes[did] = idx_p + 1
                modo = "Avanço Verticalizado (Inédito)"
                inedito = True
            elif fila_todos:
                idx_r = cursor_revisao.get(did, 0)
                topico_escolhido = fila_todos[idx_r % len(fila_todos)]
                cursor_revisao[did] = idx_r + 1
                modo = "Revisão & Bateria P1/🔥 (Edital Fechado)"
                inedito = False
            else:
                topico_escolhido = None
                modo = "Estudo Geral & Questões"
                inedito = False

            topico_id_esc = topico_escolhido.id if topico_escolhido else None
            topico_titulo_esc = topico_escolhido.titulo if topico_escolhido else "Tópico Geral da Disciplina"
            prioridade_esc = topico_escolhido.prioridade if topico_escolhido else None
            mais_cobrado_esc = bool(topico_escolhido.mais_cobrado) if topico_escolhido else False
            ordem_trilha_esc = topico_escolhido.ordem_trilha if topico_escolhido else None
            duracao_min = 60
            questoes_est = int(round(questoes_por_hora))

        return {
            "id": f"rot-{data_alvo.isoformat()}-{ordem_no_dia}",
            "ordem_dia": ordem_no_dia,
            "data_iso": data_alvo.isoformat(),
            "data_fmt": data_alvo.strftime("%d/%m/%Y"),
            "data_curta": data_alvo.strftime("%d/%m"),
            "dia_semana_curto": DIAS_SEMANA_NOMES_CURTOS[data_alvo.weekday()],
            "dia_semana_nome": DIAS_SEMANA_NOMES_COMPLETOS[data_alvo.weekday()],
            "hora_referencia": f"{ordem_no_dia}ª Hora ({ordem_no_dia}h/{missoes_por_dia}h)",
            "duracao_minutos": duracao_min,
            "bloco_ciclo_id": item_ciclo["bloco_id"],
            "ordem_ciclo": item_ciclo["ordem_ciclo"],
            "disciplina_id": did,
            "disciplina_nome": item_ciclo["disciplina_nome"],
            "grupo_conhecimento": item_ciclo["grupo_conhecimento"],
            "peso_prova": item_ciclo["peso_prova"],
            "topico_id": topico_id_esc,
            "topico_titulo": topico_titulo_esc,
            "prioridade": prioridade_esc,
            "mais_cobrado": mais_cobrado_esc,
            "ordem_trilha": ordem_trilha_esc,
            "modo_estudo": modo,
            "is_revisao_anki": is_anki,
            "topico_inedito": inedito,
            "concluida": False,
            "sessao_id": None,
            "questoes_estimadas": questoes_est,
            "ultima_observacao": ultimas_obs_por_topico.get(topico_id_esc, {}).get("ultima_observacao") if topico_id_esc else None,
            "ultima_observacao_data": ultimas_obs_por_topico.get(topico_id_esc, {}).get("ultima_observacao_data") if topico_id_esc else None,
        }

    # Quantas missões faltam hoje para completar a meta diária (ex.: se meta é 2h/dia e já fez 1h hoje, falta 1h hoje)
    qtd_concluidas_hoje = len(missoes_hoje)
    qtd_restantes_hoje = max(0, missoes_por_dia - qtd_concluidas_hoje)
    for idx_m in range(qtd_concluidas_hoje + 1, qtd_concluidas_hoje + qtd_restantes_hoje + 1):
        missoes_hoje.append(_alocar_proxima_missao(hoje, idx_m))

    # Se o usuário já bateu a meta de hoje (ex.: concluiu 2 de 2), ainda mostramos 1 "Missão Bônus (Próxima do Ciclo)" opcional ou mantemos a lista clara
    proxima_missao_ciclo = next((m for m in missoes_hoje if not m["concluida"]), None)

    # 8. Simulação dia a dia até a Data da Prova
    # Define quais dias da semana são ativos (ex.: 6 dias = Seg a Sáb; 5 dias = Seg a Sex; 7 dias = Seg a Dom)
    dias_semana_ativos_set = set(range(dias_por_semana))

    dias_roteiro: List[Dict[str, Any]] = []
    topicos_alcancados_ate_prova_set = set(topicos_concluidos_hoje_set)
    for m_hj in missoes_hoje:
        if m_hj.get("topico_id"):
            topicos_alcancados_ate_prova_set.add(m_hj["topico_id"])

    # Registra o dia de hoje no calendário
    dias_roteiro.append({
        "data_iso": hoje.isoformat(),
        "data_fmt": hoje.strftime("%d/%m/%Y"),
        "data_curta": hoje.strftime("%d/%m"),
        "dia_numero": hoje.day,
        "mes_numero": hoje.month,
        "ano_numero": hoje.year,
        "dia_semana_idx": hoje.weekday(),
        "dia_semana_curto": DIAS_SEMANA_NOMES_CURTOS[hoje.weekday()],
        "dia_semana_nome": DIAS_SEMANA_NOMES_COMPLETOS[hoje.weekday()],
        "eh_hoje": True,
        "dia_ativo": True,
        "horas_previstas": round(len(missoes_hoje) * 1.0, 1),
        "questoes_previstas": sum(m["questoes_estimadas"] for m in missoes_hoje),
        "qtd_concluidas": qtd_concluidas_hoje,
        "qtd_total": len(missoes_hoje),
        "missoes": missoes_hoje,
    })

    # Simula de amanhã até data_prova_obj
    cursor_data = hoje + timedelta(days=1)
    while cursor_data <= data_prova_obj:
        eh_ativo = cursor_data.weekday() in dias_semana_ativos_set
        missoes_do_dia: List[Dict[str, Any]] = []
        if eh_ativo:
            for h_idx in range(1, missoes_por_dia + 1):
                m_futura = _alocar_proxima_missao(cursor_data, h_idx)
                missoes_do_dia.append(m_futura)
                if m_futura.get("topico_id"):
                    topicos_alcancados_ate_prova_set.add(m_futura["topico_id"])

        dias_roteiro.append({
            "data_iso": cursor_data.isoformat(),
            "data_fmt": cursor_data.strftime("%d/%m/%Y"),
            "data_curta": cursor_data.strftime("%d/%m"),
            "dia_numero": cursor_data.day,
            "mes_numero": cursor_data.month,
            "ano_numero": cursor_data.year,
            "dia_semana_idx": cursor_data.weekday(),
            "dia_semana_curto": DIAS_SEMANA_NOMES_CURTOS[cursor_data.weekday()],
            "dia_semana_nome": DIAS_SEMANA_NOMES_COMPLETOS[cursor_data.weekday()],
            "eh_hoje": False,
            "dia_ativo": eh_ativo,
            "horas_previstas": round(len(missoes_do_dia) * 1.0, 1),
            "questoes_previstas": sum(m["questoes_estimadas"] for m in missoes_do_dia),
            "qtd_concluidas": 0,
            "qtd_total": len(missoes_do_dia),
            "missoes": missoes_do_dia,
        })
        cursor_data += timedelta(days=1)

    # 9. Recortes temporais: Semana (próximos 7 dias), Mês (próximos 30 dias + agrupamento por mês p/ Calendário) e Até a Prova
    roteiro_semana = dias_roteiro[:7]
    roteiro_mes = dias_roteiro[:30]

    # Agrupamento por Semanas até a Prova (para visualização de trilha semanal até a prova)
    semanas_ate_prova: List[Dict[str, Any]] = []
    for i in range(0, len(dias_roteiro), 7):
        fatia = dias_roteiro[i:i + 7]
        if not fatia:
            continue
        missoes_sem = [m for d in fatia for m in d["missoes"]]
        ineditos_sem = sum(1 for m in missoes_sem if m.get("topico_inedito") or m.get("concluida"))
        p1_mc_sem = sum(1 for m in missoes_sem if m.get("prioridade") == 1 or m.get("mais_cobrado"))
        questoes_sem = sum(d["questoes_previstas"] for d in fatia)
        horas_sem = round(sum(d["horas_previstas"] for d in fatia), 1)
        discs_nomes = []
        for m in missoes_sem:
            if m["disciplina_nome"] not in discs_nomes:
                discs_nomes.append(m["disciplina_nome"])

        semanas_ate_prova.append({
            "numero_semana": (i // 7) + 1,
            "periodo_fmt": f"{fatia[0]['data_curta']} a {fatia[-1]['data_curta']}",
            "data_inicio": fatia[0]["data_iso"],
            "data_fim": fatia[-1]["data_iso"],
            "horas_planejadas": horas_sem,
            "qtd_missoes": len(missoes_sem),
            "qtd_topicos_ineditos": ineditos_sem,
            "qtd_topicos_alta_prioridade": p1_mc_sem,
            "questoes_estimadas": questoes_sem,
            "disciplinas_envolvidas": discs_nomes,
            "dias": fatia,
        })

    # Agrupamento por Mês do Calendário (com preenchimento de células do grid Seg..Dom)
    meses_map: Dict[Tuple[int, int], List[Dict[str, Any]]] = defaultdict(list)
    for d_item in dias_roteiro:
        meses_map[(d_item["ano_numero"], d_item["mes_numero"])].append(d_item)

    calendario_mensal: List[Dict[str, Any]] = []
    for (ano_m, mes_m), dias_do_mes in sorted(meses_map.items()):
        primeiro_dia_dt = date(ano_m, mes_m, 1)
        if mes_m == 12:
            ultimo_dia_dt = date(ano_m + 1, 1, 1) - timedelta(days=1)
        else:
            ultimo_dia_dt = date(ano_m, mes_m + 1, 1) - timedelta(days=1)

        mapa_iso_dia = {d["data_iso"]: d for d in dias_do_mes}
        celulas_mes: List[Dict[str, Any]] = []

        # Espaços vazios antes do dia 1 (Segunda = 0 .. Domingo = 6)
        for _ in range(primeiro_dia_dt.weekday()):
            celulas_mes.append({"vazio": True})

        dt_iter = primeiro_dia_dt
        while dt_iter <= ultimo_dia_dt:
            iso_k = dt_iter.isoformat()
            if iso_k in mapa_iso_dia:
                celulas_mes.append({
                    "vazio": False,
                    "no_roteiro": True,
                    **mapa_iso_dia[iso_k],
                })
            else:
                # Dia anterior a hoje ou após a prova dentro do mesmo mês
                sessoes_dia_passado = [s for s in todas_sessoes if s.data == dt_iter]
                celulas_mes.append({
                    "vazio": False,
                    "no_roteiro": False,
                    "data_iso": iso_k,
                    "data_fmt": dt_iter.strftime("%d/%m/%Y"),
                    "data_curta": dt_iter.strftime("%d/%m"),
                    "dia_numero": dt_iter.day,
                    "mes_numero": mes_m,
                    "ano_numero": ano_m,
                    "dia_semana_idx": dt_iter.weekday(),
                    "dia_semana_curto": DIAS_SEMANA_NOMES_CURTOS[dt_iter.weekday()],
                    "eh_hoje": dt_iter == hoje,
                    "dia_passado": dt_iter < hoje,
                    "apos_prova": dt_iter > data_prova_obj,
                    "qtd_sessoes_historico": len(sessoes_dia_passado),
                    "missoes": [],
                })
            dt_iter += timedelta(days=1)

        horas_mes_tot = round(sum(d["horas_previstas"] for d in dias_do_mes), 1)
        questoes_mes_tot = sum(d["questoes_previstas"] for d in dias_do_mes)
        missoes_mes_tot = sum(d["qtd_total"] for d in dias_do_mes)

        calendario_mensal.append({
            "chave_mes": f"{ano_m}-{mes_m:02d}",
            "titulo_mes": f"{MESES_NOMES[mes_m]} {ano_m}",
            "ano": ano_m,
            "mes": mes_m,
            "horas_previstas_mes": horas_mes_tot,
            "questoes_previstas_mes": questoes_mes_tot,
            "missoes_previstas_mes": missoes_mes_tot,
            "celulas": celulas_mes,
        })

    # 10. Projeção detalhada por Disciplina (o que será visto até a prova no Verticalizado vs o que ficará pendente)
    roteiro_por_disciplina: List[Dict[str, Any]] = []
    for d in disciplinas_validas:
        todos_d = filas_todos_por_disc.get(d.id, [])
        pend_d = filas_pendentes_por_disc.get(d.id, [])
        qtd_alocada_ineditos = min(len(pend_d), cursor_pendentes.get(d.id, 0))
        qtd_revisoes_extras = cursor_revisao.get(d.id, 0)

        topicos_que_serao_vistos = pend_d[:qtd_alocada_ineditos]
        topicos_que_ficarao_fora = pend_d[qtd_alocada_ineditos:]

        ja_vistos_d = len(todos_d) - len(pend_d)
        total_vistos_ate_prova_d = ja_vistos_d + qtd_alocada_ineditos
        perc_atual_d = round((ja_vistos_d / len(todos_d)) * 100.0, 1) if todos_d else 100.0
        perc_ate_prova_d = round((total_vistos_ate_prova_d / len(todos_d)) * 100.0, 1) if todos_d else 100.0

        p1_mc_d = [t for t in todos_d if t.prioridade == 1 or bool(t.mais_cobrado)]
        p1_mc_vistos_ate_prova_d = sum(
            1 for t in p1_mc_d if t.id in topicos_alcancados_ate_prova_set
        )
        perc_p1_mc_d = round((p1_mc_vistos_ate_prova_d / len(p1_mc_d)) * 100.0, 1) if p1_mc_d else 100.0

        roteiro_por_disciplina.append({
            "disciplina_id": d.id,
            "nome": d.nome,
            "grupo_conhecimento": d.grupo_conhecimento,
            "peso_prova": d.peso_prova,
            "total_topicos": len(todos_d),
            "ja_vistos": ja_vistos_d,
            "novos_ate_prova": qtd_alocada_ineditos,
            "revisoes_apos_fechar": qtd_revisoes_extras,
            "total_vistos_ate_prova": total_vistos_ate_prova_d,
            "restantes_apos_prova": len(topicos_que_ficarao_fora),
            "perc_atual": perc_atual_d,
            "perc_ate_prova": perc_ate_prova_d,
            "total_p1_mais_cobrados": len(p1_mc_d),
            "vistos_p1_mais_cobrados_ate_prova": p1_mc_vistos_ate_prova_d,
            "perc_cobertura_p1_mais_cobrados": perc_p1_mc_d,
            "topicos_programados": [_serializar_topico_resumo(t, False) for t in topicos_que_serao_vistos],
            "topicos_nao_alcancados": [_serializar_topico_resumo(t, False) for t in topicos_que_ficarao_fora],
        })

    # 11. Métricas Globais de Cobertura do Edital, Probabilidade de Ver Mais Cobrados/P1 e Projeção de Questões
    qtd_vistos_ate_prova = len(topicos_alcancados_ate_prova_set)
    novos_topicos_ate_prova = max(0, qtd_vistos_ate_prova - qtd_vistos_atual)
    perc_edital_ate_prova = (
        round((qtd_vistos_ate_prova / total_topicos_edital) * 100.0, 1)
        if total_topicos_edital > 0
        else 100.0
    )

    vistos_p1_ate_prova = sum(1 for t in topicos_p1_lista if t.id in topicos_alcancados_ate_prova_set)
    perc_p1_ate_prova = (
        round((vistos_p1_ate_prova / len(topicos_p1_lista)) * 100.0, 1)
        if topicos_p1_lista
        else 100.0
    )

    vistos_mc_ate_prova = sum(1 for t in topicos_mc_lista if t.id in topicos_alcancados_ate_prova_set)
    perc_mc_ate_prova = (
        round((vistos_mc_ate_prova / len(topicos_mc_lista)) * 100.0, 1)
        if topicos_mc_lista
        else 100.0
    )

    vistos_elite_ate_prova = sum(1 for t in topicos_elite_lista if t.id in topicos_alcancados_ate_prova_set)
    prob_cobrir_elite_ate_prova = (
        round((vistos_elite_ate_prova / len(topicos_elite_lista)) * 100.0, 1)
        if topicos_elite_lista
        else perc_edital_ate_prova
    )

    # Quantas horas/dia seriam necessárias para fechar 100% dos tópicos P1/Mais Cobrados e 100% do Edital até a prova
    dias_ativos_restantes = sum(1 for d in dias_roteiro if d["dia_ativo"])
    total_missoes_ate_prova = sum(d["qtd_total"] for d in dias_roteiro)
    total_horas_ate_prova = round(sum(d["horas_previstas"] for d in dias_roteiro), 1)

    topicos_pendentes_totais = max(0, total_topicos_edital - qtd_vistos_atual)
    horas_dia_para_100_edital = (
        round(topicos_pendentes_totais / max(1, dias_ativos_restantes), 1)
        if dias_ativos_restantes > 0
        else horas_por_dia
    )

    # Projeção de Questões
    questoes_semana_proj = sum(d["questoes_previstas"] for d in roteiro_semana)
    questoes_mes_proj = sum(d["questoes_previstas"] for d in roteiro_mes)
    questoes_novas_ate_prova = sum(d["questoes_previstas"] for d in dias_roteiro)
    questoes_acumuladas_ate_prova = total_questoes_ja_resolvidas + questoes_novas_ate_prova

    return {
        "edital_id": edital.id,
        "edital_nome": edital.nome,
        "ciclo_id": ciclo.id if ciclo else None,
        "ciclo_nome": ciclo.nome if ciclo else "Ciclo Padrão",
        "bloco_atual_index": ciclo.bloco_atual_index if ciclo else 0,
        "voltas_completas": ciclo.voltas_completas if ciclo else 0,
        "parametros_roteiro": {
            "horas_por_dia": horas_por_dia,
            "missoes_por_dia": missoes_por_dia,
            "dias_por_semana": dias_por_semana,
            "horas_por_semana": round(horas_por_dia * dias_por_semana, 1),
            "questoes_por_hora": questoes_por_hora,
            "ritmo_historico_questoes_por_hora": ritmo_historico_q_por_hora,
            "data_hoje_iso": hoje.isoformat(),
            "data_hoje_fmt": hoje.strftime("%d/%m/%Y"),
            "data_prova_iso": data_prova_obj.isoformat(),
            "data_prova_fmt": data_prova_obj.strftime("%d/%m/%Y"),
            "tipo_data_prova": tipo_data_prova,
            "dias_corridos_ate_prova": dias_corridos_ate_prova,
            "dias_estudo_ativos_ate_prova": dias_ativos_restantes,
        },
        "projecao_ate_prova": {
            "total_topicos_edital": total_topicos_edital,
            "topicos_vistos_atual": qtd_vistos_atual,
            "perc_edital_atual": perc_edital_atual,
            "novos_topicos_ate_prova": novos_topicos_ate_prova,
            "topicos_vistos_ate_prova": qtd_vistos_ate_prova,
            "perc_edital_ate_prova": perc_edital_ate_prova,
            "topicos_restantes_apos_prova": max(0, total_topicos_edital - qtd_vistos_ate_prova),
            "horas_dia_necessarias_100_edital": horas_dia_para_100_edital,
            # Mais cobrados e Prioridade Alta (P1)
            "total_prioridade_alta_p1": len(topicos_p1_lista),
            "vistos_p1_atual": vistos_p1_atual,
            "vistos_p1_ate_prova": vistos_p1_ate_prova,
            "probabilidade_ver_p1_perc": perc_p1_ate_prova,
            "total_mais_cobrados": len(topicos_mc_lista),
            "vistos_mais_cobrados_atual": vistos_mc_atual,
            "vistos_mais_cobrados_ate_prova": vistos_mc_ate_prova,
            "probabilidade_ver_mais_cobrados_perc": perc_mc_ate_prova,
            "total_nucleo_prioritario_elite": len(topicos_elite_lista),
            "vistos_nucleo_prioritario_atual": vistos_elite_atual,
            "vistos_nucleo_prioritario_ate_prova": vistos_elite_ate_prova,
            "probabilidade_ver_nucleo_prioritario_perc": prob_cobrir_elite_ate_prova,
            # Questões e Horas
            "total_horas_ate_prova": total_horas_ate_prova,
            "total_missoes_ate_prova": total_missoes_ate_prova,
            "questoes_ja_resolvidas": total_questoes_ja_resolvidas,
            "questoes_projecao_semana": questoes_semana_proj,
            "questoes_projecao_mes": questoes_mes_proj,
            "questoes_novas_ate_prova": questoes_novas_ate_prova,
            "questoes_acumuladas_ate_prova": questoes_acumuladas_ate_prova,
        },
        "agenda_hoje": {
            "data_iso": hoje.isoformat(),
            "data_fmt": hoje.strftime("%d/%m/%Y"),
            "dia_semana_nome": DIAS_SEMANA_NOMES_COMPLETOS[hoje.weekday()],
            "meta_missoes_dia": missoes_por_dia,
            "qtd_concluidas_hoje": qtd_concluidas_hoje,
            "qtd_pendentes_hoje": max(0, len(missoes_hoje) - qtd_concluidas_hoje),
            "percentual_concluido_hoje": round((qtd_concluidas_hoje / max(1, len(missoes_hoje))) * 100.0, 1),
            "proxima_missao": proxima_missao_ciclo,
            "missoes_hoje": missoes_hoje,
        },
        "roteiro_semana": roteiro_semana,
        "roteiro_mes": roteiro_mes,
        "calendario_mensal": calendario_mensal,
        "semanas_ate_prova": semanas_ate_prova,
        "roteiro_por_disciplina": roteiro_por_disciplina,
        "gamificacao": calcular_gamificacao_aluno(db=db, edital_id=edital.id, hoje_ref=hoje),
    }
