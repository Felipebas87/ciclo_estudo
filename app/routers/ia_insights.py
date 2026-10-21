import os
import json
import random
from datetime import datetime, date, timezone
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, Query, HTTPException, Body
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.models.configuracao_prova import ConfiguracaoPainelProva
from app.models.sessao import SessaoEstudo
from app.models.disciplina import Disciplina
from app.models.ciclo import CicloEstudos, BlocoCiclo
from app.models.edital import Edital
from app.models.topico import Topico

router = APIRouter(prefix="/api/ia", tags=["Insights de IA"])

def obter_chave_gemini(config: ConfiguracaoPainelProva) -> Optional[str]:
    # Prioridade 1: Chave salva no banco de dados pelo usuário
    if config and config.gemini_api_key and config.gemini_api_key.strip():
        return config.gemini_api_key.strip()
    # Prioridade 2: Variável de ambiente no servidor (.env ou os.environ)
    env_key = os.getenv("GEMINI_API_KEY")
    if env_key and env_key.strip():
        return env_key.strip()
    return None

def calcular_dados_estudo(db: Session) -> Dict[str, Any]:
    config = db.query(ConfiguracaoPainelProva).first()
    if not config:
        config = ConfiguracaoPainelProva(id=1)
        db.add(config)
        db.commit()
        db.refresh(config)

    hoje = date.today()
    dias_restantes = 40
    data_prova_str = config.data_prova or "2026-11-29"
    try:
        data_p = datetime.strptime(data_prova_str, "%Y-%m-%d").date()
        dias_restantes = (data_p - hoje).days
    except Exception:
        dias_restantes = 40

    if dias_restantes > 90:
        zona_tag = "Cadência & Constância"
        zona_fase = "Fase Inicial / Construção de Base"
    elif dias_restantes >= 31:
        zona_tag = "Consolidação & Aceleração"
        zona_fase = "Fase Intermediária / Intensificação"
    elif dias_restantes >= 0:
        zona_tag = "Ajuste Fino & Reta Final"
        zona_fase = "Reta Finalíssima / Revisão e Simulados"
    else:
        zona_tag = "Pós-Prova"
        zona_fase = "Ciclo Concluído"

    sessoes = db.query(SessaoEstudo).order_by(SessaoEstudo.data.asc()).all()
    total_sessoes = len(sessoes)
    total_minutos = sum(s.tempo_estudado_minutos or 0 for s in sessoes)
    total_horas = round(total_minutos / 60.0, 1)

    total_questoes = sum(s.qtd_questoes_total or 0 for s in sessoes)
    total_acertos = sum(s.qtd_acertos or 0 for s in sessoes)
    total_erros = sum(s.qtd_erros or 0 for s in sessoes)
    taxa_global = round((total_acertos / total_questoes * 100), 1) if total_questoes > 0 else 0.0

    # 1. Edital & Tópicos (Premissa: 1 hora de estudo = 1 tópico do edital)
    ciclo = db.query(CicloEstudos).filter(CicloEstudos.ativo == True).first()
    ciclo_nome = ciclo.nome if ciclo else "Ciclo de Estudos"
    voltas_ciclo = ciclo.voltas_completas if ciclo else 0
    carga_horaria_semanal = ciclo.carga_horaria_semanal if ciclo and ciclo.carga_horaria_semanal else 20.0

    edital_id = ciclo.edital_id if ciclo and ciclo.edital_id else None
    if not edital_id:
        edital_first = db.query(Edital).first()
        edital_id = edital_first.id if edital_first else None

    total_topicos_edital = 0
    if edital_id:
        total_topicos_edital = db.query(Topico).join(Disciplina).filter(Disciplina.edital_id == edital_id).count()
    if total_topicos_edital == 0:
        total_topicos_edital = db.query(Topico).count() or 1

    topicos_cobertos_estimados = min(total_horas, float(total_topicos_edital))
    perc_edital_coberto = round((topicos_cobertos_estimados / total_topicos_edital * 100), 1) if total_topicos_edital > 0 else 0.0
    topicos_restantes = max(0, total_topicos_edital - int(total_horas))
    horas_para_zerar_edital = float(topicos_restantes)  # 1h por tópico

    # Projeção de fechamento do edital
    horas_dia_necessarias_40d = round(horas_para_zerar_edital / max(1, dias_restantes), 1) if dias_restantes > 0 else 0.0
    ritmo_diario_declarado = round(carga_horaria_semanal / 7.0, 2)
    dias_para_zerar_na_meta_semanal = int(horas_para_zerar_edital / ritmo_diario_declarado) if ritmo_diario_declarado > 0 else 0

    topicos_cobertos_proj_ate_prova = int(min(total_topicos_edital, topicos_cobertos_estimados + (ritmo_diario_declarado * max(0, dias_restantes))))
    perc_edital_proj_ate_prova = round((topicos_cobertos_proj_ate_prova / total_topicos_edital * 100), 1) if total_topicos_edital > 0 else 0.0

    # 2. Competitividade, Cadência e Projeção de Questões
    cadencia_questoes_hora = round(total_questoes / total_horas, 1) if total_horas > 0 else 0.0
    horas_estudo_proj_ate_prova = round(ritmo_diario_declarado * max(0, dias_restantes), 1)
    questoes_projetadas_adicionais = int(horas_estudo_proj_ate_prova * cadencia_questoes_hora)
    total_questoes_proj_dia_prova = total_questoes + questoes_projetadas_adicionais

    # Benchmarks Cebraspe / Concurso
    benchmark_questoes_recomendado = "2.500 a 4.000 questões Cebraspe resolvidas"
    benchmark_taxa_acerto_ideal = "82% a 88% de acerto bruto (para neutralizar o fator '1 errada anula 1 certa' e manter pontuação líquida > 78%)"
    benchmark_cadencia_ideal = "12 a 18 questões por hora (com estudo reverso e baterias cronometradas)"

    # 3. Constância de Estudo & Heatmap
    datas_unicas = sorted(list(set(s.data for s in sessoes if s.data)))
    total_dias_estudados = len(datas_unicas)

    if datas_unicas:
        p_val = datas_unicas[0]
        u_val = datas_unicas[-1]
        p_date = p_val if isinstance(p_val, date) else datetime.strptime(str(p_val).split("T")[0], "%Y-%m-%d").date()
        u_date = u_val if isinstance(u_val, date) else datetime.strptime(str(u_val).split("T")[0], "%Y-%m-%d").date()
        dias_corridos_periodo = max(1, (hoje - p_date).days + 1)
        hiato_dias_sem_estudo = max(0, (hoje - u_date).days)
        dias_com_estudo = total_dias_estudados
        dias_sem_estudo = max(0, dias_corridos_periodo - dias_com_estudo)
        taxa_constancia_heatmap = round((dias_com_estudo / dias_corridos_periodo * 100), 1)
        media_horas_dia_estudo = round(total_horas / dias_com_estudo, 1) if dias_com_estudo > 0 else 0.0
        media_horas_dia_corrido = round(total_horas / dias_corridos_periodo, 2)
        primeira_str = p_date.strftime("%d/%m/%Y")
        ultima_str = u_date.strftime("%d/%m/%Y")
    else:
        primeira_str = "Sem registros"
        ultima_str = "Sem registros"
        dias_corridos_periodo = 0
        hiato_dias_sem_estudo = 0
        dias_com_estudo = 0
        dias_sem_estudo = 0
        taxa_constancia_heatmap = 0.0
        media_horas_dia_estudo = 0.0
        media_horas_dia_corrido = 0.0

    if taxa_constancia_heatmap < 30.0:
        diagnostico_constancia = "Alerta Vermelho: padrão de 'estudo por explosão' com grandes hiatos de inatividade. O aluno estuda muitas horas em dias isolados, mas fica vários dias seguidos sem tocar no material, o que destrói a retenção na reta final."
    elif taxa_constancia_heatmap < 60.0:
        diagnostico_constancia = "Atenção: constância intermediária com oscilações semanais. Há semanas com bom ritmo e semanas com lapsos."
    else:
        diagnostico_constancia = "Excelente constância: frequência diária consolidada no Heatmap, condizente com a intensidade exigida para aprovação."

    disc_map: Dict[str, Dict[str, Any]] = {}
    for s in sessoes:
        d_nome = s.disciplina.nome if s.disciplina and s.disciplina.nome else "Geral"
        if d_nome not in disc_map:
            disc_map[d_nome] = {
                "nome": d_nome,
                "minutos": 0,
                "questoes": 0,
                "acertos": 0,
                "erros": 0
            }
        disc_map[d_nome]["minutos"] += s.tempo_estudado_minutos or 0
        disc_map[d_nome]["questoes"] += s.qtd_questoes_total or 0
        disc_map[d_nome]["acertos"] += s.qtd_acertos or 0
        disc_map[d_nome]["erros"] += s.qtd_erros or 0

    disciplinas_analise = []
    for d in disc_map.values():
        q = d["questoes"]
        taxa = round((d["acertos"] / q * 100), 1) if q > 0 else 0.0
        horas = round(d["minutos"] / 60.0, 1)
        disciplinas_analise.append({
            "nome": d["nome"],
            "horas": horas,
            "minutos": d["minutos"],
            "questoes": q,
            "acertos": d["acertos"],
            "erros": d["erros"],
            "taxa_acerto": taxa
        })

    disciplinas_analise.sort(key=lambda x: (x["questoes"], x["taxa_acerto"]), reverse=True)

    fortalezas = [d for d in disciplinas_analise if d["questoes"] >= 10 and d["taxa_acerto"] >= 80.0]
    gargalos = [d for d in disciplinas_analise if d["questoes"] > 0 and d["taxa_acerto"] < 70.0]
    sem_questoes = [d for d in disciplinas_analise if d["questoes"] == 0]

    nota_corte = config.nota_corte or 78.5
    diff_corte = round(taxa_global - nota_corte, 1)

    return {
        "concurso": config.concurso or "SEFAZ ALAGOAS",
        "cargo": config.cargo or "Auditor Fiscal da Receita Estadual",
        "especialidade": config.especialidade or "Geral",
        "banca": config.banca or "Cebraspe",
        "estilo_banca": config.estilo_banca or "Certo / Errado (1 anula 1)",
        "data_prova": data_prova_str,
        "dias_restantes": dias_restantes,
        "zona_tag": zona_tag,
        "zona_fase": zona_fase,
        "nota_corte": nota_corte,
        "taxa_global": taxa_global,
        "diff_corte": diff_corte,
        "total_sessoes": total_sessoes,
        "total_horas": total_horas,
        "total_dias_estudados": total_dias_estudados,
        "total_questoes": total_questoes,
        "total_acertos": total_acertos,
        "total_erros": total_erros,
        "ciclo_nome": ciclo_nome,
        "voltas_ciclo": voltas_ciclo,
        "carga_horaria_semanal": carga_horaria_semanal,
        "total_topicos_edital": total_topicos_edital,
        "topicos_cobertos_estimados": topicos_cobertos_estimados,
        "perc_edital_coberto": perc_edital_coberto,
        "topicos_restantes": topicos_restantes,
        "horas_para_zerar_edital": horas_para_zerar_edital,
        "horas_dia_necessarias_40d": horas_dia_necessarias_40d,
        "dias_para_zerar_na_meta_semanal": dias_para_zerar_na_meta_semanal,
        "topicos_cobertos_proj_ate_prova": topicos_cobertos_proj_ate_prova,
        "perc_edital_proj_ate_prova": perc_edital_proj_ate_prova,
        "cadencia_questoes_hora": cadencia_questoes_hora,
        "horas_estudo_proj_ate_prova": horas_estudo_proj_ate_prova,
        "questoes_projetadas_adicionais": questoes_projetadas_adicionais,
        "total_questoes_proj_dia_prova": total_questoes_proj_dia_prova,
        "benchmark_questoes_recomendado": benchmark_questoes_recomendado,
        "benchmark_taxa_acerto_ideal": benchmark_taxa_acerto_ideal,
        "benchmark_cadencia_ideal": benchmark_cadencia_ideal,
        "primeira_data_estudo": primeira_str,
        "ultima_data_estudo": ultima_str,
        "dias_corridos_periodo": dias_corridos_periodo,
        "dias_com_estudo": dias_com_estudo,
        "dias_sem_estudo": dias_sem_estudo,
        "taxa_constancia_heatmap": taxa_constancia_heatmap,
        "hiato_dias_sem_estudo": hiato_dias_sem_estudo,
        "media_horas_dia_estudo": media_horas_dia_estudo,
        "media_horas_dia_corrido": media_horas_dia_corrido,
        "diagnostico_constancia": diagnostico_constancia,
        "disciplinas": disciplinas_analise,
        "fortalezas": fortalezas,
        "gargalos": gargalos,
        "sem_questoes": sem_questoes
    }

async def tentar_gerar_com_gemini(dados: Dict[str, Any], api_key: str) -> Optional[Dict[str, Any]]:
    prompt = f"""Você é o Coach de Estudos e Mentor Estratégico de Elite em Concursos Públicos do app Orbis.
Analise com extremo rigor analítico, olhar clínico de coach de alta performance, profundidade matemática e linguagem viva, dinâmica e visual os dados reais e completos do aluno abaixo.

IMPORTANTE: NUNCA USE RESPOSTAS GENÉRICAS OU CLICHÊS DE MODELO. Traga uma análise inédita e perspicaz, avaliando o comportamento específico da banca examinadora ({dados['banca']}), o tempo restante ({dados['dias_restantes']} dias), a viabilidade matemática de zerar o edital, a cadência e projeção de questões vs o patamar ideal de aprovação, e a leitura cirúrgica da constância no Heatmap.

ESTILO VISUAL & ELEMENTOS GRÁFICOS OBRIGATÓRIOS:
- Use emojis expressivos (🎯, 📊, 🚨, ⏳, 📅, 💡, 🛡️, 📈, ⚖️, 🔍, ⚡, 🔥) no início de blocos e para enfatizar mensagens, deixando o texto convidativo e dinâmico.
- Use formatação Markdown (**negrito**) para destacar métricas críticas, percentuais, nomes de disciplinas, números de dias e termos-chave.
- Deixe o texto claro, escaneável e visualmente estimulante, sem parágrafos maçantes.

DADOS REAIS E COMPLETOS DO ALUNO:
- Concurso Alvo: {dados['concurso']}
- Cargo Alvo: {dados['cargo']} ({dados['especialidade']})
- Banca Examinadora: {dados['banca']} (Critério: {dados['estilo_banca']})
- Dias Restantes para a Prova: {dados['dias_restantes']} dias (Zona: {dados['zona_tag']} - {dados['zona_fase']})
- Nota de Corte Projetada: {dados['nota_corte']}%
- Rendimento Global Atual: {dados['taxa_global']}% (Diferença para o corte: {dados['diff_corte']:+0.1f} p.p.)

1. MÉTRICAS DO EDITAL & TÓPICOS (PREMISSA: 1 HORA = 1 TÓPICO):
- Total de Tópicos no Edital: {dados['total_topicos_edital']} tópicos
- Horas Estudadas Acumuladas: {dados['total_horas']}h (~{dados['topicos_cobertos_estimados']} tópicos cobertos, equivalente a {dados['perc_edital_coberto']}% do edital)
- Tópicos Restantes para Zerar o Edital: {dados['topicos_restantes']} tópicos (= {dados['horas_para_zerar_edital']}h necessárias)
- Ritmo Diário Necessário para Zerar 100% nos {dados['dias_restantes']} dias: {dados['horas_dia_necessarias_40d']}h líquidas por dia (ininterruptas)
- Meta Semanal Declarada no Ciclo: {dados['carga_horaria_semanal']}h/semana (~{round(dados['carga_horaria_semanal']/7, 1)}h/dia)
- Projeção no Ritmo Declarado até a Prova: cobrirá mais ~{round((dados['carga_horaria_semanal']/7)*dados['dias_restantes'])} tópicos, totalizando ~{dados['topicos_cobertos_proj_ate_prova']} de {dados['total_topicos_edital']} tópicos (~{dados['perc_edital_proj_ate_prova']}% do edital)
- Dias Necessários para Zerar no Ritmo Declarado: {dados['dias_para_zerar_na_meta_semanal']} dias (muito superior aos {dados['dias_restantes']} dias restantes!)

2. MÉTRICAS DE QUESTÕES & CADÊNCIA:
- Total de Questões Resolvidas: {dados['total_questoes']} itens ({dados['total_acertos']} acertos, {dados['total_erros']} erros)
- Cadência Atual de Treino: {dados['cadencia_questoes_hora']} questões resolvidas por hora de estudo
- Projeção de Questões até a Prova (mantendo {dados['cadencia_questoes_hora']} q/h e carga projetada de {dados['horas_estudo_proj_ate_prova']}h): +{dados['questoes_projetadas_adicionais']} questões -> Total Acumulado: {dados['total_questoes_proj_dia_prova']} questões
- Benchmark de Elite para {dados['banca']} no {dados['concurso']}:
  * Volume total recomendado: {dados['benchmark_questoes_recomendado']}
  * Taxa de acerto ideal recomendada: {dados['benchmark_taxa_acerto_ideal']}
  * Cadência de treino recomendada: {dados['benchmark_cadencia_ideal']}

3. CONSTÂNCIA DE ESTUDO & ANÁLISE DO HEATMAP:
- Período Analisado: {dados['dias_corridos_periodo']} dias corridos (de {dados['primeira_data_estudo']} a {dados['ultima_data_estudo']})
- Dias Ativos no Heatmap com Estudo: {dados['dias_com_estudo']} dias estudados vs {dados['dias_sem_estudo']} dias vazios
- Taxa de Constância no Heatmap: {dados['taxa_constancia_heatmap']}% de presença
- Média por Dia de Estudo Efetivo: {dados['media_horas_dia_estudo']}h/dia estudado
- Média por Dia Corrido (Diluída): {dados['media_horas_dia_corrido']}h/dia
- Hiato Atual sem Registrar Sessão: {dados['hiato_dias_sem_estudo']} dias
- Diagnóstico do Padrão: {dados['diagnostico_constancia']}

4. DESEMPENHO DETALHADO POR DISCIPLINA (Horas, Questões e % de Acerto):
{json.dumps(dados['disciplinas'], indent=2, ensure_ascii=False)}

RETORNE ESTRITAMENTE UM JSON NO FORMATO ABAIXO (SEM TEXTO ADICIONAL):
{{
  "resumo_executivo": "🎯 Parágrafo executivo afiado, direto, motivador e estratégico (3 a 4 linhas). Comece com emoji. Destaque em **negrito** métricas-chave, confronto da taxa ({dados['taxa_global']}%) com o corte ({dados['nota_corte']}%), dias restantes ({dados['dias_restantes']} dias), e a grande encruzilhada tática entre cobertura de edital, constância e a banca {dados['banca']}.",
  "pontos_analise": [
    "📊 **Competitividade & Projeção de Questões:** Confrontar a taxa atual ({dados['taxa_global']}%) com o corte ({dados['nota_corte']}%), analisar as questões feitas no tempo estudado ({dados['cadencia_questoes_hora']} q/h) e a projeção de {dados['total_questoes_proj_dia_prova']} itens até a prova. Comparar com o patamar ideal de acertos ({dados['benchmark_taxa_acerto_ideal']}) e o total de questões recomendado ({dados['benchmark_questoes_recomendado']}), indicando claramente se precisa acelerar a cadência prática.",
    "🚨 **Ponto Cego & Análise de Gargalos:** Diagnóstico cirúrgico dos maiores gargalos ou matérias perigosas (ex: disciplinas zeradas ou com aproveitamento crítico), alertando sobre armadilhas da {dados['banca']} e a regra de 1 errada anula 1 certa com emojis de atenção.",
    "⏳ **Ritmo, Tópicos & Fechamento do Edital:** Analisar o volume de horas ({dados['total_horas']}h) na premissa de 1 hora por tópico do edital ({dados['total_topicos_edital']} tópicos totais). Informar quantos tópicos restam ({dados['topicos_restantes']}), quanto tempo daria para zerar o edital nos {dados['dias_restantes']} dias restantes (necessárias {dados['horas_dia_necessarias_40d']}h/dia vs os {dados['dias_para_zerar_na_meta_semanal']} dias necessários no ritmo do ciclo), orientando se é viável zerar tudo ou se deve aplicar a priorização 80/20 de Pareto.",
    "📅 **Constância no Heatmap & Prescrição Tática:** Analisar a regularidade no Heatmap ({dados['dias_com_estudo']} dias ativos em {dados['dias_corridos_periodo']} dias corridos, taxa de {dados['taxa_constancia_heatmap']}% e hiato de {dados['hiato_dias_sem_estudo']} dias). Dizer categoricamente se essa constância está condizente com o esforço exigido para {dados['concurso']} e prescrever a rotina semanal imediata (distribuição diária de horas, baterias comentadas e controle de consistência)."
  ]
}}"""

    agora_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
    prompt_completo = f"{prompt}\n\n[SEED TEMPORAL: {agora_timestamp}]"

    # Lista de modelos do Google Gemini com alta disponibilidade e suporte a resposta JSON
    modelos_candidatos = [
        "gemini-flash-lite-latest",
        "gemini-3.1-flash-lite",
        "gemini-3.5-flash",
        "gemini-3.8-flash",
        "gemini-flash-latest"
    ]

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        config_params = types.GenerateContentConfig(
            temperature=0.95,
            response_mime_type="application/json"
        )

        for modelo in modelos_candidatos:
            try:
                response = client.models.generate_content(
                    model=modelo,
                    contents=prompt_completo,
                    config=config_params
                )
                texto = response.text.strip()
                if texto.startswith("```json"):
                    texto = texto[7:]
                if texto.endswith("```"):
                    texto = texto[:-3]
                parsed = json.loads(texto.strip())
                agora = datetime.now()
                return {
                    "titulo": "INSIGHTS DE IA",
                    "subtitulo": "Leitura dos indicadores em tempo real",
                    "resumo_executivo": parsed.get("resumo_executivo"),
                    "pontos_analise": parsed.get("pontos_analise", []),
                    "modelo_origem": f"Google Gemini ({modelo})",
                    "timestamp": agora.strftime("%H:%M:%S"),
                    "data_atualizacao": agora.isoformat(),
                    "metricas_rapidas": {
                        "edital_coberto_perc": dados.get("perc_edital_coberto", 0),
                        "topicos_cobertos": int(dados.get("topicos_cobertos_estimados", 0)),
                        "total_topicos": dados.get("total_topicos_edital", 0),
                        "cadencia_questoes_hora": dados.get("cadencia_questoes_hora", 0),
                        "questoes_proj_prova": dados.get("total_questoes_proj_dia_prova", 0),
                        "constancia_heatmap_perc": dados.get("taxa_constancia_heatmap", 0),
                        "dias_estudados": dados.get("dias_com_estudo", 0),
                        "dias_corridos": dados.get("dias_corridos_periodo", 0),
                        "taxa_global": dados.get("taxa_global", 0),
                        "nota_corte": dados.get("nota_corte", 0),
                        "diff_corte": dados.get("diff_corte", 0)
                    }
                }
            except Exception as mod_err:
                print(f"Modelo {modelo} indisponível ou em alta demanda: {mod_err}. Tentando próximo...")
                continue
    except Exception as e:
        print(f"Erro ao instanciar cliente genai: {e}")

    return None

def gerar_insight_heuristico(dados: Dict[str, Any]) -> Dict[str, Any]:
    concurso = dados["concurso"]
    banca = dados["banca"]
    dias = dados["dias_restantes"]
    total_horas = dados["total_horas"]
    total_questoes = dados["total_questoes"]
    taxa = dados["taxa_global"]
    corte = dados["nota_corte"]
    diff = dados["diff_corte"]
    zona = dados["zona_tag"]

    total_topicos = dados.get("total_topicos_edital", 369)
    topicos_cobertos = dados.get("topicos_cobertos_estimados", 0)
    topicos_restantes = dados.get("topicos_restantes", 0)
    perc_edital = dados.get("perc_edital_coberto", 0)
    horas_dia_necessarias = dados.get("horas_dia_necessarias_40d", 0)
    dias_para_zerar = dados.get("dias_para_zerar_na_meta_semanal", 0)
    carga_semanal = dados.get("carga_horaria_semanal", 20.0)

    cadencia = dados.get("cadencia_questoes_hora", 0)
    questoes_proj = dados.get("total_questoes_proj_dia_prova", 0)
    benchmark_questoes = dados.get("benchmark_questoes_recomendado", "2.500 a 4.000 questões Cebraspe")
    benchmark_taxa = dados.get("benchmark_taxa_acerto_ideal", "82% a 88% de acerto bruto")

    dias_com_estudo = dados.get("dias_com_estudo", 0)
    dias_corridos = dados.get("dias_corridos_periodo", 0)
    constancia_heatmap = dados.get("taxa_constancia_heatmap", 0)
    hiato_dias = dados.get("hiato_dias_sem_estudo", 0)

    diff_str = f"+{diff} p.p. acima do corte" if diff >= 0 else f"{abs(diff)} p.p. abaixo do corte"
    fortalezas_nomes = [f"{d['nome']} ({d['taxa_acerto']}%)" for d in dados["fortalezas"][:2]]
    gargalos_nomes = [f"{d['nome']} ({d['taxa_acerto']}%)" for d in dados["gargalos"][:2]]

    # 4 Arquétipos Dinâmicos de Coach para variação viva
    arquetipos = [
        "estrategista_corte",
        "tatico_reta_final",
        "auditor_gargalos",
        "mentalidade_banca"
    ]
    arq = random.choice(arquetipos)

    if arq == "estrategista_corte":
        resumo_executivo = (
            f"🎯 **Contagem Regressiva de {dias} dias** para o **{concurso}** ({banca}). Sua margem atual está em **{taxa}%** ({diff_str} projetado de {corte}%). "
            f"Você cobriu **{int(topicos_cobertos)} de {total_topicos} tópicos** ({perc_edital}% do edital) com **{total_questoes} questões resolvidas**. "
            f"Para transformar essa margem em vaga garantida, é imperativo blindar a pontuação líquida frente a {', '.join(gargalos_nomes) if gargalos_nomes else 'erros evitáveis'} e regularizar a constância no Heatmap."
        )
    elif arq == "tatico_reta_final":
        resumo_executivo = (
            f"⚡ **Fase Decisiva ({dias} dias)**: momento crítico para o **{concurso}**. Com aproveitamento de **{taxa}%** e cadência de **{cadencia} q/h**, "
            f"seu índice de competitividade é real. Contudo, no estilo **{banca}**, a estabilidade emocional, o controle de erros em "
            f"{', '.join(gargalos_nomes) if gargalos_nomes else 'matérias com gaps'} e o fechamento estratégico dos {topicos_restantes} tópicos restantes definirão a aprovação."
        )
    elif arq == "auditor_gargalos":
        resumo_executivo = (
            f"🔍 **Auditoria de Desempenho ({concurso} - {banca})**: Restam exatamente **{dias} dias**. Você acumula **{total_horas}h** e média de **{taxa}%** de aproveitamento. "
            f"Embora {', '.join(fortalezas_nomes) if fortalezas_nomes else 'disciplinas fortes'} puxem a nota para cima, "
            f"o calcanhar de Aquiles em {', '.join(gargalos_nomes) if gargalos_nomes else 'disciplinas zeradas'} e a cobertura de apenas {perc_edital}% do edital exigem recalibragem imediata."
        )
    else:
        resumo_executivo = (
            f"🧭 **Radar da Banca ({banca})**: A **{dias} dias** da batalha no **{concurso}**, você acumula **{total_horas}h** estudadas ({perc_edital}% do edital coberto) e rendimento geral de **{taxa}%**. "
            f"O ritmo é promissor, mas a banca {banca} pune severamente oscilações. A prioridade agora não é tentar ler tudo de forma passiva, "
            f"mas precisão cirúrgica de acertos nos tópicos mais recorrentes da prova."
        )

    pontos = []

    # Ponto 1: Competitividade & Projeção de Questões
    ponto1 = (
        f"📊 **Competitividade & Projeção de Questões:** Com aproveitamento global de **{taxa}%** ({diff_str}), você opera com folga sobre a nota de corte ({corte}%). "
        f"Nas **{total_horas}h estudadas**, você resolveu **{total_questoes} itens** (cadência de **{cadencia} q/h**). "
        f"Mantendo esse ritmo, a projeção é alcançar **~{questoes_proj} questões** até a prova. "
        f"Atenção ao perfil da banca **{banca}**: candidatos competitivos de elite acumulam **{benchmark_questoes}** com taxa ideal de **{benchmark_taxa}**. "
        f"Para se aproximar desse patamar, é fundamental acelerar a resolução prática para 12 a 15 q/h através de estudo reverso."
    )
    pontos.append(ponto1)

    # Ponto 2: Gargalos
    if dados["gargalos"]:
        crit = dados["gargalos"][0]
        ponto2_variacoes = [
            f"🚨 **Gargalo Crítico de Prova:** **{crit['nome']}** acusa **{crit['taxa_acerto']}%** de acerto em {crit['questoes']} itens resolvidos — risco extremo na banca {banca}, onde cada erro subtrai uma questão certa.",
            f"🚨 **Ponto de Vulnerabilidade Tática:** **{crit['nome']}** apresenta aproveitamento perigoso de **{crit['taxa_acerto']}%**. Numa prova disputada ponto a ponto pela {banca}, este é o maior vazamento de nota do seu ciclo.",
            f"⚠️ **Alerta de Risco Cirúrgico:** O rendimento de **{crit['taxa_acerto']}%** em **{crit['nome']}** exige contenção urgente de danos. Elimine o chute nessa matéria e mapeie as pegadinhas recorrentes da banca."
        ]
        pontos.append(random.choice(ponto2_variacoes))
    elif dados["sem_questoes"]:
        sem_q = dados["sem_questoes"][0]
        pontos.append(f"⚠️ **Disciplina Oculta:** **{sem_q['nome']}** possui teoria acumulada mas zero questões registradas. Concurseiro não passa com teoria sem treino de bateria.")
    else:
        pontos.append(f"🛡️ **Mapeamento de Lacunas:** Mantenha caderno de erros ativo em todas as disciplinas limítrofes para estancar perda de pontos.")

    # Ponto 3: Ritmo, Tópicos & Fechamento do Edital
    ponto3 = (
        f"⏳ **Ritmo, Tópicos & Fechamento do Edital:** Na premissa de 1 hora por tópico, suas **{total_horas}h estudadas** cobriram cerca de **{int(topicos_cobertos)} dos {total_topicos} tópicos** ({perc_edital}% do edital), "
        f"restando **{topicos_restantes} tópicos** a serem vistos. Para zerar 100% do edital nos {dias} dias restantes, seriam necessárias **{horas_dia_necessarias}h líquidas diárias** sem folga — meta impraticável no ritmo semanal de {carga_semanal}h/sem (que levaria ~{dias_para_zerar} dias). "
        f"A diretriz estratégica é abandonar a cobertura linear e aplicar a **Regra 80/20 de Pareto**: focar nos tópicos de maior peso histórico da banca {banca}."
    )
    pontos.append(ponto3)

    # Ponto 4: Constância no Heatmap & Prescrição Tática
    ponto4 = (
        f"📅 **Constância no Heatmap & Prescrição Tática:** A leitura do Heatmap acusa **{dias_com_estudo} dias com estudo em {dias_corridos} dias corridos** ({constancia_heatmap}% de constância) e um hiato recente de **{hiato_dias} dias sem estudo registrado**. "
        f"Esse padrão de 'estudo por explosão' (cramming) não é condizente com o esforço e a retenção exigidos para o {concurso}. "
        f"Prescrição imediata: dilua a carga em **3h a 4h líquidas diárias** com 6 dias de esteira ativa por semana, priorizando blocos de questões comentadas e revisão diária no Anki."
    )
    pontos.append(ponto4)

    agora = datetime.now()
    return {
        "titulo": "INSIGHTS DE IA",
        "subtitulo": "Leitura dos indicadores em tempo real",
        "resumo_executivo": resumo_executivo,
        "pontos_analise": pontos,
        "modelo_origem": "Coach IA Orbis (Heurístico Dinâmico)",
        "timestamp": agora.strftime("%H:%M:%S"),
        "data_atualizacao": agora.isoformat(),
        "metricas_rapidas": {
            "edital_coberto_perc": dados.get("perc_edital_coberto", 0),
            "topicos_cobertos": int(dados.get("topicos_cobertos_estimados", 0)),
            "total_topicos": dados.get("total_topicos_edital", 0),
            "cadencia_questoes_hora": dados.get("cadencia_questoes_hora", 0),
            "questoes_proj_prova": dados.get("total_questoes_proj_dia_prova", 0),
            "constancia_heatmap_perc": dados.get("taxa_constancia_heatmap", 0),
            "dias_estudados": dados.get("dias_com_estudo", 0),
            "dias_corridos": dados.get("dias_corridos_periodo", 0),
            "taxa_global": dados.get("taxa_global", 0),
            "nota_corte": dados.get("nota_corte", 0),
            "diff_corte": dados.get("diff_corte", 0)
        }
    }

@router.get("/status-chave")
def status_chave_gemini(db: Session = Depends(get_db)):
    config = db.query(ConfiguracaoPainelProva).first()
    if not config:
        config = ConfiguracaoPainelProva(id=1)
        db.add(config)
        db.commit()
        db.refresh(config)

    chave = obter_chave_gemini(config)
    configurada = bool(chave)
    mascarada = None
    origem = "nenhuma"
    if config.gemini_api_key and config.gemini_api_key.strip():
        origem = "banco"
        k = config.gemini_api_key.strip()
        mascarada = f"{k[:6]}...{k[-4:]}" if len(k) > 10 else "******"
    elif os.getenv("GEMINI_API_KEY"):
        origem = "env"
        k = os.getenv("GEMINI_API_KEY").strip()
        mascarada = f"{k[:6]}...{k[-4:]}" if len(k) > 10 else "******"

    return {
        "configurada": configurada,
        "chave_mascarada": mascarada,
        "origem": origem,
        "modelo": "Google Gemini (Flash Lite)"
    }

@router.post("/config-chave")
async def configurar_chave_gemini(payload: dict = Body(...), db: Session = Depends(get_db)):
    config = db.query(ConfiguracaoPainelProva).first()
    if not config:
        config = ConfiguracaoPainelProva(id=1)
        db.add(config)

    chave_raw = payload.get("api_key", "").strip()
    config.gemini_api_key = chave_raw if chave_raw else None
    config.ultimo_insight_ia = None  # Limpa cache para forçar análise nova
    db.commit()
    db.refresh(config)

    # Gera nova análise com a chave configurada
    dados_estudo = calcular_dados_estudo(db)
    chave_ativa = obter_chave_gemini(config)
    insight = None
    if chave_ativa:
        insight = await tentar_gerar_com_gemini(dados_estudo, chave_ativa)

    if not insight:
        insight = gerar_insight_heuristico(dados_estudo)

    config.ultimo_insight_ia = json.dumps(insight, ensure_ascii=False)
    config.data_insight_ia = datetime.now()
    db.commit()

    return {
        "sucesso": True,
        "configurada": bool(chave_ativa),
        "insight": insight
    }

@router.get("/insights")
async def obter_insights_ia(db: Session = Depends(get_db)):
    config = db.query(ConfiguracaoPainelProva).first()
    if not config:
        config = ConfiguracaoPainelProva(id=1)
        db.add(config)
        db.commit()
        db.refresh(config)

    # Retorno instantâneo do último insight em cache (< 2ms) para nunca travar a aplicação
    if config.ultimo_insight_ia:
        try:
            return json.loads(config.ultimo_insight_ia)
        except Exception:
            pass

    dados_estudo = calcular_dados_estudo(db)
    chave_ativa = obter_chave_gemini(config)
    insight = None
    if chave_ativa:
        insight = await tentar_gerar_com_gemini(dados_estudo, chave_ativa)

    if not insight:
        insight = gerar_insight_heuristico(dados_estudo)

    config.ultimo_insight_ia = json.dumps(insight, ensure_ascii=False)
    config.data_insight_ia = datetime.now()
    db.commit()

    return insight

@router.post("/insights/recarregar")
async def recarregar_insights_ia(db: Session = Depends(get_db)):
    config = db.query(ConfiguracaoPainelProva).first()
    if not config:
        config = ConfiguracaoPainelProva(id=1)
        db.add(config)
        db.commit()
        db.refresh(config)

    agora = datetime.now()
    dados_estudo = calcular_dados_estudo(db)
    chave_ativa = obter_chave_gemini(config)
    insight = None
    if chave_ativa:
        insight = await tentar_gerar_com_gemini(dados_estudo, chave_ativa)

    if not insight:
        insight = gerar_insight_heuristico(dados_estudo)

    config.ultimo_insight_ia = json.dumps(insight, ensure_ascii=False)
    config.data_insight_ia = agora
    db.commit()

    return insight
