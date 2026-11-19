import math
from datetime import date, datetime, timedelta
from collections import defaultdict
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy.orm import Session, selectinload, joinedload

from app.models.edital import Edital
from app.models.disciplina import Disciplina
from app.models.topico import Topico
from app.models.ciclo import CicloEstudos, BlocoCiclo
from app.models.sessao import SessaoEstudo


INTERVALOS_PADRAO_DIAS = [1, 3, 7, 15, 30, 60]

CATALOGO_TECNICAS_MEMORIZACAO = [
    {
        "codigo": "ACTIVE_RECALL_ERROS",
        "nome": "Active Recall + Flashcards Cloze de Erros",
        "icone": "fa-bolt",
        "cor": "rose",
        "faixa_ideal": "Rendimento < 65% ou alta recorrência de erros",
        "como_aplicar": (
            "Transforme cada questão errada do tópico em 1 card de pergunta direta ou omissão de palavra-chave (Cloze) "
            "no Anki. Tente responder mentalmente antes de virar o card, forçando a recuperação ativa na memória."
        ),
        "beneficio_neuro": "Fortalece as sinapses de recuperação e elimina a ilusão de competência da leitura passiva.",
    },
    {
        "codigo": "FEYNMAN_CONCEITO",
        "nome": "Técnica Feynman (Autoexplicação Simplificada)",
        "icone": "fa-chalkboard-user",
        "cor": "amber",
        "faixa_ideal": "Tópicos P1 ⚡ / 🔥 com base teórica frágil (< 70%)",
        "como_aplicar": (
            "Explique o conceito central do tópico em voz alta ou em 5 linhas como se estivesse ensinando um iniciante. "
            "Onde travar na explicação, volte pontualmente na teoria por 10 minutos e refaça 10 questões."
        ),
        "beneficio_neuro": "Converte memória de curto prazo fragmentada em compreensão estruturada de longo prazo.",
    },
    {
        "codigo": "INTERLEAVING_QUEST",
        "nome": "Prática Intercalada (Interleaving + Ciclo 7d/15d)",
        "icone": "fa-shuffle",
        "cor": "blue",
        "faixa_ideal": "Rendimento intermediário (65% a 79%) em janela de 7 a 15 dias",
        "como_aplicar": (
            "Resolva uma bateria curta de 15 questões misturando este tópico com outro tópico já visto da disciplina, "
            "treinando o cérebro a identificar qual regra aplicar em cada enunciado da banca."
        ),
        "beneficio_neuro": "Aumenta a discriminação conceitual e evita confundir institutos parecidos na hora da prova.",
    },
    {
        "codigo": "DUAL_CODING_MAPA",
        "nome": "Dual Coding (Esquema Visual + Lei Seca / Normas)",
        "icone": "fa-diagram-project",
        "cor": "purple",
        "faixa_ideal": "Tópicos vistos há mais de 14 dias com queda de retenção",
        "como_aplicar": (
            "Revise em 15 minutos usando uma tabela comparativa, fluxograma de prazos/competências ou grifos visuais "
            "dos artigos/regras mais cobrados antes de abrir os cards do Anki."
        ),
        "beneficio_neuro": "Combina os canais verbal e visual na memória de trabalho, dobrando a ancoragem mnêmica.",
    },
    {
        "codigo": "SPRINT_MANUTENCAO",
        "nome": "Sprint de Manutenção Espaçada (Overlearning 30d)",
        "icone": "fa-shield-halved",
        "cor": "emerald",
        "faixa_ideal": "Tópicos dominados (≥ 80% de acerto) em ciclo de 21 a 30+ dias",
        "como_aplicar": (
            "Não releia a teoria! Faça apenas 10 minutos de cards maduros no Anki + 10 questões rápidas da banca "
            "para renovar a estabilidade da curva de Ebbinghaus por mais 30 dias."
        ),
        "beneficio_neuro": "Mantém a retenção acima de 85% com custo mínimo de tempo no ciclo.",
    },
]


def _selecionar_tecnica_memorizacao(
    taxa_acerto: float,
    erros_total: int,
    dias_sem_ver: int,
    prioridade: Optional[int],
    mais_cobrado: bool,
) -> Dict[str, str]:
    if taxa_acerto < 62.0 or erros_total >= 8:
        t = CATALOGO_TECNICAS_MEMORIZACAO[0]
    elif taxa_acerto < 70.0 and (prioridade == 1 or mais_cobrado):
        t = CATALOGO_TECNICAS_MEMORIZACAO[1]
    elif dias_sem_ver >= 14 and taxa_acerto < 82.0:
        t = CATALOGO_TECNICAS_MEMORIZACAO[3]
    elif taxa_acerto < 80.0:
        t = CATALOGO_TECNICAS_MEMORIZACAO[2]
    else:
        t = CATALOGO_TECNICAS_MEMORIZACAO[4]

    return {
        "codigo": t["codigo"],
        "nome": t["nome"],
        "icone": t["icone"],
        "cor": t["cor"],
        "orientacao_curta": t["como_aplicar"],
    }


def _calcular_parametros_sm2_ebbinghaus(
    taxa_acerto: float,
    qtd_passagens: int,
    dias_desde_ultimo: int,
) -> Dict[str, Any]:
    """
    Calcula o Fator de Facilidade (Ease Factor SM-2), o intervalo ótimo de repetição espaçada,
    o estágio atual (24h, 3d, 7d, 15d, 30d) e a retenção estimada pela Curva de Ebbinghaus R = e^(-t/S).
    """
    # 1. Ease Factor (1.3 a 2.5) conforme rendimento de acertos
    if taxa_acerto < 50.0:
        ef = 1.30
        indice_base = 0  # 1 dia (24h)
    elif taxa_acerto < 65.0:
        ef = 1.55
        indice_base = min(1, max(0, qtd_passagens - 1))  # 1d ou 3d
    elif taxa_acerto < 75.0:
        ef = 1.90
        indice_base = min(2, max(0, qtd_passagens - 1))  # 1d, 3d, 7d
    elif taxa_acerto < 85.0:
        ef = 2.25
        indice_base = min(3, max(1, qtd_passagens))  # 3d, 7d, 15d
    else:
        ef = 2.50
        indice_base = min(4, max(2, qtd_passagens))  # 7d, 15d, 30d

    intervalo_ideal_dias = INTERVALOS_PADRAO_DIAS[min(len(INTERVALOS_PADRAO_DIAS) - 1, indice_base)]

    # Estabilidade S da memória (em dias): cresce com repetições e com a taxa de acerto
    fator_qualidade = max(0.35, (taxa_acerto / 100.0) ** 1.35)
    estabilidade_dias = max(1.8, intervalo_ideal_dias * ef * fator_qualidade * (1.0 + 0.25 * max(0, qtd_passagens - 1)))

    # Retenção de Ebbinghaus: R(t) = exp(-t / S) * 100
    retencao_perc = round(max(12.0, min(99.0, 100.0 * math.exp(-max(0, dias_desde_ultimo) / estabilidade_dias))), 1)

    rotulos_estagio = {
        1: "Ciclo 24h (Reaprendizagem Imediata)",
        3: "Ciclo 3 Dias (Fixação Curta)",
        7: "Ciclo 7 Dias (Consolidação Semanal)",
        15: "Ciclo 15 Dias (Retenção Quinzenal)",
        30: "Ciclo 30 Dias (Memória de Longo Prazo)",
        60: "Ciclo 60 Dias (Domínio Blindado)",
    }
    estagio_label = rotulos_estagio.get(intervalo_ideal_dias, f"Ciclo {intervalo_ideal_dias} Dias")

    return {
        "ease_factor": round(ef, 2),
        "intervalo_ideal_dias": intervalo_ideal_dias,
        "estabilidade_memoria_dias": round(estabilidade_dias, 1),
        "retencao_estimada_perc": retencao_perc,
        "estagio_revisao": estagio_label,
    }


def diagnosticar_fila_revisoes_anki(
    db: Session,
    edital_id: Optional[int] = None,
    hoje_ref: Optional[date] = None,
) -> Dict[str, Any]:
    """
    Mapeia todas as revisões feitas, avalia o rendimento de cada matéria e tópico visto nos ciclos,
    calcula a retenção pela curva de esquecimento de Ebbinghaus e constrói a sequência ordenada de
    próximas revisões para o Anki e para a esteira do Ciclo de Estudos.
    """
    hoje = hoje_ref or date.today()

    # 1. Localiza Ciclo ativo e Edital
    ciclo_q = db.query(CicloEstudos).options(selectinload(CicloEstudos.blocos).joinedload(BlocoCiclo.disciplina))
    if edital_id:
        ciclo = ciclo_q.filter(CicloEstudos.edital_id == edital_id, CicloEstudos.ativo == True).first()
    else:
        ciclo = ciclo_q.filter(CicloEstudos.ativo == True).first()

    edital_q = db.query(Edital).options(
        selectinload(Edital.disciplinas).selectinload(Disciplina.topicos).joinedload(Topico.vinculo_tec)
    )
    if ciclo:
        edital = edital_q.filter(Edital.id == ciclo.edital_id).first()
    elif edital_id:
        edital = edital_q.filter(Edital.id == edital_id).first()
    else:
        edital = edital_q.filter(Edital.encerrado == False).order_by(Edital.id.desc()).first()
        if not edital:
            edital = edital_q.order_by(Edital.id.desc()).first()

    if not edital:
        return {"erro": "Nenhum edital ativo encontrado."}

    # 2. Carrega todas as sessões de estudo do edital
    todas_sessoes = (
        db.query(SessaoEstudo)
        .join(Disciplina, SessaoEstudo.disciplina_id == Disciplina.id)
        .filter(Disciplina.edital_id == edital.id)
        .order_by(SessaoEstudo.data.asc(), SessaoEstudo.id.asc())
        .all()
    )

    disciplinas_validas = [
        d for d in edital.disciplinas
        if d.categoria != "REVISAO_ANKI" and d.nome != "REVISÃO ANKI"
    ]
    disciplinas_validas.sort(key=lambda d: (d.ordem_trilha if d.ordem_trilha is not None else 999, d.id))
    mapa_disc = {d.id: d for d in disciplinas_validas}
    mapa_topico: Dict[int, Topico] = {}
    for d in disciplinas_validas:
        for t in d.topicos or []:
            mapa_topico[t.id] = t

    # 3. Agrupa sessões por tópico e identifica todas as revisões realizadas
    sessoes_por_topico: Dict[int, List[SessaoEstudo]] = defaultdict(list)
    sessoes_por_disc: Dict[int, List[SessaoEstudo]] = defaultdict(list)
    historico_revisoes_feitas: List[Dict[str, Any]] = []

    # Mapa do tópico principal (1º da trilha) de cada disciplina para sessões antigas sem topico_id explícito
    primeiro_topico_por_disc: Dict[int, Topico] = {}
    for d in disciplinas_validas:
        if d.topicos:
            tops_ord = sorted(
                d.topicos,
                key=lambda t: (t.ordem_trilha if t.ordem_trilha is not None else 999999, t.ordem or 0, t.id or 0),
            )
            primeiro_topico_por_disc[d.id] = tops_ord[0]

    contagem_topico_vista: Dict[int, int] = defaultdict(int)
    ultimo_rend_por_topico: Dict[int, float] = {}
    for s in todas_sessoes:
        sessoes_por_disc[s.disciplina_id].append(s)
        tid_efetivo = s.topico_id
        if not tid_efetivo and s.disciplina_id in primeiro_topico_por_disc and not s.is_revisao_anki:
            tid_efetivo = primeiro_topico_por_disc[s.disciplina_id].id

        if tid_efetivo:
            sessoes_por_topico[tid_efetivo].append(s)
            contagem_topico_vista[tid_efetivo] += 1

        q_sessao = int(s.qtd_questoes_total or 0)
        perc_sessao = round(float(s.percentual_acerto or 0.0), 1)
        rend_ant = ultimo_rend_por_topico.get(tid_efetivo) if tid_efetivo else None
        delta_ant = round(perc_sessao - rend_ant, 1) if (q_sessao > 0 and rend_ant is not None) else None

        # Uma sessão é contabilizada no histórico de revisões se:
        # (a) foi marcada explicitamente como Revisão Anki (is_revisao_anki == True) ou pertence à disciplina REVISÃO ANKI, OU
        # (b) é a 2ª+ passagem pelo mesmo tópico (revisão prática de tópico já visto)
        eh_bloco_anki_disc = s.disciplina_id not in mapa_disc
        eh_revisao_pratica = bool(tid_efetivo and contagem_topico_vista[tid_efetivo] >= 2)
        if bool(s.is_revisao_anki) or eh_bloco_anki_disc or eh_revisao_pratica:
            d_obj = mapa_disc.get(s.disciplina_id)
            t_obj = mapa_topico.get(tid_efetivo) if tid_efetivo else None
            historico_revisoes_feitas.append({
                "sessao_id": s.id,
                "data_iso": s.data.isoformat() if s.data else hoje.isoformat(),
                "data_fmt": s.data.strftime("%d/%m/%Y") if s.data else hoje.strftime("%d/%m/%Y"),
                "disciplina_id": s.disciplina_id,
                "disciplina_nome": d_obj.nome if d_obj else "Revisão Espaçada (Anki)",
                "topico_id": t_obj.id if t_obj else None,
                "topico_titulo": t_obj.titulo if t_obj else "Cards Gerais / Revisão Anki",
                "tempo_minutos": int(s.tempo_estudado_minutos or 0),
                "questoes_total": q_sessao,
                "acertos": int(s.qtd_acertos or 0),
                "erros": int(s.qtd_erros or 0),
                "percentual_acerto": perc_sessao,
                "rendimento_anterior_perc": rend_ant if q_sessao > 0 else None,
                "delta_vs_anterior_pp": delta_ant,
                "tipo_revisao": "Revisão Anki (Esteira)" if (s.is_revisao_anki or eh_bloco_anki_disc) else f"{contagem_topico_vista[tid_efetivo]}ª Passagem no Tópico",
                "observacoes": s.observacoes or "",
            })

        if tid_efetivo and q_sessao > 0:
            ultimo_rend_por_topico[tid_efetivo] = perc_sessao

    historico_revisoes_feitas.reverse()  # Mais recentes primeiro

    # 4. Avalia cada tópico já visto nos ciclos (Rendimento, Ebbinghaus, SM-2 e Prioridade de Revisão)
    topicos_analisados: List[Dict[str, Any]] = []
    for d in disciplinas_validas:
        for t in d.topicos or []:
            lista_s = sessoes_por_topico.get(t.id, [])
            if not lista_s and not bool(t.concluido):
                continue

            q_tot = sum(int(s.qtd_questoes_total or 0) for s in lista_s)
            ac_tot = sum(int(s.qtd_acertos or 0) for s in lista_s)
            er_tot = sum(int(s.qtd_erros or 0) for s in lista_s)
            min_tot = sum(int(s.tempo_estudado_minutos or 0) for s in lista_s)
            qtd_passagens = max(1, len(lista_s))
            qtd_revisoes_topico = max(0, len(lista_s) - 1) + sum(1 for s in lista_s if s.is_revisao_anki)

            if q_tot > 0:
                taxa_acerto = round((ac_tot / q_tot) * 100.0, 1)
            else:
                # Tópico marcado como concluído sem questões registradas ainda -> prior neutro (75%)
                taxa_acerto = 75.0

            ultima_data = max((s.data for s in lista_s if s.data), default=hoje - timedelta(days=7))
            dias_sem_ver = max(0, (hoje - ultima_data).days)

            sm2 = _calcular_parametros_sm2_ebbinghaus(
                taxa_acerto=taxa_acerto,
                qtd_passagens=qtd_passagens,
                dias_desde_ultimo=dias_sem_ver,
            )

            data_prox_revisao = ultima_data + timedelta(days=sm2["intervalo_ideal_dias"])
            dias_ate_proxima = (data_prox_revisao - hoje).days

            if dias_ate_proxima < 0 or taxa_acerto < 62.0:
                status_revisao = "ATRASADA_CRITICA"
                status_label = "Urgente / Atrasada"
            elif dias_ate_proxima <= 2 or sm2["retencao_estimada_perc"] < 72.0:
                status_revisao = "PARA_HOJE"
                status_label = "Revisar Neste Ciclo"
            elif dias_ate_proxima <= 7:
                status_revisao = "PROGRAMADA"
                status_label = f"Em {dias_ate_proxima} dias"
            else:
                status_revisao = "CONSOLIDADA"
                status_label = "Memória Estável"

            # Cálculo do Score de Prioridade Anki (0 a 100):
            # Quanto MENOR o rendimento no ciclo e MENOR a retenção atual, MAIOR a prioridade na fila do Anki!
            deficit_rendimento = max(0.0, 100.0 - taxa_acerto)  # 0 a 100
            perda_memoria = max(0.0, 100.0 - sm2["retencao_estimada_perc"])  # 0 a 100
            bonus_pareto = (12.0 if t.prioridade == 1 else (6.0 if t.prioridade == 2 else 2.0)) + (8.0 if t.mais_cobrado else 0.0)
            bonus_atraso = min(18.0, max(0, -dias_ate_proxima) * 2.5)
            bonus_erros = min(12.0, er_tot * 0.8)

            score_anki = round(
                min(
                    99.9,
                    (deficit_rendimento * 0.42)
                    + (perda_memoria * 0.28)
                    + bonus_pareto
                    + bonus_atraso
                    + bonus_erros,
                ),
                1,
            )

            tecnica = _selecionar_tecnica_memorizacao(
                taxa_acerto=taxa_acerto,
                erros_total=er_tot,
                dias_sem_ver=dias_sem_ver,
                prioridade=t.prioridade,
                mais_cobrado=bool(t.mais_cobrado),
            )

            motivo_escolha = (
                f"Rendimento de {taxa_acerto}% ({ac_tot}/{q_tot}q, {er_tot} erros) • "
                f"Retenção estimada em {sm2['retencao_estimada_perc']}% após {dias_sem_ver}d sem contato • "
                f"Técnica: {tecnica['nome']}."
            )

            from app.services.tec_matching_service import montar_dados_vinculo_topico
            tec_vinc = montar_dados_vinculo_topico(t, getattr(t, "vinculo_tec", None))

            # Linha do tempo de evolução de rendimento do tópico (1º estudo -> revisões sucessivas)
            evolucao_rendimento = []
            rev_seq = 0
            taxa_prev = None
            for idx_ev, s_ev in enumerate(lista_s):
                q_ev = int(s_ev.qtd_questoes_total or 0)
                if q_ev <= 0:
                    continue
                ac_ev = int(s_ev.qtd_acertos or 0)
                taxa_ev = round((ac_ev / q_ev) * 100.0, 1)
                if len(evolucao_rendimento) == 0 and not bool(s_ev.is_revisao_anki):
                    etapa_lbl = "1º Estudo"
                else:
                    rev_seq += 1
                    etapa_lbl = f"Rev. Anki #{rev_seq}" if bool(s_ev.is_revisao_anki) else f"Revisão #{rev_seq}"
                delta_ev = round(taxa_ev - taxa_prev, 1) if taxa_prev is not None else None
                evolucao_rendimento.append({
                    "ordem": len(evolucao_rendimento) + 1,
                    "etapa": etapa_lbl,
                    "data_fmt": s_ev.data.strftime("%d/%m") if s_ev.data else "",
                    "taxa_perc": taxa_ev,
                    "acertos": ac_ev,
                    "total": q_ev,
                    "is_revisao_anki": bool(s_ev.is_revisao_anki),
                    "delta_pp": delta_ev,
                })
                taxa_prev = taxa_ev

            primeiro_rend = evolucao_rendimento[0]["taxa_perc"] if evolucao_rendimento else None
            ultimo_rend = evolucao_rendimento[-1]["taxa_perc"] if evolucao_rendimento else None
            delta_evolucao_total = (
                round(ultimo_rend - primeiro_rend, 1)
                if (len(evolucao_rendimento) >= 2 and primeiro_rend is not None and ultimo_rend is not None)
                else None
            )

            topicos_analisados.append({
                "topico_id": t.id,
                "topico_titulo": t.titulo,
                "disciplina_id": d.id,
                "disciplina_nome": d.nome,
                "grupo_conhecimento": d.grupo_conhecimento,
                "peso_prova": d.peso_prova,
                "prioridade": t.prioridade,
                "mais_cobrado": bool(t.mais_cobrado),
                "questoes_resolvidas": q_tot,
                "acertos": ac_tot,
                "erros": er_tot,
                "tempo_estudado_min": min_tot,
                "taxa_acerto_perc": taxa_acerto,
                "qtd_passagens_ciclo": qtd_passagens,
                "qtd_revisoes_feitas": qtd_revisoes_topico,
                "ultima_data_iso": ultima_data.isoformat(),
                "ultima_data_fmt": ultima_data.strftime("%d/%m/%Y"),
                "dias_desde_ultimo_estudo": dias_sem_ver,
                "proxima_revisao_iso": data_prox_revisao.isoformat(),
                "proxima_revisao_fmt": data_prox_revisao.strftime("%d/%m/%Y"),
                "dias_ate_proxima_revisao": dias_ate_proxima,
                "status_revisao": status_revisao,
                "status_label": status_label,
                "ease_factor": sm2["ease_factor"],
                "intervalo_ideal_dias": sm2["intervalo_ideal_dias"],
                "estagio_revisao": sm2["estagio_revisao"],
                "retencao_estimada_perc": sm2["retencao_estimada_perc"],
                "score_prioridade_anki": score_anki,
                "tecnica_recomendada": tecnica,
                "motivo_escolha": motivo_escolha,
                "tec_vinculo": tec_vinc,
                "evolucao_rendimento": evolucao_rendimento,
                "primeiro_rendimento_perc": primeiro_rend,
                "ultimo_rendimento_perc": ultimo_rend,
                "delta_evolucao_pp": delta_evolucao_total,
            })

    # Se nenhum tópico foi estudado ainda, cria sugestão inicial com o primeiro tópico P1 do edital
    if not topicos_analisados and disciplinas_validas:
        d0 = disciplinas_validas[0]
        t0 = (d0.topicos or [None])[0]
        if t0:
            tecnica0 = CATALOGO_TECNICAS_MEMORIZACAO[1]
            topicos_analisados.append({
                "topico_id": t0.id,
                "topico_titulo": t0.titulo,
                "disciplina_id": d0.id,
                "disciplina_nome": d0.nome,
                "grupo_conhecimento": d0.grupo_conhecimento,
                "peso_prova": d0.peso_prova,
                "prioridade": t0.prioridade,
                "mais_cobrado": bool(t0.mais_cobrado),
                "questoes_resolvidas": 0,
                "acertos": 0,
                "erros": 0,
                "tempo_estudado_min": 0,
                "taxa_acerto_perc": 0.0,
                "qtd_passagens_ciclo": 0,
                "qtd_revisoes_feitas": 0,
                "ultima_data_iso": hoje.isoformat(),
                "ultima_data_fmt": hoje.strftime("%d/%m/%Y"),
                "dias_desde_ultimo_estudo": 0,
                "proxima_revisao_iso": hoje.isoformat(),
                "proxima_revisao_fmt": hoje.strftime("%d/%m/%Y"),
                "dias_ate_proxima_revisao": 0,
                "status_revisao": "PARA_HOJE",
                "status_label": "Revisão Inicial",
                "ease_factor": 2.5,
                "intervalo_ideal_dias": 1,
                "estagio_revisao": "Ciclo 24h (Fixação Inicial)",
                "retencao_estimada_perc": 70.0,
                "score_prioridade_anki": 80.0,
                "tecnica_recomendada": {
                    "codigo": tecnica0["codigo"],
                    "nome": tecnica0["nome"],
                    "icone": tecnica0["icone"],
                    "cor": tecnica0["cor"],
                    "orientacao_curta": tecnica0["como_aplicar"],
                },
                "motivo_escolha": "Tópico prioritário inicial para abertura do baralho de revisão espaçada.",
                "tec_vinculo": None,
            })

    # 5. Sequência Ordenada das Próximas Revisões do Anki (do maior score_prioridade_anki para o menor, priorizando tópicos com questões e erros reais)
    fila_sequencial_anki = sorted(
        topicos_analisados,
        key=lambda x: (
            0 if x["questoes_resolvidas"] > 0 else 1,
            -x["score_prioridade_anki"],
            x["taxa_acerto_perc"],
            -x["dias_desde_ultimo_estudo"],
        ),
    )
    for idx_f, item_f in enumerate(fila_sequencial_anki, start=1):
        item_f["ordem_fila_anki"] = idx_f

    # 6. Ranking de Pior Rendimento nos Ciclos (ordenado pela menor taxa de acerto entre os tópicos com questões feitas, seguido dos demais)
    ranking_pior_rendimento = sorted(
        topicos_analisados,
        key=lambda x: (
            0 if x["questoes_resolvidas"] > 0 else 1,
            x["taxa_acerto_perc"],
            -x["erros"],
            -x["score_prioridade_anki"],
        ),
    )
    topico_pior_rendimento_destaque = ranking_pior_rendimento[0] if ranking_pior_rendimento else None

    # 7. Resumo por Disciplina (rendimento médio nos tópicos vistos vs retenção média de memória)
    vulnerabilidade_disciplinas: List[Dict[str, Any]] = []
    for d in disciplinas_validas:
        tops_d = [x for x in topicos_analisados if x["disciplina_id"] == d.id]
        if not tops_d:
            continue
        media_acerto_d = round(sum(x["taxa_acerto_perc"] for x in tops_d) / len(tops_d), 1)
        media_retencao_d = round(sum(x["retencao_estimada_perc"] for x in tops_d) / len(tops_d), 1)
        pior_top_d = min(tops_d, key=lambda x: (x["taxa_acerto_perc"], -x["erros"]))
        urgentes_d = sum(1 for x in tops_d if x["status_revisao"] in ("ATRASADA_CRITICA", "PARA_HOJE"))
        vulnerabilidade_disciplinas.append({
            "disciplina_id": d.id,
            "disciplina_nome": d.nome,
            "qtd_topicos_vistos": len(tops_d),
            "qtd_revisoes_urgentes": urgentes_d,
            "taxa_acerto_media_perc": media_acerto_d,
            "retencao_media_perc": media_retencao_d,
            "pior_topico_id": pior_top_d["topico_id"],
            "pior_topico_titulo": pior_top_d["topico_titulo"],
            "pior_topico_acerto_perc": pior_top_d["taxa_acerto_perc"],
            "pior_topico_erros": pior_top_d["erros"],
        })

    vulnerabilidade_disciplinas.sort(key=lambda x: (x["taxa_acerto_media_perc"], x["retencao_media_perc"]))

    # 8. Mapeamento dos blocos REVISÃO ANKI na Esteira Sequencial do Ciclo Atual
    mapeamento_esteira_anki: List[Dict[str, Any]] = []
    if ciclo and ciclo.blocos:
        blocos_ord = sorted(ciclo.blocos, key=lambda b: b.ordem)
        idx_atual_ciclo = (ciclo.bloco_atual_index or 0) % len(blocos_ord)
        # Ordem de encontro dos blocos REVISAO_ANKI a partir da posição atual da esteira
        blocos_rot = [( (idx_atual_ciclo + offset) % len(blocos_ord), offset, blocos_ord[(idx_atual_ciclo + offset) % len(blocos_ord)] ) for offset in range(len(blocos_ord))]
        anki_seq_counter = 0
        for pos_esteira, dist_blocos, b_obj in blocos_rot:
            if b_obj.disciplina and (b_obj.disciplina.categoria == "REVISAO_ANKI" or b_obj.disciplina.nome == "REVISÃO ANKI"):
                alvo = fila_sequencial_anki[anki_seq_counter % len(fila_sequencial_anki)] if fila_sequencial_anki else None
                anki_seq_counter += 1
                if alvo:
                    mapeamento_esteira_anki.append({
                        "ordem_encontro_anki": anki_seq_counter,
                        "bloco_id": b_obj.id,
                        "posicao_esteira_numero": pos_esteira + 1,
                        "distancia_blocos_ate_ele": dist_blocos,
                        "eh_bloco_atual": dist_blocos == 0,
                        "duracao_minutos": b_obj.duracao_minutos,
                        "disciplina_id": alvo["disciplina_id"],
                        "disciplina_nome": alvo["disciplina_nome"],
                        "topico_id": alvo["topico_id"],
                        "topico_titulo": alvo["topico_titulo"],
                        "taxa_acerto_perc": alvo["taxa_acerto_perc"],
                        "retencao_estimada_perc": alvo["retencao_estimada_perc"],
                        "estagio_revisao": alvo["estagio_revisao"],
                        "tecnica_recomendada": alvo["tecnica_recomendada"]["nome"],
                        "motivo_escolha": alvo["motivo_escolha"],
                    })

    # 9. Dados para os 3 Gráficos Visuais:
    # (A) Curva de Ebbinghaus (Sem Revisão vs Com Revisões Espaçadas 1d/7d/15d/30d)
    dias_eixo = [0, 1, 2, 3, 5, 7, 10, 14, 15, 21, 30]
    curva_sem_revisao = [round(100.0 * math.exp(-d / 4.5), 1) for d in dias_eixo]
    curva_com_anki = []
    for d in dias_eixo:
        if d == 0:
            curva_com_anki.append(100.0)
        elif d <= 1:
            curva_com_anki.append(94.0)
        elif d <= 7:
            curva_com_anki.append(round(96.0 * math.exp(-(d - 1) / 18.0), 1))
        elif d <= 15:
            curva_com_anki.append(round(97.0 * math.exp(-(d - 7) / 32.0), 1))
        else:
            curva_com_anki.append(round(98.0 * math.exp(-(d - 15) / 65.0), 1))

    # Posição estimada dinâmica do aluno na Curva de Ebbinghaus (atualiza a cada revisão!)
    if topicos_analisados:
        media_dias_sem_revisar = round(
            sum(min(30, int(x["dias_desde_ultimo_estudo"])) for x in topicos_analisados) / len(topicos_analisados),
            1,
        )
    else:
        media_dias_sem_revisar = 0.0

    # Encontra o ponto do eixo X mais próximo da média real de dias desde a última revisão/estudo
    indice_eixo_usuario = min(
        range(len(dias_eixo)),
        key=lambda idx: abs(dias_eixo[idx] - media_dias_sem_revisar),
    )
    dia_eixo_usuario = dias_eixo[indice_eixo_usuario]
    ret_atual_plot = round(
        sum(x["retencao_estimada_perc"] for x in topicos_analisados) / len(topicos_analisados), 1
    ) if topicos_analisados else 100.0

    ponto_usuario = [None] * len(dias_eixo)
    ponto_usuario[indice_eixo_usuario] = ret_atual_plot

    if ret_atual_plot >= 75.0:
        zona_ebbinghaus = "Zona Blindada (Memória Forte)"
        explicacao_posicao = (
            f"Você está no Dia {dia_eixo_usuario} com {ret_atual_plot}% de retenção média estimada "
            f"(média de {media_dias_sem_revisar} dias desde o último contato com seus tópicos). "
            f"Sua constância de revisões está mantendo a memória próxima da curva verde ideal!"
        )
    elif ret_atual_plot >= 40.0:
        zona_ebbinghaus = "Zona de Atenção (Revisão Recomendada)"
        explicacao_posicao = (
            f"Você está no Dia {dia_eixo_usuario} com {ret_atual_plot}% de retenção média estimada "
            f"(média de {media_dias_sem_revisar} dias desde o último contato). "
            f"A cada revisão feita no Anki/Ciclo, seu ponto azul sobe em direção à curva verde."
        )
    else:
        zona_ebbinghaus = "Zona de Esquecimento (Alerta Ebbinghaus)"
        explicacao_posicao = (
            f"Você está no Dia {dia_eixo_usuario} com {ret_atual_plot}% de retenção média estimada "
            f"(média de {media_dias_sem_revisar} dias sem revisar os tópicos estudados). "
            f"Ao concluir as revisões urgentes da fila, seu ponto azul sobe rapidamente e recua para a esquerda rumo à curva verde!"
        )

    posicao_usuario_ebbinghaus = {
        "indice_eixo": indice_eixo_usuario,
        "dia_eixo": dia_eixo_usuario,
        "dia_estimado_label": f"Dia {dia_eixo_usuario}",
        "media_dias_sem_revisar": media_dias_sem_revisar,
        "retencao_atual_perc": ret_atual_plot,
        "zona": zona_ebbinghaus,
        "explicacao": explicacao_posicao,
    }

    # (B) Constância de Revisões (14 dias recentes ou janela ancorada na última revisão/sessão registrada)
    inicio_recente_14d = hoje - timedelta(days=13)
    tem_revisao_recente = any(
        r["data_iso"] >= inicio_recente_14d.isoformat() for r in historico_revisoes_feitas
    )
    if tem_revisao_recente:
        data_fim_janela = hoje
        fonte_constancia = historico_revisoes_feitas
    elif historico_revisoes_feitas:
        # Ancora a janela de 14 dias na data da última revisão registrada no servidor
        try:
            data_fim_janela = date.fromisoformat(historico_revisoes_feitas[0]["data_iso"][:10])
        except Exception:
            data_fim_janela = hoje
        fonte_constancia = historico_revisoes_feitas
    elif todas_sessoes:
        # Fallback: se não houver revisões marcadas ainda, usa a janela das últimas sessões de estudo
        datas_sessoes = [s.data for s in todas_sessoes if s.data]
        data_fim_janela = max(datas_sessoes) if datas_sessoes else hoje
        fonte_constancia = [
            {
                "data_iso": s.data.isoformat() if s.data else hoje.isoformat(),
                "tempo_minutos": int(s.tempo_estudado_minutos or 0),
                "questoes_total": int(s.qtd_questoes_total or 0),
            }
            for s in todas_sessoes
        ]
    else:
        data_fim_janela = hoje
        fonte_constancia = []

    constancia_14d = []
    for offset_d in range(13, -1, -1):
        dt_ref = data_fim_janela - timedelta(days=offset_d)
        dt_iso = dt_ref.isoformat()
        revs_dia = [r for r in fonte_constancia if r["data_iso"] == dt_iso]
        min_dia = sum(r["tempo_minutos"] for r in revs_dia)
        q_dia = sum(r["questoes_total"] for r in revs_dia)
        constancia_14d.append({
            "data_fmt": dt_ref.strftime("%d/%m"),
            "qtd_revisoes": len(revs_dia),
            "minutos": min_dia,
            "questoes": q_dia,
        })

    # 10. Enriquecimento do Catálogo de Técnicas com os tópicos reais do aluno para cada técnica
    tecnicas_com_topicos = []
    for tec in CATALOGO_TECNICAS_MEMORIZACAO:
        topicos_desta_tec = [
            {
                "topico_id": x["topico_id"],
                "topico_titulo": x["topico_titulo"],
                "disciplina_id": x["disciplina_id"],
                "disciplina_nome": x["disciplina_nome"],
                "taxa_acerto_perc": x["taxa_acerto_perc"],
                "retencao_estimada_perc": x["retencao_estimada_perc"],
            }
            for x in fila_sequencial_anki
            if x["tecnica_recomendada"]["codigo"] == tec["codigo"]
        ]
        tecnicas_com_topicos.append({
            **tec,
            "qtd_topicos_recomendados": len(topicos_desta_tec),
            "topicos_recomendados": topicos_desta_tec[:6],
        })

    # KPIs Globais de Revisão
    total_revisoes_feitas = len(historico_revisoes_feitas)
    minutos_revisoes_total = sum(r["tempo_minutos"] for r in historico_revisoes_feitas)
    horas_revisoes_total = round(minutos_revisoes_total / 60.0, 1)
    questoes_em_revisoes = sum(r["questoes_total"] for r in historico_revisoes_feitas)
    retencao_media_global = (
        round(sum(x["retencao_estimada_perc"] for x in topicos_analisados) / len(topicos_analisados), 1)
        if topicos_analisados
        else 0.0
    )
    qtd_atrasadas_criticas = sum(1 for x in topicos_analisados if x["status_revisao"] == "ATRASADA_CRITICA")
    qtd_para_hoje = sum(1 for x in topicos_analisados if x["status_revisao"] == "PARA_HOJE")

    return {
        "edital_id": edital.id,
        "edital_nome": edital.nome,
        "ciclo_id": ciclo.id if ciclo else None,
        "kpis": {
            "total_revisoes_feitas": total_revisoes_feitas,
            "horas_revisoes_total": horas_revisoes_total,
            "questoes_em_revisoes": questoes_em_revisoes,
            "total_topicos_mapeados": len(topicos_analisados),
            "retencao_media_global_perc": retencao_media_global,
            "qtd_revisoes_criticas": qtd_atrasadas_criticas,
            "qtd_revisoes_para_hoje": qtd_para_hoje,
            "qtd_urgent_total": qtd_atrasadas_criticas + qtd_para_hoje,
        },
        "destaque_pior_rendimento": topico_pior_rendimento_destaque,
        "proxima_revisao_anki_esteira": fila_sequencial_anki[0] if fila_sequencial_anki else None,
        "mapeamento_esteira_anki": mapeamento_esteira_anki,
        "fila_sequencial_anki": fila_sequencial_anki,
        "ranking_pior_rendimento": ranking_pior_rendimento,
        "vulnerabilidade_disciplinas": vulnerabilidade_disciplinas,
        "historico_revisoes_feitas": historico_revisoes_feitas,
        "tecnicas_memorizacao": tecnicas_com_topicos,
        "graficos": {
            "curva_ebbinghaus": {
                "labels": [f"Dia {d}" for d in dias_eixo],
                "sem_revisao": curva_sem_revisao,
                "com_revisao_anki": curva_com_anki,
                "ponto_usuario": ponto_usuario,
                "posicao_usuario": posicao_usuario_ebbinghaus,
            },
            "constancia_14d": constancia_14d,
            "vulnerabilidade_disciplinas": vulnerabilidade_disciplinas[:10],
        },
    }


def mapear_topicos_para_blocos_anki_do_ciclo(db: Session, ciclo: CicloEstudos) -> Dict[int, Dict[str, Any]]:
    """
    Para cada bloco REVISAO_ANKI do ciclo ativo, retorna o dicionário compatível com
    `TopicoApontadoCiclo` indicando a melhor Disciplina e Tópico a revisar naquele bloco
    segundo o rendimento nos ciclos e a curva de esquecimento (Anki / SM-2).
    """
    if not ciclo or not ciclo.blocos:
        return {}

    diag = diagnosticar_fila_revisoes_anki(db, edital_id=ciclo.edital_id)
    fila = diag.get("fila_sequencial_anki") or []
    if not fila:
        return {}

    blocos_ord = sorted(ciclo.blocos, key=lambda b: b.ordem)
    idx_atual = (ciclo.bloco_atual_index or 0) % len(blocos_ord)
    blocos_rot = [blocos_ord[(idx_atual + offset) % len(blocos_ord)] for offset in range(len(blocos_ord))]

    mapa_bloco_topico: Dict[int, Dict[str, Any]] = {}
    contador_anki = 0
    for b in blocos_rot:
        if b.disciplina and (b.disciplina.categoria == "REVISAO_ANKI" or b.disciplina.nome == "REVISÃO ANKI"):
            escolhido = fila[contador_anki % len(fila)]
            contador_anki += 1
            mapa_bloco_topico[b.id] = {
                "id": escolhido["topico_id"],
                "titulo": escolhido["topico_titulo"],
                "ordem": contador_anki,
                "ordem_trilha": contador_anki,
                "prioridade": escolhido["prioridade"],
                "mais_cobrado": escolhido["mais_cobrado"],
                "motivo_ia": (
                    f"🧠 Revisão Anki #{contador_anki} • {escolhido['disciplina_nome']} "
                    f"(Acerto: {escolhido['taxa_acerto_perc']}% | Retenção: {escolhido['retencao_estimada_perc']}% | "
                    f"{escolhido['estagio_revisao']} — {escolhido['tecnica_recomendada']['nome']})"
                ),
                "concluido": False,
                "visto": True,
                "tec_vinculo": escolhido.get("tec_vinculo"),
                "disciplina_id": escolhido["disciplina_id"],
                "disciplina_nome": escolhido["disciplina_nome"],
                "taxa_acerto_perc": escolhido["taxa_acerto_perc"],
                "retencao_estimada_perc": escolhido["retencao_estimada_perc"],
                "estagio_revisao": escolhido["estagio_revisao"],
                "tecnica_recomendada": escolhido["tecnica_recomendada"]["nome"],
                "eh_revisao_anki": True,
            }

    return mapa_bloco_topico
