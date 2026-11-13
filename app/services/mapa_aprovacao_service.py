import json
import math
import httpx
from datetime import date, datetime, timedelta
from collections import defaultdict
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session, selectinload

from app.models.configuracao_prova import ConfiguracaoPainelProva
from app.models.edital import Edital
from app.models.disciplina import Disciplina
from app.models.topico import Topico
from app.models.sessao import SessaoEstudo
from app.models.ciclo import CicloEstudos
from app.routers.ia_insights import obter_chave_gemini, MODELOS_GEMINI_ATIVOS, extrair_json_resiliente


def _garantir_config(db: Session) -> ConfiguracaoPainelProva:
    config = db.query(ConfiguracaoPainelProva).first()
    if not config:
        config = ConfiguracaoPainelProva(id=1)
        db.add(config)
        db.commit()
        db.refresh(config)
    return config


def _calcular_benchmark_ia_padrao(
    area_concurso: str,
    cargo: str,
    banca: str,
    estilo_banca: str,
    eh_nota_liquida: bool,
    fator_penalidade: float,
) -> Dict[str, Any]:
    """Calcula a referência típica de aprovados por carreira, cargo e banca."""
    area_low = (area_concurso or "").lower()
    cargo_low = (cargo or "").lower()
    if eh_nota_liquida:
        nota_sug = 64.0 if ("fiscal" in area_low or "auditor" in cargo_low or "controle" in area_low) else 68.0
        faixa_sug = f"{nota_sug - 4:.0f}% a {nota_sug + 4:.0f}% líquidos (banca {banca})"
        p_bruta_nec = round((((nota_sug / 100.0) + fator_penalidade) / (1.0 + fator_penalidade)) * 100.0, 1)
        justif_bench = (
            f"Em provas {banca} ({estilo_banca}) para {cargo} ({area_concurso}), "
            f"a penalidade de {fator_penalidade:g}x por erro comprime a nota líquida dos aprovados para a faixa de {faixa_sug}. "
            f"Para atingir {nota_sug:.1f}% líquidos (Bruta - Erros), o candidato precisa de ~{p_bruta_nec}% de acerto bruto."
        )
    else:
        nota_sug = 78.0 if ("fiscal" in area_low or "auditor" in cargo_low) else 80.0
        faixa_sug = f"{nota_sug - 3:.0f}% a {nota_sug + 4:.0f}% (múltipla escolha)"
        p_bruta_nec = nota_sug
        justif_bench = (
            f"Para {cargo} ({area_concurso}) na banca {banca} sem anulação de erros, "
            f"os aprovados nas vagas costumam pontuar entre {faixa_sug}."
        )
    return {
        "nota_aprovados_sugerida_perc": nota_sug,
        "faixa_aprovados_perc": faixa_sug,
        "taxa_acerto_bruta_necessaria_perc": p_bruta_nec,
        "justificativa_banca_cargo": justif_bench,
    }


def _obter_edital_ativo(db: Session, edital_id: Optional[int] = None) -> Optional[Edital]:
    query = db.query(Edital).options(
        selectinload(Edital.disciplinas).selectinload(Disciplina.topicos)
    )
    if edital_id:
        ed = query.filter(Edital.id == edital_id).first()
        if ed:
            return ed

    ciclo = db.query(CicloEstudos).filter(CicloEstudos.ativo == True).first()
    if ciclo and ciclo.edital_id:
        ed = query.filter(Edital.id == ciclo.edital_id).first()
        if ed:
            return ed

    return query.order_by(Edital.data_criacao.desc()).first()


def calcular_mapa_aprovacao(db: Session, edital_id: Optional[int] = None) -> Dict[str, Any]:
    config = _garantir_config(db)
    edital = _obter_edital_ativo(db, edital_id)

    hoje = date.today()
    data_prova_str = config.data_prova or "2026-11-29"
    try:
        data_prova_dt = datetime.strptime(data_prova_str, "%Y-%m-%d").date()
        dias_restantes = (data_prova_dt - hoje).days
    except Exception:
        data_prova_dt = hoje + timedelta(days=45)
        dias_restantes = 45

    dias_uteis_horizonte = max(1, dias_restantes)
    semanas_restantes = round(max(0.5, dias_uteis_horizonte / 7.0), 1)

    # Parâmetros da prova e critérios eliminatórios
    banca = config.banca or "Cebraspe"
    estilo_banca = config.estilo_banca or "Certo / Errado (1 anula 1)"
    tipo_data_prova = getattr(config, "tipo_data_prova", None) or "Confirmada"
    nota_corte = float(config.nota_corte if config.nota_corte is not None else 78.5)
    nota_minima_geral = float(getattr(config, "nota_minima_geral", None) or 60.0)
    nota_minima_basicos = float(getattr(config, "nota_minima_basicos", None) or 50.0)
    nota_minima_especificos = float(getattr(config, "nota_minima_especificos", None) or 60.0)
    nota_minima_disciplina = float(getattr(config, "nota_minima_disciplina", None) if getattr(config, "nota_minima_disciplina", None) is not None else 0.0)
    nao_zerar_raw = getattr(config, "nao_zerar_disciplina", None)
    nao_zerar_disciplina = True if nao_zerar_raw is None else bool(nao_zerar_raw)
    fator_penalidade_erro = float(getattr(config, "fator_penalidade_erro", None) if getattr(config, "fator_penalidade_erro", None) is not None else 0.0)
    estilo_lower = (estilo_banca or "").lower()
    banca_lower = (banca or "").lower()
    eh_cebraspe_ce = ("anula" in estilo_lower) or ("certo / errado" in estilo_lower) or ("certo/errado" in estilo_lower) or ("cebraspe" in banca_lower and "múltipla" not in estilo_lower and "multipla" not in estilo_lower)
    fator_penalidade_efetivo = 1.0 if (fator_penalidade_erro == 0.0 and eh_cebraspe_ce) else fator_penalidade_erro
    modo_pontuacao = (
        f"Nota Líquida (Banca {banca}: penalidade {fator_penalidade_efetivo:g}x por erro)"
        if fator_penalidade_efetivo > 0
        else "Nota Bruta (Sem penalidade por erro)"
    )

    # Parâmetros de Gestão Temporal
    meta_conclusao_edital = float(getattr(config, "meta_conclusao_edital", None) or 85.0)
    dias_disponiveis_semana = int(getattr(config, "dias_disponiveis_semana", None) or 6)
    dias_disponiveis_semana = max(1, min(7, dias_disponiveis_semana))
    horas_estudo_dia = float(getattr(config, "horas_estudo_dia", None) or 4.0)
    horas_por_topico = float(getattr(config, "horas_por_topico", None) or 1.5)
    dias_antecedencia_revisao = int(getattr(config, "dias_antecedencia_revisao", None) if getattr(config, "dias_antecedencia_revisao", None) is not None else 21)
    horas_simulado_semana = float(getattr(config, "horas_simulado_semana", None) if getattr(config, "horas_simulado_semana", None) is not None else 4.0)

    if not edital:
        return {"erro": "Nenhum edital encontrado."}

    disciplinas_validas = [
        d for d in edital.disciplinas
        if d.categoria != "REVISAO_ANKI" and (d.nome or "").upper() != "REVISÃO ANKI"
    ]
    disciplinas_validas.sort(key=lambda d: (0 if d.grupo_conhecimento == "BASICOS" else 1, d.id))

    # Sessões de estudo do edital
    todas_sessoes = (
        db.query(SessaoEstudo)
        .join(Disciplina, SessaoEstudo.disciplina_id == Disciplina.id)
        .filter(Disciplina.edital_id == edital.id)
        .order_by(SessaoEstudo.data.asc())
        .all()
    )

    sessoes_por_disc: Dict[int, List[SessaoEstudo]] = defaultdict(list)
    sessoes_por_topico: Dict[int, List[SessaoEstudo]] = defaultdict(list)
    for s in todas_sessoes:
        sessoes_por_disc[s.disciplina_id].append(s)
        if s.topico_id is not None:
            sessoes_por_topico[s.topico_id].append(s)

    total_questoes_feitas_global = sum((s.qtd_questoes_total or 0) for s in todas_sessoes)
    total_acertos_global = sum((s.qtd_acertos or 0) for s in todas_sessoes)
    total_erros_global = max(0, total_questoes_feitas_global - total_acertos_global)
    taxa_global_observada = (total_acertos_global / total_questoes_feitas_global * 100.0) if total_questoes_feitas_global > 0 else 65.0

    # Prior Bayesiano para suavizar disciplinas com poucas questões registradas
    prior_acerto = max(50.0, min(92.0, taxa_global_observada * 0.96)) if total_questoes_feitas_global >= 20 else 60.0
    k_credibilidade = 15.0  # Peso de estabilização amostral (15 questões)

    # 1. Cálculo de Pontos e Pesos Totais da Prova
    total_questoes_prova = 0
    total_pontos_prova = 0.0
    questoes_basicos = 0
    pontos_basicos = 0.0
    questoes_especificos = 0
    pontos_especificos = 0.0

    disc_raw_meta = []
    for d in disciplinas_validas:
        q_prova = int(d.qtd_questoes_prova) if (d.qtd_questoes_prova is not None and d.qtd_questoes_prova > 0) else 10
        peso = float(d.peso_prova) if (d.peso_prova is not None and d.peso_prova > 0) else 1.0
        pts_max = round(q_prova * peso, 2)

        total_questoes_prova += q_prova
        total_pontos_prova += pts_max
        if d.grupo_conhecimento == "BASICOS":
            questoes_basicos += q_prova
            pontos_basicos += pts_max
        else:
            questoes_especificos += q_prova
            pontos_especificos += pts_max

        disc_raw_meta.append((d, q_prova, peso, pts_max))

    if total_pontos_prova <= 0:
        total_pontos_prova = 100.0

    # 2. Análise Detalhada por Disciplina + Conteúdo Não Estudado
    disciplinas_detalhe = []
    soma_pontos_estimados = 0.0
    soma_pontos_brutos_estimados = 0.0
    soma_pontos_observados = 0.0
    soma_variancia_pontos = 0.0

    soma_pontos_est_basicos = 0.0
    soma_pontos_est_especificos = 0.0

    total_topicos_edital = 0
    total_topicos_estudados = 0
    total_topicos_em_andamento = 0
    total_topicos_nao_estudados = 0
    total_p1_pendentes = 0
    total_mc_pendentes = 0

    for d, q_prova, peso, pts_max in disc_raw_meta:
        representatividade_perc = round((pts_max / total_pontos_prova) * 100.0, 2)
        s_disc = sessoes_por_disc.get(d.id, [])
        q_res = sum((s.qtd_questoes_total or 0) for s in s_disc)
        q_ac = sum((s.qtd_acertos or 0) for s in s_disc)
        q_er = sum((s.qtd_erros or 0) for s in s_disc)
        min_est = sum((s.tempo_estudado_minutos or 0) for s in s_disc)
        horas_est = round(min_est / 60.0, 1)

        taxa_obs = round((q_ac / q_res) * 100.0, 1) if q_res > 0 else None

        # Tópicos da disciplina
        topicos_disc = sorted(d.topicos, key=lambda t: (t.ordem if t.ordem is not None else 0, t.id))
        n_top = len(topicos_disc)
        n_concluidos = 0
        n_andamento = 0
        n_nao_estudados = 0
        p1_pend = 0
        mc_pend = 0

        topicos_lista_projeto = []
        for t in topicos_disc:
            s_top = sessoes_por_topico.get(t.id, [])
            tem_sessao = len(s_top) > 0
            concl = bool(t.concluido)
            q_top = sum((s.qtd_questoes_total or 0) for s in s_top)
            a_top = sum((s.qtd_acertos or 0) for s in s_top)
            taxa_top = round((a_top / q_top) * 100.0, 1) if q_top > 0 else None

            if concl:
                status_top = "concluido"
                n_concluidos += 1
            elif tem_sessao:
                status_top = "em_andamento"
                n_andamento += 1
            else:
                status_top = "nao_estudado"
                n_nao_estudados += 1
                if getattr(t, "prioridade", None) == 1:
                    p1_pend += 1
                if getattr(t, "mais_cobrado", False):
                    mc_pend += 1

            topicos_lista_projeto.append({
                "id": t.id,
                "titulo": t.titulo,
                "ordem": t.ordem if t.ordem is not None else 0,
                "ordem_trilha": getattr(t, "ordem_trilha", None),
                "prioridade": getattr(t, "prioridade", None),
                "mais_cobrado": bool(getattr(t, "mais_cobrado", False)),
                "concluido": concl,
                "status": status_top,
                "questoes": q_top,
                "taxa_acerto": taxa_top
            })

        n_vistos = n_concluidos + n_andamento
        cobertura_perc = round((n_vistos / n_top) * 100.0, 1) if n_top > 0 else (100.0 if q_res > 0 else 0.0)
        frac_coberta = min(1.0, max(0.0, cobertura_perc / 100.0))

        total_topicos_edital += n_top
        total_topicos_estudados += n_vistos
        total_topicos_em_andamento += n_andamento
        total_topicos_nao_estudados += n_nao_estudados
        total_p1_pendentes += p1_pend
        total_mc_pendentes += mc_pend

        # Estimativa Bayesiana + Ajuste por Cobertura do Edital
        # 1) Taxa esperada nos tópicos já estudados (suavizada pelo volume de questões q_res)
        if q_res > 0:
            peso_amostra = q_res / (q_res + k_credibilidade)
            taxa_base_estudada = (peso_amostra * taxa_obs) + ((1.0 - peso_amostra) * prior_acerto)
        else:
            taxa_base_estudada = prior_acerto * 0.90

        # 2) Nos tópicos ainda não estudados (1 - frac_coberta), desconto realista suave (~10%)
        fator_cobertura = 0.90 + (0.10 * frac_coberta)
        taxa_estimada_bruta = min(98.0, max(15.0, taxa_base_estudada * fator_cobertura))

        # 3) Cálculo de Nota Líquida (Cebraspe / bancas com penalidade por erro: Bruta - Erros * fator)
        if fator_penalidade_efetivo > 0:
            p_ac = taxa_estimada_bruta / 100.0
            p_er = 1.0 - p_ac
            taxa_liquida = max(0.0, (p_ac - (p_er * fator_penalidade_efetivo)) * 100.0)
            taxa_estimada = round(min(98.0, max(5.0, taxa_liquida)), 1)
        else:
            taxa_estimada = round(taxa_estimada_bruta, 1)

        # 4) Cálculo da Margem de Incerteza (Erro Padrão Amostral + Incerteza de Tópicos Não Vistos)
        p_prop = min(0.95, max(0.05, taxa_estimada_bruta / 100.0))
        erro_padrao_amostral = math.sqrt((p_prop * (1.0 - p_prop)) / (q_res + 6.0)) * 1.96 * 100.0
        incerteza_cobertura = (1.0 - frac_coberta) * 9.5
        fator_escala_inc = (1.0 + fator_penalidade_efetivo * 0.25) if fator_penalidade_efetivo > 0 else 1.0
        incerteza_disc = round(min(28.0, max(2.2, (erro_padrao_amostral * 0.65 + incerteza_cobertura) * fator_escala_inc)), 1)

        pts_estimados = round(pts_max * (taxa_estimada / 100.0), 2)
        pts_brutos_estimados = round(pts_max * (taxa_estimada_bruta / 100.0), 2)
        pts_observados = round(pts_max * ((taxa_obs if taxa_obs is not None else taxa_estimada_bruta) / 100.0), 2)
        pts_perdidos = round(max(0.0, pts_max - pts_estimados), 2)

        soma_pontos_estimados += pts_estimados
        soma_pontos_brutos_estimados += pts_brutos_estimados
        soma_pontos_observados += pts_observados
        if d.grupo_conhecimento == "BASICOS":
            soma_pontos_est_basicos += pts_estimados
        else:
            soma_pontos_est_especificos += pts_estimados

        # Variância na pontuação final (combinação de erros independentes + correlação sistêmica de prova)
        desvio_pts_disc = pts_max * (incerteza_disc / 100.0)
        soma_variancia_pontos += (desvio_pts_disc ** 2)

        # Meta necessária na disciplina para atingir a pontuação desejada (nota_corte)
        # Disciplinas de maior peso exigem alinhamento firme com a nota de corte
        meta_disc_perc = round(min(95.0, max(nota_corte, nota_minima_disciplina, 65.0)), 1)
        if taxa_estimada >= nota_corte + 5.0:
            # Se o aluno já domina acima do corte, a meta é manter o patamar atual
            meta_disc_perc = round(min(95.0, taxa_estimada), 1)

        questoes_certas_estimadas = round(q_prova * (taxa_estimada / 100.0), 1)
        questoes_certas_meta = math.ceil(q_prova * (meta_disc_perc / 100.0))
        gap_para_meta_perc = round(max(0.0, meta_disc_perc - taxa_estimada), 1)
        deficit_pontos_para_corte = round(max(0.0, (pts_max * (nota_corte / 100.0)) - pts_estimados), 2)

        # Índice de comprometimento da nota final: combina pontos totais desperdiçados e distância ao corte
        comprometimento_pts = round(pts_perdidos, 2)
        comprometimento_perc_nota_final = round((pts_perdidos / total_pontos_prova) * 100.0, 2)

        if taxa_estimada >= nota_corte:
            status_cor = "emerald"
            status_label = "Acima da Meta"
        elif taxa_estimada >= nota_corte - 8.0:
            status_cor = "amber"
            status_label = "Zona de Ajuste"
        else:
            status_cor = "rose"
            status_label = "Gargalo Crítico"

        disciplinas_detalhe.append({
            "id": d.id,
            "nome": d.nome,
            "grupo_conhecimento": d.grupo_conhecimento,
            "categoria": d.categoria,
            "qtd_questoes_prova": q_prova,
            "peso_prova": peso,
            "pontos_maximos": pts_max,
            "representatividade_perc": representatividade_perc,
            "questoes_resolvidas": q_res,
            "acertos": q_ac,
            "erros": q_er,
            "horas_estudadas": horas_est,
            "taxa_observada_perc": taxa_obs if taxa_obs is not None else 0.0,
            "tem_questoes": q_res > 0,
            "taxa_estimada_perc": taxa_estimada,
            "incerteza_perc": incerteza_disc,
            "intervalo_min_perc": round(max(0.0, taxa_estimada - incerteza_disc), 1),
            "intervalo_max_perc": round(min(100.0, taxa_estimada + incerteza_disc), 1),
            "pontos_estimados": pts_estimados,
            "pontos_perdidos_estimados": pts_perdidos,
            "comprometimento_perc_nota_final": comprometimento_perc_nota_final,
            "deficit_pontos_para_corte": deficit_pontos_para_corte,
            "questoes_certas_estimadas": questoes_certas_estimadas,
            "meta_necessaria_perc": meta_disc_perc,
            "questoes_certas_meta": questoes_certas_meta,
            "gap_para_meta_perc": gap_para_meta_perc,
            "topicos_total": n_top,
            "topicos_concluidos": n_concluidos,
            "topicos_em_andamento": n_andamento,
            "topicos_estudados": n_vistos,
            "topicos_nao_estudados": n_nao_estudados,
            "topicos_p1_pendentes": p1_pend,
            "topicos_mais_cobrados_pendentes": mc_pend,
            "cobertura_perc": cobertura_perc,
            "status_cor": status_cor,
            "status_label": status_label,
            "topicos_lista": topicos_lista_projeto
        })

    # 3. Consolidação da Nota Estimada Global (ancorada no Benchmark IA) e Margem de Incerteza
    analise_ia_salva = None
    if getattr(config, "ultimo_mapa_ia", None):
        try:
            analise_ia_salva = json.loads(config.ultimo_mapa_ia)
        except Exception:
            analise_ia_salva = None

    eh_nota_liquida = fator_penalidade_efetivo > 0
    benchmark_padrao = _calcular_benchmark_ia_padrao(
        area_concurso=config.area_concurso or "Fiscal",
        cargo=config.cargo or edital.cargo or "Auditor Fiscal",
        banca=banca,
        estilo_banca=estilo_banca,
        eh_nota_liquida=eh_nota_liquida,
        fator_penalidade=fator_penalidade_efetivo,
    )
    bench_ia = (analise_ia_salva or {}).get("benchmark_aprovados") or {}
    nota_ia_raw = bench_ia.get("nota_aprovados_sugerida_perc")
    nota_bruta_ia_raw = bench_ia.get("taxa_acerto_bruta_necessaria_perc")

    nota_estimada_perc = round(
        float(nota_ia_raw) if isinstance(nota_ia_raw, (int, float)) and nota_ia_raw > 0 else float(benchmark_padrao["nota_aprovados_sugerida_perc"]),
        1,
    )
    nota_estimada_pontos = round(total_pontos_prova * (nota_estimada_perc / 100.0), 2)

    if eh_nota_liquida:
        if isinstance(nota_bruta_ia_raw, (int, float)) and nota_bruta_ia_raw > 0:
            nota_bruta_estimada_perc = round(float(nota_bruta_ia_raw), 1)
        else:
            nota_bruta_estimada_perc = round(
                min(99.0, max(0.0, (((nota_estimada_perc / 100.0) + fator_penalidade_efetivo) / (1.0 + fator_penalidade_efetivo)) * 100.0)),
                1,
            )
    else:
        nota_bruta_estimada_perc = nota_estimada_perc

    aproveitamento_ponderado_obs_perc = round((soma_pontos_observados / total_pontos_prova) * 100.0, 1)

    # Taxa de acerto bruto necessária para alcançar a meta (nota_corte) considerando a penalidade da banca
    if fator_penalidade_efetivo > 0:
        # Nota Líquida = p - (1-p)*f  =>  p = (M + f) / (1 + f)
        meta_frac = nota_corte / 100.0
        p_necessario = min(0.99, max(0.0, (meta_frac + fator_penalidade_efetivo) / (1.0 + fator_penalidade_efetivo)))
        taxa_acerto_bruta_meta_perc = round(p_necessario * 100.0, 1)
        nota_liquida_observada_perc = round(
            max(0.0, ((total_acertos_global - total_erros_global * fator_penalidade_efetivo) / total_questoes_feitas_global) * 100.0),
            1
        ) if total_questoes_feitas_global > 0 else 0.0
    else:
        taxa_acerto_bruta_meta_perc = round(nota_corte, 1)
        nota_liquida_observada_perc = round(taxa_global_observada, 1) if total_questoes_feitas_global > 0 else 0.0

    cobertura_global_edital_perc = round((total_topicos_estudados / total_topicos_edital) * 100.0, 1) if total_topicos_edital > 0 else 0.0

    # Margem provável ajustada: 6.0 p.p. abaixo da nota estimada pela IA; notas superiores permanecem dentro da margem provável
    margem_incerteza_perc = 6.0
    margem_incerteza_pontos = round(total_pontos_prova * (margem_incerteza_perc / 100.0), 1)

    ic_min_perc = round(max(0.0, nota_estimada_perc - margem_incerteza_perc), 1)
    ic_max_perc = 100.0
    ic_min_pts = round(max(0.0, total_pontos_prova * (ic_min_perc / 100.0)), 1)
    ic_max_pts = round(total_pontos_prova, 1)

    ic_bruta_min_perc = round(max(0.0, nota_bruta_estimada_perc - margem_incerteza_perc), 1) if eh_nota_liquida else ic_min_perc
    ic_bruta_max_perc = 100.0

    # Nível de maturidade / confiança estatística da estimativa (0 a 100%)
    fator_q = min(1.0, total_questoes_feitas_global / 1500.0)
    fator_c = cobertura_global_edital_perc / 100.0
    indice_confianca_modelo = int(round((fator_q * 0.55 + fator_c * 0.45) * 100))
    if indice_confianca_modelo >= 75:
        label_confianca = "Alta Maturidade Estatística"
    elif indice_confianca_modelo >= 40:
        label_confianca = "Maturidade Moderada (Em Refinamento)"
    else:
        label_confianca = "Amostragem Inicial (Margem Ampla)"

    # Pontos para a curva de distribuição preditiva (Gaussiana com ápice na nota estimada IA + segunda onda bruta quando houver penalidade)
    sigma_curva = 4.5
    curva_min_x = max(5, min(35, int((nota_estimada_perc - 20.0) // 5) * 5))
    curva_pontos = []
    for x_val in range(curva_min_x, 101, 1):
        z = (x_val - nota_estimada_perc) / sigma_curva
        densidade = round(math.exp(-0.5 * (z ** 2)) * 100.0, 2)
        if eh_nota_liquida:
            z_bruta = (x_val - nota_bruta_estimada_perc) / sigma_curva
            densidade_bruta = round(math.exp(-0.5 * (z_bruta ** 2)) * 100.0, 2)
            dentro_inc_bruta = x_val >= ic_bruta_min_perc
        else:
            densidade_bruta = None
            dentro_inc_bruta = None
        curva_pontos.append({
            "perc": x_val,
            "pontos": round(total_pontos_prova * (x_val / 100.0), 1),
            "densidade": densidade,
            "densidade_bruta": densidade_bruta,
            "dentro_incerteza": x_val >= ic_min_perc,
            "dentro_incerteza_bruta": dentro_inc_bruta,
            "acima_corte": x_val >= nota_corte
        })

    # 4. Verificação dos Critérios Eliminatórios
    perc_est_basicos = round((soma_pontos_est_basicos / pontos_basicos) * 100.0, 1) if pontos_basicos > 0 else nota_estimada_perc
    perc_est_especificos = round((soma_pontos_est_especificos / pontos_especificos) * 100.0, 1) if pontos_especificos > 0 else nota_estimada_perc

    criterios_avaliados = []

    def _avaliar_criterio(nome_crit: str, atual: float, minimo: float, incerteza: float, pts_tot: float):
        if minimo <= 0:
            return None
        min_ic = atual - incerteza
        if atual < minimo:
            st = "alerta_eliminacao"
            msg = f"Abaixo do mínimo eliminatório ({atual:.1f}% < {minimo:.1f}%)"
        elif min_ic < minimo:
            st = "risco_incerteza"
            msg = f"Acima na média ({atual:.1f}%), mas a margem de incerteza ({min_ic:.1f}%) toca a zona de eliminação ({minimo:.1f}%)"
        else:
            st = "seguro"
            msg = f"Margem segura ({atual:.1f}% vs mínimo de {minimo:.1f}%)"
        return {
            "criterio": nome_crit,
            "estimado_perc": round(atual, 1),
            "minimo_exigido_perc": round(minimo, 1),
            "minimo_exigido_pontos": round(pts_tot * (minimo / 100.0), 1),
            "folga_perc": round(atual - minimo, 1),
            "status": st,
            "diagnostico": msg
        }

    c_geral = _avaliar_criterio("Nota Mínima Geral da Prova", nota_estimada_perc, nota_minima_geral, margem_incerteza_perc, total_pontos_prova)
    if c_geral:
        criterios_avaliados.append(c_geral)

    if pontos_basicos > 0:
        c_bas = _avaliar_criterio("Mínimo — Conhecimentos Básicos", perc_est_basicos, nota_minima_basicos, margem_incerteza_perc, pontos_basicos)
        if c_bas:
            criterios_avaliados.append(c_bas)

    if pontos_especificos > 0:
        c_esp = _avaliar_criterio("Mínimo — Conhecimentos Específicos", perc_est_especificos, nota_minima_especificos, margem_incerteza_perc, pontos_especificos)
        if c_esp:
            criterios_avaliados.append(c_esp)

    disciplinas_risco_eliminatorio = []
    for d_item in disciplinas_detalhe:
        if nao_zerar_disciplina and not d_item["tem_questoes"] and d_item["cobertura_perc"] == 0:
            disciplinas_risco_eliminatorio.append({
                "disciplina": d_item["nome"],
                "motivo": "Disciplina ainda sem estudo/questões (Risco de zerar na prova)"
            })
        elif nota_minima_disciplina > 0 and d_item["taxa_estimada_perc"] < nota_minima_disciplina:
            disciplinas_risco_eliminatorio.append({
                "disciplina": d_item["nome"],
                "motivo": f"Estimativa ({d_item['taxa_estimada_perc']}%) abaixo do mínimo por disciplina ({nota_minima_disciplina}%)"
            })

    criterios_avaliados.append({
        "criterio": "Critério por Disciplina (Não Zerar / Mínimo Individual)",
        "estimado_perc": min((d["taxa_estimada_perc"] for d in disciplinas_detalhe), default=0.0),
        "minimo_exigido_perc": max(1.0 if nao_zerar_disciplina else 0.0, nota_minima_disciplina),
        "minimo_exigido_pontos": 0.0,
        "folga_perc": round(min((d["taxa_estimada_perc"] for d in disciplinas_detalhe), default=0.0) - nota_minima_disciplina, 1),
        "status": "alerta_eliminacao" if len(disciplinas_risco_eliminatorio) > 0 else "seguro",
        "diagnostico": (
            f"{len(disciplinas_risco_eliminatorio)} disciplina(s) exigem atenção contra eliminação direta."
            if disciplinas_risco_eliminatorio
            else "Todas as disciplinas operam acima do piso eliminatório individual."
        ),
        "disciplinas_em_risco": disciplinas_risco_eliminatorio
    })

    # 5. Disciplinas que Mais Comprometem a Pontuação (Ranking de Vazamento de Pontos)
    gargalos_pontuacao = sorted(
        disciplinas_detalhe,
        key=lambda x: (x["pontos_perdidos_estimados"], x["deficit_pontos_para_corte"]),
        reverse=True
    )[:6]

    # 6. Meta Necessária para Atingir a Pontuação Desejada
    pontos_meta_desejada = round(total_pontos_prova * (nota_corte / 100.0), 1)
    gap_nota_perc = round(nota_corte - nota_estimada_perc, 1)
    gap_nota_pontos = round(max(0.0, pontos_meta_desejada - nota_estimada_pontos), 1)

    # Plano de alavancagem: onde buscar os pontos que faltam com menor esforço / maior retorno
    alavancas_meta = []
    pontos_acumulados_alavanca = 0.0
    for d_item in sorted(disciplinas_detalhe, key=lambda x: x["deficit_pontos_para_corte"], reverse=True):
        if d_item["deficit_pontos_para_corte"] <= 0:
            continue
        ganho_pts = d_item["deficit_pontos_para_corte"]
        ganho_perc_final = round((ganho_pts / total_pontos_prova) * 100.0, 2)
        questoes_adicionais = max(1, d_item["questoes_certas_meta"] - int(round(d_item["questoes_certas_estimadas"])))
        pontos_acumulados_alavanca += ganho_pts
        alavancas_meta.append({
            "disciplina_id": d_item["id"],
            "nome": d_item["nome"],
            "peso_prova": d_item["peso_prova"],
            "qtd_questoes_prova": d_item["qtd_questoes_prova"],
            "representatividade_perc": d_item["representatividade_perc"],
            "taxa_atual_estimada": d_item["taxa_estimada_perc"],
            "meta_recomendada_perc": d_item["meta_necessaria_perc"],
            "questoes_atuais_estimadas": d_item["questoes_certas_estimadas"],
            "questoes_meta": d_item["questoes_certas_meta"],
            "questoes_adicionais_necessarias": questoes_adicionais,
            "ganho_pontos_prova": ganho_pts,
            "ganho_perc_nota_final": ganho_perc_final
        })

    # 7. Evolução da Estimativa ao Longo do Tempo (Série Histórica Semanal)
    evolucao_estimativa = _calcular_evolucao_temporal_estimativa(
        todas_sessoes=todas_sessoes,
        disciplinas_validas=disc_raw_meta,
        total_pontos_prova=total_pontos_prova,
        total_topicos_edital=max(1, total_topicos_edital),
        prior_acerto=prior_acerto,
        nota_corte=nota_corte,
        nota_estimada_atual=nota_estimada_perc,
        incerteza_atual=margem_incerteza_perc,
        fator_penalidade_efetivo=fator_penalidade_efetivo
    )

    # 8. Camada de Gestão Temporal ("Gerenciamento de Projeto da Aprovação")
    gestao_temporal = _calcular_gestao_temporal_projeto(
        hoje=hoje,
        data_prova_dt=data_prova_dt,
        dias_restantes=dias_restantes,
        tipo_data_prova=tipo_data_prova,
        total_topicos_edital=total_topicos_edital,
        total_topicos_estudados=total_topicos_estudados,
        total_topicos_em_andamento=total_topicos_em_andamento,
        total_topicos_nao_estudados=total_topicos_nao_estudados,
        total_p1_pendentes=total_p1_pendentes,
        total_mc_pendentes=total_mc_pendentes,
        meta_conclusao_edital=meta_conclusao_edital,
        dias_disponiveis_semana=dias_disponiveis_semana,
        horas_estudo_dia=horas_estudo_dia,
        horas_por_topico=horas_por_topico,
        dias_antecedencia_revisao=dias_antecedencia_revisao,
        horas_simulado_semana=horas_simulado_semana,
        disciplinas_detalhe=disciplinas_detalhe
    )

    return {
        "parametros_prova": {
            "edital_id": edital.id,
            "edital_nome": edital.nome,
            "concurso": config.concurso or edital.nome,
            "area_concurso": config.area_concurso or "Fiscal",
            "cargo": config.cargo or edital.cargo or "Auditor Fiscal",
            "especialidade": config.especialidade or "Geral",
            "banca": banca,
            "estilo_banca": estilo_banca,
            "data_prova": data_prova_str,
            "data_prova_fmt": data_prova_dt.strftime("%d/%m/%Y"),
            "tipo_data_prova": tipo_data_prova,
            "dias_restantes": dias_restantes,
            "semanas_restantes": semanas_restantes,
            "total_questoes_prova": total_questoes_prova,
            "total_pontos_prova": round(total_pontos_prova, 1),
            "questoes_basicos": questoes_basicos,
            "pontos_basicos": round(pontos_basicos, 1),
            "questoes_especificos": questoes_especificos,
            "pontos_especificos": round(pontos_especificos, 1),
            "nota_corte": nota_corte,
            "pontos_meta_desejada": pontos_meta_desejada,
            "nota_minima_geral": nota_minima_geral,
            "nota_minima_basicos": nota_minima_basicos,
            "nota_minima_especificos": nota_minima_especificos,
            "nota_minima_disciplina": nota_minima_disciplina,
            "nao_zerar_disciplina": nao_zerar_disciplina,
            "fator_penalidade_erro": fator_penalidade_erro,
            "meta_conclusao_edital": meta_conclusao_edital,
            "dias_disponiveis_semana": dias_disponiveis_semana,
            "horas_estudo_dia": horas_estudo_dia,
            "horas_por_topico": horas_por_topico,
            "dias_antecedencia_revisao": dias_antecedencia_revisao,
            "horas_simulado_semana": horas_simulado_semana
        },
        "estimativa_nota": {
            "nota_estimada_perc": nota_estimada_perc,
            "nota_estimada_pontos": nota_estimada_pontos,
            "nota_bruta_estimada_perc": nota_bruta_estimada_perc,
            "total_pontos_prova": round(total_pontos_prova, 1),
            "aproveitamento_observado_perc": aproveitamento_ponderado_obs_perc,
            "nota_liquida_observada_perc": nota_liquida_observada_perc,
            "taxa_bruta_simples_perc": round(taxa_global_observada, 1) if total_questoes_feitas_global > 0 else 0.0,
            "acertos_globais": total_acertos_global,
            "erros_globais": total_erros_global,
            "taxa_acerto_bruta_meta_perc": taxa_acerto_bruta_meta_perc,
            "eh_nota_liquida": fator_penalidade_efetivo > 0,
            "fator_penalidade_efetivo": fator_penalidade_efetivo,
            "modo_pontuacao": modo_pontuacao,
            "margem_incerteza_perc": margem_incerteza_perc,
            "margem_incerteza_pontos": margem_incerteza_pontos,
            "intervalo_confianca": {
                "min_perc": ic_min_perc,
                "max_perc": ic_max_perc,
                "min_pontos": ic_min_pts,
                "max_pontos": ic_max_pts,
                "bruta_min_perc": ic_bruta_min_perc,
                "bruta_max_perc": ic_bruta_max_perc
            },
            "estimativa_basicos_perc": perc_est_basicos,
            "estimativa_especificos_perc": perc_est_especificos,
            "gap_para_meta_perc": gap_nota_perc,
            "gap_para_meta_pontos": gap_nota_pontos,
            "atingiu_meta_central": nota_estimada_perc >= nota_corte,
            "atingiu_meta_com_margem": ic_min_perc >= nota_corte,
            "meta_dentro_da_incerteza": ic_min_perc < nota_corte <= ic_max_perc,
            "indice_confianca_modelo": indice_confianca_modelo,
            "label_confianca": label_confianca,
            "total_questoes_amostra": total_questoes_feitas_global,
            "cobertura_edital_perc": cobertura_global_edital_perc,
            "aviso_metodologico": (
                f"A nota estimada de {nota_estimada_perc}% (±{margem_incerteza_perc} p.p., faixa de {ic_min_perc}% a {ic_max_perc}%) "
                f"é uma projeção estatística ponderada pelos pesos do edital, volume amostral ({total_questoes_feitas_global} questões) "
                f"e cobertura atual ({cobertura_global_edital_perc}%). Esta estimativa reflete sua tendência atual com margem de incerteza "
                f"e não constitui promessa ou garantia de aprovação."
            ),
            "curva_distribuicao": curva_pontos
        },
        "criterios_eliminatorios": criterios_avaliados,
        "disciplinas": disciplinas_detalhe,
        "gargalos_pontuacao": gargalos_pontuacao,
        "plano_metas": {
            "meta_desejada_perc": nota_corte,
            "meta_desejada_pontos": pontos_meta_desejada,
            "nota_atual_estimada_perc": nota_estimada_perc,
            "nota_atual_estimada_pontos": nota_estimada_pontos,
            "pontos_faltantes": gap_nota_pontos,
            "pp_faltantes": round(max(0.0, nota_corte - nota_estimada_perc), 1),
            "alavancas_disciplinas": alavancas_meta
        },
        "evolucao_estimativa": evolucao_estimativa,
        "gestao_temporal": gestao_temporal,
        "analise_ia": analise_ia_salva
    }


def _calcular_evolucao_temporal_estimativa(
    todas_sessoes: List[SessaoEstudo],
    disciplinas_validas: List[ Any ],
    total_pontos_prova: float,
    total_topicos_edital: int,
    prior_acerto: float,
    nota_corte: float,
    nota_estimada_atual: float,
    incerteza_atual: float,
    fator_penalidade_efetivo: float = 0.0
) -> List[Dict[str, Any]]:
    if not todas_sessoes:
        hoje_str = date.today().strftime("%d/%m")
        return [{
            "periodo": f"Atual ({hoje_str})",
            "data_iso": date.today().isoformat(),
            "nota_estimada_perc": nota_estimada_atual,
            "ic_min_perc": round(max(0.0, nota_estimada_atual - incerteza_atual), 1),
            "ic_max_perc": round(min(100.0, nota_estimada_atual + incerteza_atual), 1),
            "incerteza_perc": incerteza_atual,
            "meta_corte_perc": nota_corte,
            "questoes_acumuladas": 0
        }]

    # Agrupar sessões por segunda-feira da semana
    semanas_map = defaultdict(list)
    for s in todas_sessoes:
        if not s.data:
            continue
        seg = s.data - timedelta(days=s.data.weekday())
        semanas_map[seg].append(s)

    semanas_ordenadas = sorted(semanas_map.keys())
    if len(semanas_ordenadas) > 12:
        semanas_ordenadas = semanas_ordenadas[-12:]

    ac_por_disc = defaultdict(int)
    q_por_disc = defaultdict(int)
    topicos_vistos_set = set()
    q_acum = 0
    ac_acum = 0

    # Se recortamos as últimas 12 semanas, acumula as anteriores primeiro
    todas_semanas_full = sorted(semanas_map.keys())
    for seg_ant in todas_semanas_full:
        if seg_ant in semanas_ordenadas:
            break
        for s in semanas_map[seg_ant]:
            ac_por_disc[s.disciplina_id] += (s.qtd_acertos or 0)
            q_por_disc[s.disciplina_id] += (s.qtd_questoes_total or 0)
            q_acum += (s.qtd_questoes_total or 0)
            ac_acum += (s.qtd_acertos or 0)
            if s.topico_id:
                topicos_vistos_set.add(s.topico_id)

    serie = []
    for idx, seg in enumerate(semanas_ordenadas):
        for s in semanas_map[seg]:
            ac_por_disc[s.disciplina_id] += (s.qtd_acertos or 0)
            q_por_disc[s.disciplina_id] += (s.qtd_questoes_total or 0)
            q_acum += (s.qtd_questoes_total or 0)
            ac_acum += (s.qtd_acertos or 0)
            if s.topico_id:
                topicos_vistos_set.add(s.topico_id)

        cobertura_acum = min(1.0, len(topicos_vistos_set) / float(max(1, total_topicos_edital)))
        fator_cob = 0.90 + (0.10 * cobertura_acum)

        pts_semana = 0.0
        for d, q_prova, peso, pts_max in disciplinas_validas:
            qd = q_por_disc[d.id]
            ad = ac_por_disc[d.id]
            if qd > 0:
                tx_d = (ad / qd) * 100.0
                w_am = qd / (qd + 15.0)
                tx_est_bruta = ((w_am * tx_d) + ((1.0 - w_am) * prior_acerto)) * fator_cob
            else:
                tx_est_bruta = (prior_acerto * 0.90) * fator_cob
            tx_est_bruta = min(98.0, max(15.0, tx_est_bruta))
            if fator_penalidade_efetivo > 0:
                p_ac = tx_est_bruta / 100.0
                tx_est = max(5.0, (p_ac - ((1.0 - p_ac) * fator_penalidade_efetivo)) * 100.0)
            else:
                tx_est = tx_est_bruta
            pts_semana += pts_max * (tx_est / 100.0)

        nota_sem_perc = round((pts_semana / total_pontos_prova) * 100.0, 1)
        # No último ponto, alinha exatamente com a nota estimada atual (que considera também tópicos marcados concluídos)
        if idx == len(semanas_ordenadas) - 1:
            nota_sem_perc = nota_estimada_atual
            inc_sem = incerteza_atual
        else:
            inc_sem = round(min(22.0, max(incerteza_atual, 14.0 - (min(1.0, q_acum / 1200.0) * 6.5) - (cobertura_acum * 4.0))), 1)

        serie.append({
            "periodo": f"Sem {seg.strftime('%d/%m')}",
            "data_iso": seg.isoformat(),
            "nota_estimada_perc": nota_sem_perc,
            "ic_min_perc": round(max(0.0, nota_sem_perc - inc_sem), 1),
            "ic_max_perc": round(min(100.0, nota_sem_perc + inc_sem), 1),
            "incerteza_perc": inc_sem,
            "aproveitamento_bruto_perc": round((ac_acum / q_acum) * 100.0, 1) if q_acum > 0 else 0.0,
            "meta_corte_perc": nota_corte,
            "questoes_acumuladas": q_acum
        })

    return serie


def _calcular_gestao_temporal_projeto(
    hoje: date,
    data_prova_dt: date,
    dias_restantes: int,
    tipo_data_prova: str,
    total_topicos_edital: int,
    total_topicos_estudados: int,
    total_topicos_em_andamento: int,
    total_topicos_nao_estudados: int,
    total_p1_pendentes: int,
    total_mc_pendentes: int,
    meta_conclusao_edital: float,
    dias_disponiveis_semana: int,
    horas_estudo_dia: float,
    horas_por_topico: float,
    dias_antecedencia_revisao: int,
    horas_simulado_semana: float,
    disciplinas_detalhe: List[Dict[str, Any]]
) -> Dict[str, Any]:
    total_top = max(1, total_topicos_edital)
    cobertura_atual_perc = round((total_topicos_estudados / total_top) * 100.0, 1)

    # Meta de conclusão do edital (em tópicos e %)
    topicos_alvo_meta = int(math.ceil(total_top * (meta_conclusao_edital / 100.0)))
    topicos_restantes_meta = max(0, topicos_alvo_meta - total_topicos_estudados)
    perc_restante_meta = round(max(0.0, meta_conclusao_edital - cobertura_atual_perc), 1)

    # Horizontes de tempo
    dias_ate_prova_util = max(1, dias_restantes)
    semanas_ate_prova = round(max(0.5, dias_ate_prova_util / 7.0), 1)

    # Quando iniciar a Fase de Revisão Final
    dias_revisao_efetivos = min(max(7, dias_antecedencia_revisao), max(7, int(dias_ate_prova_util * 0.45))) if dias_restantes > 14 else max(3, dias_restantes // 2)
    data_inicio_revisao_dt = data_prova_dt - timedelta(days=dias_revisao_efetivos)
    dias_ate_inicio_revisao = max(0, (data_inicio_revisao_dt - hoje).days)
    semanas_avanco_teorico = round(max(0.5, dias_ate_inicio_revisao / 7.0), 1) if dias_ate_inicio_revisao > 0 else 0.5

    ja_na_fase_revisao = dias_ate_inicio_revisao <= 0

    # Quanto do edital precisa ser concluído por semana:
    # 1) Para fechar a meta antes da Fase de Revisão
    if dias_ate_inicio_revisao > 0:
        topicos_semana_ate_revisao = round(topicos_restantes_meta / semanas_avanco_teorico, 1)
        perc_edital_semana_ate_revisao = round(perc_restante_meta / semanas_avanco_teorico, 1)
    else:
        topicos_semana_ate_revisao = round(topicos_restantes_meta / semanas_ate_prova, 1)
        perc_edital_semana_ate_revisao = round(perc_restante_meta / semanas_ate_prova, 1)

    # 2) Diluído até a véspera da prova
    topicos_semana_ate_prova = round(topicos_restantes_meta / semanas_ate_prova, 1)
    perc_edital_semana_ate_prova = round(perc_restante_meta / semanas_ate_prova, 1)

    # Ritmo por dia disponível da semana
    topicos_por_dia_disponivel = round(topicos_semana_ate_revisao / max(1, dias_disponiveis_semana), 2)

    # Orçamento de Horas Semanais do Projeto
    carga_semanal_total = round(dias_disponiveis_semana * horas_estudo_dia, 1)
    horas_simulado_sem = round(min(carga_semanal_total * 0.4, max(0.0, horas_simulado_semana)), 1)
    horas_revisao_anki_sem = round(carga_semanal_total * (0.45 if ja_na_fase_revisao else 0.22), 1)
    horas_avanco_disponiveis_sem = round(max(1.0, carga_semanal_total - horas_simulado_sem - horas_revisao_anki_sem), 1)

    # Capacidade real de fechar tópicos por semana com as horas disponíveis para avanço
    capacidade_topicos_semana = round(horas_avanco_disponiveis_sem / max(0.5, horas_por_topico), 1)
    horas_semanais_necessarias_meta = round(topicos_semana_ate_revisao * horas_por_topico, 1)
    horas_totais_para_fechar_meta = round(topicos_restantes_meta * horas_por_topico, 1)
    horas_totais_nucleo_p1 = round(total_p1_pendentes * horas_por_topico, 1)

    # Quantas semanas levará no ritmo disponível atual para bater a meta do edital
    semanas_necessarias_no_ritmo_atual = round(topicos_restantes_meta / max(0.5, capacidade_topicos_semana), 1) if topicos_restantes_meta > 0 else 0.0
    dias_necessarios_no_ritmo_atual = int(math.ceil(semanas_necessarias_no_ritmo_atual * 7))
    data_conclusao_projetada_dt = hoje + timedelta(days=dias_necessarios_no_ritmo_atual)

    # Simulados recomendados até a prova
    if dias_restantes <= 0:
        qtd_simulados_ate_prova = 0
    elif dias_restantes <= 30:
        qtd_simulados_ate_prova = max(1, int(round(semanas_ate_prova)))
    else:
        semanas_finais = round(dias_revisao_efetivos / 7.0, 1)
        semanas_iniciais = max(0.0, semanas_ate_prova - semanas_finais)
        qtd_simulados_ate_prova = int(round((semanas_iniciais / 2.0) + semanas_finais))

    horas_totais_simulados_ate_prova = round(semanas_ate_prova * horas_simulado_sem, 1)
    perc_tempo_simulados = round((horas_simulado_sem / max(1.0, carga_semanal_total)) * 100.0, 1)

    # Diagnóstico de Viabilidade do Projeto
    if topicos_restantes_meta == 0:
        status_projeto = "Concluído"
        cor_projeto = "emerald"
        resumo_viabilidade = "Meta de cobertura do edital já atingida! Foco 100% em revisão espaçada, baterias de questões e simulados."
    elif semanas_necessarias_no_ritmo_atual <= semanas_avanco_teorico:
        status_projeto = "No Prazo (Verde)"
        cor_projeto = "emerald"
        resumo_viabilidade = (
            f"Seu ritmo atual ({capacidade_topicos_semana} tópicos/sem em {horas_avanco_disponiveis_sem}h líquidas de avanço) "
            f"permite concluir a meta de {meta_conclusao_edital}% do edital até {data_conclusao_projetada_dt.strftime('%d/%m/%Y')}, "
            f"antes do início da Fase de Revisão ({data_inicio_revisao_dt.strftime('%d/%m/%Y')})."
        )
    elif semanas_necessarias_no_ritmo_atual <= semanas_ate_prova:
        status_projeto = "Atenção ao Cronograma (Âmbar)"
        cor_projeto = "amber"
        resumo_viabilidade = (
            f"No ritmo atual ({capacidade_topicos_semana} tópicos/sem), a meta de {meta_conclusao_edital}% será concluída em "
            f"{data_conclusao_projetada_dt.strftime('%d/%m/%Y')} (invadindo parte da Fase de Revisão). "
            f"Para fechar antes da revisão, avance {topicos_semana_ate_revisao} tópicos/sem (~{horas_semanais_necessarias_meta}h/sem de teoria)."
        )
    else:
        status_projeto = "Escopo Crítico — Ativar Pareto 80/20 (Vermelho)"
        cor_projeto = "rose"
        resumo_viabilidade = (
            f"Fechar {topicos_restantes_meta} tópicos ({meta_conclusao_edital}% do edital) exige {horas_totais_para_fechar_meta}h de avanço, "
            f"acima da janela disponível até a prova ({semanas_necessarias_no_ritmo_atual} semanas necessárias vs {semanas_ate_prova} semanas restantes). "
            f"Recomendação de Gestão de Projeto: priorizar os {total_p1_pendentes} tópicos P1 e {total_mc_pendentes} Mais Cobrados pendentes ({horas_totais_nucleo_p1}h)!"
        )

    # Fases do Projeto (Roadmap Temporal)
    data_meio_avanco = hoje + timedelta(days=max(1, dias_ate_inicio_revisao // 2))
    data_sprint_final = data_prova_dt - timedelta(days=min(10, max(3, dias_restantes // 4)))

    fases_projeto = [
        {
            "ordem": 1,
            "nome": "Fase 1 — Núcleo Pareto & Matérias de Maior Peso",
            "periodo": f"{hoje.strftime('%d/%m')} a {data_meio_avanco.strftime('%d/%m/%Y')}",
            "foco": f"Vencer os {total_p1_pendentes} tópicos P1 e {total_mc_pendentes} Mais Cobrados pendentes nas disciplinas de maior peso.",
            "alocacao": "65% Avanço Direcionado • 20% Revisão/Questões • 15% Simulados Quinzenais",
            "ativa": not ja_na_fase_revisao and dias_ate_inicio_revisao > 14
        },
        {
            "ordem": 2,
            "nome": f"Fase 2 — Fechamento da Meta do Edital ({meta_conclusao_edital:.0f}%)",
            "periodo": f"{data_meio_avanco.strftime('%d/%m')} a {data_inicio_revisao_dt.strftime('%d/%m/%Y')}",
            "foco": f"Ritmo de {topicos_semana_ate_revisao} tópicos/semana ({perc_edital_semana_ate_revisao}% do edital/semana) para atingir {topicos_alvo_meta} tópicos vistos.",
            "alocacao": "50% Fechamento de Tópicos • 35% Baterias da Banca • 15% Simulados",
            "ativa": not ja_na_fase_revisao and dias_ate_inicio_revisao <= 14
        },
        {
            "ordem": 3,
            "nome": "Fase 3 — Revisão Intensiva & Estancamento de Gargalos",
            "periodo": f"Início em {data_inicio_revisao_dt.strftime('%d/%m/%Y')} ({dias_revisao_efetivos} dias pré-prova)",
            "foco": "Congelar teoria inédita residual; ataque massivo aos gargalos que mais comprometem a nota e revisão ativa (Anki + Lei Seca).",
            "alocacao": "15% Ajustes Pontuais • 60% Revisão & Caderno de Erros • 25% Simulados Semanais",
            "ativa": ja_na_fase_revisao and dias_restantes > 10
        },
        {
            "ordem": 4,
            "nome": "Fase 4 — Sprint Final & Simulação de Prova",
            "periodo": f"{data_sprint_final.strftime('%d/%m')} até {data_prova_dt.strftime('%d/%m/%Y')}",
            "foco": "Treino de estratégia de prova, controle de tempo, blindagem contra critérios eliminatórios e revisão de véspera.",
            "alocacao": "75% Revisão Rápida & Decorebas • 25% Simulado Final & Estratégia de Banca",
            "ativa": dias_restantes <= 10 and dias_restantes >= 0
        }
    ]

    # Ritmo semanal requerido por disciplina proporcional ao peso e tópicos restantes
    progresso_disciplinas_projeto = []
    for d_item in disciplinas_detalhe:
        nao_est = d_item["topicos_nao_estudados"]
        meta_top_disc = int(math.ceil(d_item["topicos_total"] * (meta_conclusao_edital / 100.0)))
        faltam_meta_disc = max(0, meta_top_disc - d_item["topicos_estudados"])
        ritmo_sem_disc = round(faltam_meta_disc / semanas_avanco_teorico, 1) if faltam_meta_disc > 0 else 0.0

        progresso_disciplinas_projeto.append({
            "id": d_item["id"],
            "nome": d_item["nome"],
            "grupo_conhecimento": d_item["grupo_conhecimento"],
            "peso_prova": d_item["peso_prova"],
            "qtd_questoes_prova": d_item["qtd_questoes_prova"],
            "representatividade_perc": d_item["representatividade_perc"],
            "topicos_total": d_item["topicos_total"],
            "topicos_concluidos": d_item["topicos_concluidos"],
            "topicos_em_andamento": d_item["topicos_em_andamento"],
            "topicos_estudados": d_item["topicos_estudados"],
            "topicos_nao_estudados": nao_est,
            "topicos_p1_pendentes": d_item["topicos_p1_pendentes"],
            "cobertura_perc": d_item["cobertura_perc"],
            "faltam_para_meta": faltam_meta_disc,
            "ritmo_topicos_semana": ritmo_sem_disc,
            "horas_restantes_meta": round(faltam_meta_disc * horas_por_topico, 1),
            "topicos_lista": d_item["topicos_lista"]
        })

    return {
        "tipo_data_prova": tipo_data_prova,
        "data_prova_fmt": data_prova_dt.strftime("%d/%m/%Y"),
        "dias_restantes": dias_restantes,
        "semanas_restantes": semanas_ate_prova,
        "dias_disponiveis_semana": dias_disponiveis_semana,
        "horas_estudo_dia": horas_estudo_dia,
        "carga_semanal_total": carga_semanal_total,
        "horas_por_topico": horas_por_topico,
        "total_topicos_edital": total_topicos_edital,
        "topicos_estudados": total_topicos_estudados,
        "topicos_em_andamento": total_topicos_em_andamento,
        "conteudo_nao_estudado": total_topicos_nao_estudados,
        "cobertura_atual_perc": cobertura_atual_perc,
        "perc_nao_estudado": round(max(0.0, 100.0 - cobertura_atual_perc), 1),
        "total_p1_pendentes": total_p1_pendentes,
        "total_mais_cobrados_pendentes": total_mc_pendentes,
        "meta_conclusao_edital_perc": meta_conclusao_edital,
        "topicos_alvo_meta": topicos_alvo_meta,
        "topicos_restantes_meta": topicos_restantes_meta,
        "perc_restante_meta": perc_restante_meta,
        "ritmo_semanal": {
            "topicos_por_semana_ate_revisao": topicos_semana_ate_revisao,
            "perc_edital_por_semana_ate_revisao": perc_edital_semana_ate_revisao,
            "topicos_por_semana_ate_prova": topicos_semana_ate_prova,
            "perc_edital_por_semana_ate_prova": perc_edital_semana_ate_prova,
            "topicos_por_dia_disponivel": topicos_por_dia_disponivel,
            "capacidade_atual_topicos_semana": capacidade_topicos_semana,
            "horas_semanais_necessarias_teoria": horas_semanais_necessarias_meta,
            "horas_totais_para_fechar_meta": horas_totais_para_fechar_meta,
            "horas_totais_nucleo_p1": horas_totais_nucleo_p1
        },
        "fase_revisao": {
            "dias_antecedencia_revisao": dias_revisao_efetivos,
            "data_inicio_revisao_iso": data_inicio_revisao_dt.isoformat(),
            "data_inicio_revisao_fmt": data_inicio_revisao_dt.strftime("%d/%m/%Y"),
            "dias_ate_inicio_revisao": dias_ate_inicio_revisao,
            "semanas_ate_inicio_revisao": semanas_avanco_teorico,
            "ja_na_fase_revisao": ja_na_fase_revisao,
            "status_revisao": "Fase de Revisão Intensiva Ativa" if ja_na_fase_revisao else f"Iniciar em {data_inicio_revisao_dt.strftime('%d/%m/%Y')} (faltam {dias_ate_inicio_revisao} dias)",
            "horas_revisao_semanal_recomendada": horas_revisao_anki_sem
        },
        "reserva_simulados": {
            "horas_simulado_semana": horas_simulado_sem,
            "perc_carga_semanal_simulados": perc_tempo_simulados,
            "qtd_simulados_recomendados_ate_prova": qtd_simulados_ate_prova,
            "horas_totais_simulados_ate_prova": horas_totais_simulados_ate_prova,
            "recomendacao": (
                f"Reservar {horas_simulado_sem}h/semana ({perc_tempo_simulados}% da sua carga semanal) para realizar "
                f"~{qtd_simulados_ate_prova} simulados cronometrados até a prova (incluindo 1h30 de diagnóstico de erros por simulado)."
            )
        },
        "orcamento_semanal": {
            "horas_avanco_teorico": horas_avanco_disponiveis_sem,
            "horas_revisao_fixacao": horas_revisao_anki_sem,
            "horas_simulados": horas_simulado_sem,
            "total_horas_semana": carga_semanal_total
        },
        "viabilidade_projeto": {
            "status": status_projeto,
            "cor": cor_projeto,
            "semanas_necessarias_ritmo_atual": semanas_necessarias_no_ritmo_atual,
            "data_conclusao_projetada_fmt": data_conclusao_projetada_dt.strftime("%d/%m/%Y"),
            "resumo": resumo_viabilidade
        },
        "fases_projeto": fases_projeto,
        "progresso_disciplinas": progresso_disciplinas_projeto
    }


async def gerar_analise_ia_mapa_aprovacao(db: Session, edital_id: Optional[int] = None) -> Dict[str, Any]:
    config = _garantir_config(db)
    mapa = calcular_mapa_aprovacao(db, edital_id)
    if "erro" in mapa:
        return mapa

    chave = obter_chave_gemini(config)
    p = mapa["parametros_prova"]
    est = mapa["estimativa_nota"]
    gt = mapa["gestao_temporal"]
    gargalos = mapa["gargalos_pontuacao"][:4]
    alavancas = mapa["plano_metas"]["alavancas_disciplinas"][:4]

    resumo_gargalos = [
        {
            "disciplina": g["nome"],
            "peso": g["peso_prova"],
            "questoes_prova": g["qtd_questoes_prova"],
            "representatividade_nota_final": f"{g['representatividade_perc']}%",
            "taxa_estimada": f"{g['taxa_estimada_perc']}% ± {g['incerteza_perc']}%",
            "pontos_perdidos": g["pontos_perdidos_estimados"],
            "topicos_nao_estudados": g["topicos_nao_estudados"]
        }
        for g in gargalos
    ]

    if chave:
        prompt = f"""Você é o Estrategista-Chefe e Gestor de Projetos de Aprovação do sistema Orbis.
Analise os dados reais do MAPA DA APROVAÇÃO do aluno e retorne um parecer técnico, estatístico e tático de altíssima precisão.

IMPORTANTE:
- A estimativa NUNCA deve prometer aprovação garantida; sempre mencione e interprete a margem de incerteza (±{est['margem_incerteza_perc']} p.p.) e como reduzi-la.
- Considere especificamente a prova **{p['concurso']}**, a carreira/área **{p['area_concurso']}**, o cargo **{p['cargo']} ({p['especialidade']})**, a banca **{p['banca']} ({p['estilo_banca']})** e o sistema de pontuação **{est['modo_pontuacao']}**.
- Estime, com base no histórico típico de concursos dessa carreira, cargo e banca, qual costuma ser a **nota líquida (ou bruta, se sem penalidade) dos aprovados** dentro das vagas e qual o **% de acerto bruto em questões** necessário para atingir essa nota (considerando que no Cebraspe 1 errada anula 1 certa, a nota líquida é significativamente menor que o % de acerto bruto).

DADOS DO MAPA DA APROVAÇÃO:
- Concurso: {p['concurso']} | Carreira/Área: {p['area_concurso']} | Cargo: {p['cargo']} ({p['especialidade']})
- Banca: {p['banca']} ({p['estilo_banca']}) | Regra de Pontuação: {est['modo_pontuacao']}
- Data da Prova ({p['tipo_data_prova']}): {p['data_prova_fmt']} ({p['dias_restantes']} dias restantes / {p['semanas_restantes']} semanas)
- Total da Prova: {p['total_questoes_prova']} questões ({p['total_pontos_prova']} pontos ponderados)
- Nota Estimada Atual ({'Líquida' if est['eh_nota_liquida'] else 'Bruta'}): {est['nota_estimada_perc']}% ({est['nota_estimada_pontos']} pts) com Margem de Incerteza de ±{est['margem_incerteza_perc']}% (IC: {est['intervalo_confianca']['min_perc']}% a {est['intervalo_confianca']['max_perc']}%)
- Aproveitamento Bruto Atual (% acerto nas questões): {est['aproveitamento_observado_perc']}% (Bruta estimada ponderada: {est['nota_bruta_estimada_perc']}%)
- Meta Desejada Atual (Corte): {p['nota_corte']}% ({p['pontos_meta_desejada']} pts) — exige ~{est['taxa_acerto_bruta_meta_perc']}% de acerto bruto
- Critérios Eliminatórios: Mínimo Geral {p['nota_minima_geral']}%, Básicos {p['nota_minima_basicos']}%, Específicos {p['nota_minima_especificos']}%
- Disciplinas que mais comprometem a pontuação hoje: {json.dumps(resumo_gargalos, ensure_ascii=False)}
- Gestão Temporal do Projeto:
  * Cobertura atual: {gt['cobertura_atual_perc']}% ({gt['topicos_estudados']}/{gt['total_topicos_edital']} tópicos; {gt['conteudo_nao_estudado']} tópicos não estudados)
  * Meta de conclusão do edital: {gt['meta_conclusao_edital_perc']}% (faltam {gt['topicos_restantes_meta']} tópicos)
  * Disponibilidade: {gt['dias_disponiveis_semana']} dias/semana ({gt['carga_semanal_total']}h/semana)
  * Ritmo necessário até a Fase de Revisão ({gt['fase_revisao']['data_inicio_revisao_fmt']}): {gt['ritmo_semanal']['topicos_por_semana_ate_revisao']} tópicos/semana ({gt['ritmo_semanal']['perc_edital_por_semana_ate_revisao']}% do edital/semana)
  * Reserva para Simulados: {gt['reserva_simulados']['horas_simulado_semana']}h/semana (~{gt['reserva_simulados']['qtd_simulados_recomendados_ate_prova']} simulados até a prova)

RETORNE ESTRITAMENTE UM JSON VÁLIDO NO FORMATO:
{{
  "benchmark_aprovados": {{
    "nota_aprovados_sugerida_perc": 65.0,
    "faixa_aprovados_perc": "60% a 68% líquidos (Cebraspe)",
    "taxa_acerto_bruta_necessaria_perc": 82.5,
    "justificativa_banca_cargo": "Explicação objetiva de por que aprovados no cargo {p['cargo']} ({p['area_concurso']}) da banca {p['banca']} costumam pontuar nessa faixa, diferenciando nota líquida de % de acerto bruto."
  }},
  "diagnostico_preditivo": "🎯 Análise estatística da nota estimada ({est['nota_estimada_perc']}% ± {est['margem_incerteza_perc']}%), comparando nota líquida vs % de acerto bruto, intervalo de confiança [{est['intervalo_confianca']['min_perc']}% a {est['intervalo_confianca']['max_perc']}%], critérios eliminatórios e banca {p['banca']} sem prometer aprovação.",
  "analise_gargalos_pesos": "🚨 Diagnóstico das disciplinas que mais comprometem a pontuação final hoje pelo cruzamento de Peso × Questões × Taxa, indicando quantos pontos podem ser destravados.",
  "parecer_gestao_temporal": "📅 Avaliação de Gerenciamento de Projeto sobre os {p['dias_restantes']} dias restantes, ritmo de {gt['ritmo_semanal']['topicos_por_semana_ate_revisao']} tópicos/semana ({gt['ritmo_semanal']['perc_edital_por_semana_ate_revisao']}%/sem), início da Fase de Revisão em {gt['fase_revisao']['data_inicio_revisao_fmt']} e reserva de {gt['reserva_simulados']['horas_simulado_semana']}h/sem para simulados.",
  "metas_semanais_acao": [
    "Meta tática 1 específica com números e disciplinas",
    "Meta tática 2 sobre fechamento de tópicos não estudados",
    "Meta tática 3 sobre redução da margem de incerteza e controle de erros na banca {p['banca']}",
    "Meta tática 4 sobre revisão e simulados"
  ]
}}"""

        modelos = MODELOS_GEMINI_ATIVOS
        async with httpx.AsyncClient(timeout=20.0) as client:
            for mod in modelos:
                try:
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{mod}:generateContent?key={chave}"
                    payload = {
                        "contents": [{"parts": [{"text": prompt}]}],
                        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.4}
                    }
                    resp = await client.post(url, json=payload)
                    if resp.status_code == 200:
                        partes = resp.json().get("candidates", [{}])[0].get("content", {}).get("parts", [])
                        txt = "".join(pt.get("text", "") for pt in partes if "text" in pt).strip()
                        parsed = extrair_json_resiliente(txt)
                        parsed["modelo_origem"] = f"Google Gemini ({mod})"
                        parsed["timestamp"] = datetime.now().strftime("%d/%m/%Y %H:%M")
                        config.ultimo_mapa_ia = json.dumps(parsed, ensure_ascii=False)
                        config.data_mapa_ia = datetime.now()
                        db.commit()
                        print(f"[MAPA APROVACAO IA] Sucesso via Google Gemini ({mod})")
                        return parsed
                    elif resp.status_code in (401, 403) or "API_KEY_INVALID" in resp.text:
                        print(f"[MAPA APROVACAO IA] Chave inválida ({resp.status_code}): {resp.text[:140]}")
                        break
                    else:
                        print(f"[MAPA APROVACAO IA] Modelo {mod} retornou HTTP {resp.status_code}: {resp.text[:140]}")
                except Exception as e:
                    print(f"[MAPA APROVACAO IA] Aviso com {mod}: {e}")
                    continue

    # Fallback Heurístico Especialista
    nomes_gargalos = ", ".join(
        f"**{g['nome']}** ({g['representatividade_perc']}% da prova, perdendo {g['pontos_perdidos_estimados']} pts)"
        for g in gargalos[:3]
    ) if gargalos else "disciplinas de maior peso"

    nomes_alavancas = ", ".join(
        f"**{a['nome']}** (+{a['ganho_pontos_prova']} pts ao subir para {a['meta_recomendada_perc']}%)"
        for a in alavancas[:3]
    ) if alavancas else "matérias específicas"

    eh_liq = est["eh_nota_liquida"]
    f_pen = est["fator_penalidade_efetivo"]
    bench_padrao = _calcular_benchmark_ia_padrao(
        area_concurso=p.get("area_concurso") or "",
        cargo=p.get("cargo") or "",
        banca=p["banca"],
        estilo_banca=p["estilo_banca"],
        eh_nota_liquida=eh_liq,
        fator_penalidade=f_pen,
    )

    resultado_heuristico = {
        "benchmark_aprovados": bench_padrao,
        "diagnostico_preditivo": (
            f"🎯 **Leitura Probabilística ({est['modo_pontuacao']}):** Sua nota {'líquida' if eh_liq else 'bruta'} estimada encontra-se em **{est['nota_estimada_perc']}%** "
            f"(**{est['nota_estimada_pontos']} de {p['total_pontos_prova']} pts**), com margem de incerteza de **±{est['margem_incerteza_perc']} p.p.** "
            f"(faixa provável entre **{est['intervalo_confianca']['min_perc']}% e {est['intervalo_confianca']['max_perc']}%**). "
            f"Seu aproveitamento bruto atual nas questões é **{est['aproveitamento_observado_perc']}%**. "
            f"Esta estimativa considera os pesos reais do edital e a cobertura atual de **{est['cobertura_edital_perc']}%**, não representando promessa de aprovação."
        ),
        "analise_gargalos_pesos": (
            f"🚨 **Vazamento Ponderado de Pontos:** As disciplinas que mais comprometem sua nota final hoje são {nomes_gargalos}. "
            f"Para atingir a meta desejada de **{p['nota_corte']}%** (**{p['pontos_meta_desejada']} pts**), as maiores alavancas de pontuação estão em {nomes_alavancas}."
        ),
        "parecer_gestao_temporal": (
            f"📅 **Engenharia Temporal do Projeto ({p['dias_restantes']} dias / {p['tipo_data_prova']}):** Restam **{gt['conteudo_nao_estudado']} tópicos não estudados** no edital. "
            f"Para cumprir a meta de **{gt['meta_conclusao_edital_perc']}% de conclusão** antes do marco da **Fase de Revisão ({gt['fase_revisao']['data_inicio_revisao_fmt']})**, "
            f"o projeto exige vencer **{gt['ritmo_semanal']['topicos_por_semana_ate_revisao']} tópicos/semana** (**{gt['ritmo_semanal']['perc_edital_por_semana_ate_revisao']}% do edital/semana**) "
            f"nos seus **{gt['dias_disponiveis_semana']} dias disponíveis por semana**, reservando **{gt['reserva_simulados']['horas_simulado_semana']}h semanais** para simulados e diagnóstico."
        ),
        "metas_semanais_acao": [
            f"Concluir **{gt['ritmo_semanal']['topicos_por_semana_ate_revisao']} tópicos nesta semana** (~{gt['ritmo_semanal']['topicos_por_dia_disponivel']} tópicos por dia disponível), priorizando os **{gt['total_p1_pendentes']} tópicos P1 pendentes**.",
            f"Estancar a perda de pontos em **{gargalos[0]['nome'] if gargalos else 'Específicas'}** (representa **{gargalos[0]['representatividade_perc'] if gargalos else 10}%** da nota final) com bateria comentada da banca {p['banca']}.",
            f"Reduzir a margem de incerteza (±{est['margem_incerteza_perc']}%) resolvendo ao menos 30 questões nas disciplinas com menor amostragem para blindar os critérios eliminatórios.",
            f"Cumprir o orçamento semanal do projeto: **{gt['orcamento_semanal']['horas_avanco_teorico']}h** de avanço teórico, **{gt['orcamento_semanal']['horas_revisao_fixacao']}h** de revisão ativa e **{gt['orcamento_semanal']['horas_simulados']}h** para simulado/diagnóstico."
        ],
        "modelo_origem": "Motor Analítico Preditivo Orbis",
        "timestamp": datetime.now().strftime("%d/%m/%Y %H:%M")
    }
    config.ultimo_mapa_ia = json.dumps(resultado_heuristico, ensure_ascii=False)
    config.data_mapa_ia = datetime.now()
    db.commit()
    return resultado_heuristico
