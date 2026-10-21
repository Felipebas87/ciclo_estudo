import os
import json
import random
import httpx
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
        k = config.gemini_api_key.strip(" \t\r\n'\"")
        if k:
            return k
    # Prioridade 2: Variável de ambiente no servidor (.env ou os.environ)
    env_key = os.getenv("GEMINI_API_KEY")
    if env_key and env_key.strip():
        k = env_key.strip(" \t\r\n'\"")
        if k:
            return k
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

    # 1.1 Tópicos com priorização (P1, P2, P3 e Mais Cobrados) e sessões necessárias
    topicos_query = db.query(Topico).join(Disciplina).filter(Disciplina.categoria != 'REVISAO_ANKI')
    if edital_id:
        topicos_query = topicos_query.filter(Disciplina.edital_id == edital_id)
    todos_topicos_db = topicos_query.all()

    sessoes_topicos_vistos_ids = set(s.topico_id for s in sessoes if s.topico_id is not None)

    def topico_esta_visto(t):
        return (t.id in sessoes_topicos_vistos_ids) or bool(t.concluido)

    topicos_prioritarios = [t for t in todos_topicos_db if t.prioridade is not None or t.mais_cobrado]
    total_prioritarios = len(topicos_prioritarios)
    prioritarios_vistos = [t for t in topicos_prioritarios if topico_esta_visto(t)]
    prioritarios_pendentes = [t for t in topicos_prioritarios if not topico_esta_visto(t)]

    total_prioritarios_vistos = len(prioritarios_vistos)
    total_prioritarios_pendentes = len(prioritarios_pendentes)
    perc_prioritarios_cobertos = round((total_prioritarios_vistos / total_prioritarios * 100), 1) if total_prioritarios > 0 else 0.0

    total_p1 = sum(1 for t in todos_topicos_db if t.prioridade == 1)
    p1_vistos = sum(1 for t in todos_topicos_db if t.prioridade == 1 and topico_esta_visto(t))
    p1_pendentes = max(0, total_p1 - p1_vistos)

    total_p2 = sum(1 for t in todos_topicos_db if t.prioridade == 2)
    p2_vistos = sum(1 for t in todos_topicos_db if t.prioridade == 2 and topico_esta_visto(t))
    p2_pendentes = max(0, total_p2 - p2_vistos)

    total_p3 = sum(1 for t in todos_topicos_db if t.prioridade == 3)
    p3_vistos = sum(1 for t in todos_topicos_db if t.prioridade == 3 and topico_esta_visto(t))
    p3_pendentes = max(0, total_p3 - p3_vistos)

    total_mais_cobrados = sum(1 for t in todos_topicos_db if t.mais_cobrado)
    mais_cobrados_vistos = sum(1 for t in todos_topicos_db if t.mais_cobrado and topico_esta_visto(t))
    mais_cobrados_pendentes = max(0, total_mais_cobrados - mais_cobrados_vistos)

    # Sessões de estudo necessárias para terminar os tópicos prioritários (1 sessão = 1 tópico = 1 hora)
    sessoes_necessarias_prioritarios = total_prioritarios_pendentes
    horas_necessarias_prioritarios = float(total_prioritarios_pendentes)
    dias_para_zerar_prioritarios = round(horas_necessarias_prioritarios / ritmo_diario_declarado, 1) if ritmo_diario_declarado > 0 else 0

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
        "total_prioritarios": total_prioritarios,
        "total_prioritarios_vistos": total_prioritarios_vistos,
        "total_prioritarios_pendentes": total_prioritarios_pendentes,
        "perc_prioritarios_cobertos": perc_prioritarios_cobertos,
        "total_p1": total_p1,
        "p1_pendentes": p1_pendentes,
        "total_p2": total_p2,
        "p2_pendentes": p2_pendentes,
        "total_p3": total_p3,
        "p3_pendentes": p3_pendentes,
        "total_mais_cobrados": total_mais_cobrados,
        "mais_cobrados_pendentes": mais_cobrados_pendentes,
        "sessoes_necessarias_prioritarios": sessoes_necessarias_prioritarios,
        "horas_necessarias_prioritarios": horas_necessarias_prioritarios,
        "dias_para_zerar_prioritarios": dias_para_zerar_prioritarios,
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

def _montar_resposta_insight(parsed: dict, modelo_origem: str, agora: datetime, dados: dict) -> dict:
    return {
        "titulo": "INSIGHTS DE IA",
        "subtitulo": "Leitura dos indicadores em tempo real",
        "resumo_executivo": parsed.get("resumo_executivo"),
        "pontos_analise": parsed.get("pontos_analise", []),
        "modelo_origem": modelo_origem,
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
            "diff_corte": dados.get("diff_corte", 0),
            "total_prioritarios": dados.get("total_prioritarios", 0),
            "total_prioritarios_pendentes": dados.get("total_prioritarios_pendentes", 0),
            "sessoes_necessarias_prioritarios": dados.get("sessoes_necessarias_prioritarios", 0)
        }
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
- REGRA OBRIGATÓRIA DE ANÁLISE DO CORTE:
  * Se a taxa atual ({dados['taxa_global']}%) for MENOR que a nota de corte ({dados['nota_corte']}%), o aluno está {abs(dados['diff_corte']):.1f} p.p. ABAIXO DO CORTE. NUNCA diga que o aluno 'opera com folga' ou 'com margem confortável'! Afirme com clareza matemática que ele está abaixo da nota de corte, na zona de risco/atenção, e indique o que precisa para reverter.
  * Se a taxa for maior ou igual ao corte, aponte a margem positiva real sobre a nota de corte.

1. MÉTRICAS DO EDITAL & TRILHA DE TÓPICOS PRIORITÁRIOS (1 HORA = 1 SESSÃO = 1 TÓPICO):
- Total de Tópicos no Edital: {dados['total_topicos_edital']} tópicos
- Tópicos Mapeados com Prioridade (P1, P2, P3 ou Mais Cobrados): {dados['total_prioritarios']} tópicos ({dados['total_p1']} P1, {dados['total_p2']} P2, {dados['total_p3']} P3 e {dados['total_mais_cobrados']} Mais Cobrados)
- Tópicos Prioritários já Vencidos: {dados['total_prioritarios_vistos']} de {dados['total_prioritarios']} ({dados['perc_prioritarios_cobertos']}%)
- Tópicos Prioritários Restantes / Pendentes: {dados['total_prioritarios_pendentes']} tópicos ({dados['p1_pendentes']} P1 pendentes, {dados['mais_cobrados_pendentes']} Mais Cobrados pendentes)
- Sessões de Estudo Necessárias para Zerar os Tópicos Prioritários: {dados['sessoes_necessarias_prioritarios']} sessões de 1h (~{dados['dias_para_zerar_prioritarios']} dias necessários no ritmo do ciclo)
- Tópicos Gerais Restantes no Edital Inteiro: {dados['topicos_restantes']} tópicos (levaria {dados['dias_para_zerar_na_meta_semanal']} dias para ver tudo)
- Conclusão Tática: Zerar 100% de todo o edital ({dados['total_topicos_edital']} tópicos) em {dados['dias_restantes']} dias é inviável, MAS cobrir os {dados['total_prioritarios_pendentes']} tópicos prioritários exige apenas {dados['sessoes_necessarias_prioritarios']} sessões de 1h (~{dados['dias_para_zerar_prioritarios']} dias), sendo a estratégia de ouro para aprovação!

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
    "📊 **Competitividade & Projeção de Questões:** Confrontar a taxa atual ({dados['taxa_global']}%) com o corte ({dados['nota_corte']}%). Se estiver abaixo do corte ({dados['diff_corte']} p.p.), declare com precisão e seriedade que está abaixo do corte na zona de atenção/risco. NUNCA use 'opera com folga' se taxa < corte! Analisar a cadência ({dados['cadencia_questoes_hora']} q/h) e projeção ({dados['total_questoes_proj_dia_prova']} itens) vs benchmarks ({dados['benchmark_questoes_recomendado']} e {dados['benchmark_taxa_acerto_ideal']}).",
    "🚨 **Ponto Cego & Análise de Gargalos:** Diagnóstico cirúrgico dos maiores gargalos ou matérias perigosas (ex: disciplinas zeradas ou com aproveitamento crítico), alertando sobre armadilhas da {dados['banca']} e a regra de 1 errada anula 1 certa com emojis de atenção.",
    "🎯 **Trilha Prioritária, Ritmo & Sessões Necessárias:** Analisar quantos tópicos possuem priorização definida ({dados['total_prioritarios']} tópicos mapeados, sendo {dados['total_prioritarios_vistos']} vencidos e {dados['total_prioritarios_pendentes']} pendentes). Explicar que para fechar esse núcleo de maior peso são necessárias exatamente {dados['sessoes_necessarias_prioritarios']} sessões de 1h de estudo (~{dados['dias_para_zerar_prioritarios']} dias de estudo), sendo o plano de ação perfeito contra a inviabilidade de ver os {dados['total_topicos_edital']} tópicos gerais.", 
    "📅 **Constância no Heatmap & Prescrição Tática:** Analisar a regularidade no Heatmap ({dados['dias_com_estudo']} dias ativos em {dados['dias_corridos_periodo']} dias corridos, taxa de {dados['taxa_constancia_heatmap']}% e hiato de {dados['hiato_dias_sem_estudo']} dias). Dizer categoricamente se essa constância está condizente com o esforço exigido para {dados['concurso']} e prescrever a rotina semanal imediata (distribuição diária de horas, baterias comentadas e controle de consistência)."
  ]
}}"""

    agora_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
    prompt_completo = f"{prompt}\n\n[SEED TEMPORAL: {agora_timestamp}]"

    # Lista de modelos do Google Gemini com alta disponibilidade e suporte a resposta JSON
    modelos_candidatos = [
        "gemini-flash-lite-latest",
        "gemini-3.5-flash-lite",
        "gemini-3.5-flash",
        "gemini-flash-latest",
        "gemini-3.1-flash-lite"
    ]

    # Tentativa 1: Via SDK oficial google.genai (se instalado no ambiente)
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
                print(f"[IA INSIGHTS] Sucesso via SDK google.genai com modelo {modelo}")
                return _montar_resposta_insight(parsed, f"Google Gemini ({modelo})", datetime.now(), dados)
            except Exception as mod_err:
                print(f"[IA INSIGHTS] Modelo {modelo} via SDK falhou: {mod_err}. Tentando próximo...")
                continue
    except Exception as e:
        print(f"[IA INSIGHTS] SDK google.genai não carregado ({e}). Acionando API REST direta com HTTPX...")

    # Tentativa 2: Via REST API direta do Google Gemini com HTTPX (autônomo, sem dependências extras)
    for modelo in modelos_candidatos:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent?key={api_key}"
            payload = {
                "contents": [{"parts": [{"text": prompt_completo}]}],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "temperature": 0.95
                }
            }
            async with httpx.AsyncClient(timeout=35.0) as http_client:
                resp = await http_client.post(url, json=payload)
                if resp.status_code == 200:
                    resp_json = resp.json()
                    texto = resp_json["candidates"][0]["content"]["parts"][0]["text"].strip()
                    if texto.startswith("```json"):
                        texto = texto[7:]
                    if texto.endswith("```"):
                        texto = texto[:-3]
                    parsed = json.loads(texto.strip())
                    print(f"[IA INSIGHTS] Sucesso via REST HTTPX com modelo {modelo}")
                    return _montar_resposta_insight(parsed, f"Google Gemini ({modelo})", datetime.now(), dados)
                else:
                    print(f"[IA INSIGHTS] Modelo {modelo} via REST retornou HTTP {resp.status_code}: {resp.text[:120]}")
        except Exception as rest_err:
            print(f"[IA INSIGHTS] Erro na requisição REST para modelo {modelo}: {rest_err}")
            continue

    print("[IA INSIGHTS] Todos os modelos e métodos Gemini falharam. Recorrendo ao motor heurístico.")
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

    # Ponto 1: Competitividade & Projeção de Questões (diagnóstico sem contradição)
    if diff >= 3.0:
        corte_diagnostico = f"você opera com margem de segurança de **+{diff:.1f} p.p.** sobre a nota de corte projetada ({corte}%)."
    elif diff >= 0.0:
        corte_diagnostico = f"você opera no limiar da nota de corte projetada ({corte}%), com margem estreita de **+{diff:.1f} p.p.** que exige máxima atenção contra oscilações."
    elif diff >= -3.0:
        corte_diagnostico = f"você está em zona de atenção, **{abs(diff):.1f} p.p. abaixo da nota de corte** projetada ({corte}%). A distância é curta e plenamente recuperável estancando erros nas matérias mais cobradas."
    else:
        corte_diagnostico = f"você se encontra em zona de risco crítico, **{abs(diff):.1f} p.p. abaixo da nota de corte** projetada ({corte}%). É mandatório eliminar o chute cego e revisar a teoria dos pontos vulneráveis."

    ponto1 = (
        f"📊 **Competitividade & Projeção de Questões:** Com aproveitamento global de **{taxa}%** ({diff_str}), {corte_diagnostico} "
        f"Nas **{total_horas}h estudadas**, você resolveu **{total_questoes} itens** (cadência de **{cadencia} q/h**). "
        f"Mantendo esse ritmo, a projeção é alcançar **~{questoes_proj} questões** até a prova. "
        f"Atenção ao perfil da banca **{banca}**: candidatos competitivos de elite acumulam **{benchmark_questoes}** com taxa ideal de **{benchmark_taxa}**. "
        f"Para se aproximar desse patamar, acelere a cadência prática para 12 a 15 q/h através de estudo reverso."
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

    # Ponto 3: Trilha Prioritária, Ritmo & Sessões Necessárias
    tot_pri = dados.get("total_prioritarios", 0)
    pri_pend = dados.get("total_prioritarios_pendentes", 0)
    pri_vistos = dados.get("total_prioritarios_vistos", 0)
    sess_pri = dados.get("sessoes_necessarias_prioritarios", 0)
    dias_pri = dados.get("dias_para_zerar_prioritarios", 0)
    tot_p1 = dados.get("total_p1", 0)
    tot_p2 = dados.get("total_p2", 0)
    tot_p3 = dados.get("total_p3", 0)
    tot_mc = dados.get("total_mais_cobrados", 0)
    perc_pri = dados.get("perc_prioritarios_cobertos", 0)

    if tot_pri > 0:
        detalhe_trilha = (
            f"Na sua **Trilha Prioritária**, você mapeou **{tot_pri} tópicos essenciais** ({tot_p1} P1, {tot_p2} P2, {tot_p3} P3 e {tot_mc} Mais Cobrados), "
            f"com **{pri_vistos} já concluídos** ({perc_pri}%). Restam **{pri_pend} tópicos prioritários**, o que exige exatamente **{sess_pri} sessões de estudo de 1h** "
            f"para fechar 100% do núcleo decisivo da prova — meta plenamente viável em **~{dias_pri} dias** no ritmo semanal de {carga_semanal}h/sem do seu ciclo."
        )
    else:
        detalhe_trilha = (
            f"Você ainda não marcou tópicos com prioridade na aba **Verticalizado**. "
            f"Defina seus tópicos P1/P2/P3 e Mais Cobrados para que o sistema projete exatamente quantas sessões restam para garantir o núcleo essencial da aprovação."
        )

    ponto3 = (
        f"🎯 **Trilha Prioritária, Ritmo & Sessões Necessárias:** Na premissa de 1 hora por tópico, suas **{total_horas}h estudadas** cobriram cerca de **{int(topicos_cobertos)} dos {total_topicos} tópicos** ({perc_edital}% do edital total). "
        f"Zerar todos os {topicos_restantes} tópicos restantes nos {dias} dias restantes exigiria {horas_dia_necessarias}h/dia (inviável). "
        f"Por isso, a Regra 80/20 de Pareto é o caminho cirúrgico: {detalhe_trilha}"
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
            "total_prioritarios": dados.get("total_prioritarios", 0),
            "total_prioritarios_pendentes": dados.get("total_prioritarios_pendentes", 0),
            "sessoes_necessarias_prioritarios": dados.get("sessoes_necessarias_prioritarios", 0),
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

    chave_ativa = obter_chave_gemini(config)

    # Retorno instantâneo do último insight em cache (< 2ms) para nunca travar a aplicação
    if config.ultimo_insight_ia:
        try:
            cached = json.loads(config.ultimo_insight_ia)
            # Se o cache atual for heurístico mas agora há uma chave Gemini ativa,
            # tenta gerar com Gemini para atualizar o painel automaticamente!
            if not ("Heurístico" in str(cached.get("modelo_origem", "")) and chave_ativa):
                return cached
        except Exception:
            pass

    dados_estudo = calcular_dados_estudo(db)
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
