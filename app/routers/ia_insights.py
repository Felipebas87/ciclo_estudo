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

    sessoes = db.query(SessaoEstudo).all()
    total_sessoes = len(sessoes)
    total_minutos = sum(s.tempo_estudado_minutos or 0 for s in sessoes)
    total_horas = round(total_minutos / 60.0, 1)

    total_questoes = sum(s.qtd_questoes_total or 0 for s in sessoes)
    total_acertos = sum(s.qtd_acertos or 0 for s in sessoes)
    total_erros = sum(s.qtd_erros or 0 for s in sessoes)
    taxa_global = round((total_acertos / total_questoes * 100), 1) if total_questoes > 0 else 0.0

    dias_unicos = set()
    for s in sessoes:
        if s.data:
            dias_unicos.add(s.data.split("T")[0] if "T" in str(s.data) else str(s.data))
    total_dias_estudados = len(dias_unicos)

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

    ciclo = db.query(CicloEstudos).filter(CicloEstudos.ativo == True).first()
    ciclo_nome = ciclo.nome if ciclo else "Ciclo de Estudos"
    voltas_ciclo = ciclo.voltas_completas if ciclo else 0

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
        "disciplinas": disciplinas_analise,
        "fortalezas": fortalezas,
        "gargalos": gargalos,
        "sem_questoes": sem_questoes
    }

async def tentar_gerar_com_gemini(dados: Dict[str, Any], api_key: str) -> Optional[Dict[str, Any]]:
    prompt = f"""Você é o Coach de Estudos e Mentor Estratégico de Elite em Concursos Públicos do app Orbis.
Analise com rigor técnico, olhar clínico, profundidade e linguagem viva, dinâmica e altamente visual os dados reais do aluno abaixo.
IMPORTANTE: NUNCA USE RESPOSTAS GENÉRICAS OU CLICHÊS DE MODELO. Traga uma análise inédita e perspicaz, avaliando o comportamento específico da banca examinadora ({dados['banca']}), o tempo restante ({dados['dias_restantes']} dias), os pontos cegos e uma prescrição tática original.

ESTILO VISUAL & ELEMENTOS GRÁFICOS OBRIGATÓRIOS:
- Use emojis expressivos (🎯, 📊, 🚨, ⏳, 💡, 🛡️, 📈, ⚖️, 🔍, ⚡, 🔥) no início de blocos e para enfatizar mensagens, deixando o texto convidativo e dinâmico.
- Use formatação Markdown (**negrito**) para destacar métricas críticas, percentuais, nomes de disciplinas e termos-chave.
- Deixe o texto claro, escaneável e visualmente estimulante, sem parágrafos maçantes.

DADOS REAIS E COMPLETOS DO ALUNO:
- Concurso Alvo: {dados['concurso']}
- Cargo Alvo: {dados['cargo']} ({dados['especialidade']})
- Banca Examinadora: {dados['banca']} (Critério: {dados['estilo_banca']})
- Dias Restantes para a Prova: {dados['dias_restantes']} dias (Zona Atual: {dados['zona_tag']} - {dados['zona_fase']})
- Nota de Corte Projetada: {dados['nota_corte']}%
- Total Horas Estudadas: {dados['total_horas']}h acumuladas em {dados['total_dias_estudados']} dias estudados ({dados['total_sessoes']} sessões cumpridas)
- Total de Questões Resolvidas: {dados['total_questoes']} ({dados['total_acertos']} acertos, {dados['total_erros']} erros)
- Taxa Geral de Aproveitamento: {dados['taxa_global']}% (Diferença para a nota de corte: {dados['diff_corte']:+0.1f} p.p.)
- Giros Completos no Ciclo: {dados['voltas_ciclo']}

DESEMPENHO DETALHADO POR DISCIPLINA (Horas, Questões e % de Acerto):
{json.dumps(dados['disciplinas'], indent=2, ensure_ascii=False)}

RETORNE ESTRITAMENTE UM JSON NO FORMATO ABAIXO (SEM TEXTO ADICIONAL):
{{
  "resumo_executivo": "🎯 Parágrafo executivo afiado, direto e motivador (3 a 4 linhas). Comece com um emoji impactante (ex: 🎯 ou 🧭). Destaque em **negrito** métricas-chave, confronto da taxa ({dados['taxa_global']}%) com o corte ({dados['nota_corte']}%), a banca ({dados['banca']}) e a batalha tática a travar nos {dados['dias_restantes']} dias restantes.",
  "pontos_analise": [
    "📊 **Competitividade & Margem:** Análise da margem de segurança frente à nota de corte e banca, citando disciplinas de ponta em **negrito** e números reais.",
    "🚨 **Ponto Cego & Alerta da Banca:** Diagnóstico cirúrgico dos maiores gargalos ou matérias perigosas, alertando sobre armadilhas da {dados['banca']} com emojis de atenção.",
    "⏳ **Ritmo & Gestão do Tempo ({dados['dias_restantes']} dias):** Projeção prática de horas líquidas e volume de questões até a prova, orientando a energia do candidato.",
    "💡 **Prescrição Tática Inédita:** Plano de ação direto (técnicas ativas, cadernos de erros, Anki, baterias focadas) para a semana."
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
                    "data_atualizacao": agora.isoformat()
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
    total_sessoes = dados.get("total_sessoes", 0)
    total_horas = dados["total_horas"]
    total_dias = dados["total_dias_estudados"]
    total_questoes = dados["total_questoes"]
    taxa = dados["taxa_global"]
    corte = dados["nota_corte"]
    diff = dados["diff_corte"]
    zona = dados["zona_tag"]

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
            f"Você consolidou **{total_horas}h** de estudo e **{total_questoes} questões** resolvidas. A base está firme em {', '.join(fortalezas_nomes) if fortalezas_nomes else 'matérias-chave'}, "
            f"mas para transformar essa margem em vaga garantida, é imperativo blindar a pontuação líquida frente a {', '.join(gargalos_nomes) if gargalos_nomes else 'erros evitáveis'}."
        )
    elif arq == "tatico_reta_final":
        resumo_executivo = (
            f"⚡ **Fase Decisiva ({dias} dias)**: momento crítico para o **{concurso}**. Com **{total_sessoes} sessões** cumpridas e taxa global de **{taxa}%**, "
            f"seu índice de competitividade é real. Contudo, no estilo **{banca}**, a estabilidade emocional e o controle de erros em "
            f"{', '.join(gargalos_nomes) if gargalos_nomes else 'matérias com gaps'} definirão a aprovação. Hora de trocar estudo passivo por pressão tática."
        )
    elif arq == "auditor_gargalos":
        resumo_executivo = (
            f"🔍 **Auditoria de Desempenho ({concurso} - {banca})**: Restam exatamente **{dias} dias**. Você acumula **{total_horas}h** e média de **{taxa}%** de aproveitamento. "
            f"Embora {', '.join(fortalezas_nomes) if fortalezas_nomes else 'disciplinas fortes'} puxem a nota para cima, "
            f"o calcanhar de Aquiles em {', '.join(gargalos_nomes) if gargalos_nomes else 'disciplinas zeradas'} pode custar pontos preciosos de corte."
        )
    else:
        resumo_executivo = (
            f"🧭 **Radar da Banca ({banca})**: A **{dias} dias** da batalha no **{concurso}**, você acumula **{total_horas}h** estudadas em {total_dias} dias ativos e rendimento geral de **{taxa}%**. "
            f"O ritmo é promissor, mas a banca {banca} pune severamente oscilações. A prioridade agora não é quantidade de horas, "
            f"mas precisão cirúrgica de acertos e proteção de pontos nos tópicos mais críticos."
        )

    pontos = []

    # Ponto 1: Competitividade
    ponto1_variacoes = [
        f"📊 **Competitividade & Margem:** Com aproveitamento de **{taxa}%** ({diff_str}), você opera em zona de competitividade direta. {dados['fortalezas'][0]['nome'] + ' lidera com ' + str(dados['fortalezas'][0]['taxa_acerto']) + '% em ' + str(dados['fortalezas'][0]['questoes']) + ' questões' if dados['fortalezas'] else 'Mantenha ritmo para romper a barreira do corte.'}",
        f"📊 **Linha de Corte Alvo ({corte}%):** Seu rendimento global de **{taxa}%** está {diff_str}. {dados['fortalezas'][0]['nome'] if dados['fortalezas'] else 'O topo da esteira'} sustenta o índice, mas é preciso replicar esse padrão nas matérias secundárias.",
        f"📊 **Eficiência por Questão:** Das **{total_questoes} questões** registradas, seu índice de acertos é de **{taxa}%**. A consistência nas disciplinas centrais garante base sólida para a nota de corte (**{corte}%**)."
    ]
    pontos.append(random.choice(ponto1_variacoes))

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

    # Ponto 3: Projeção de Volume
    if dias > 0:
        media_bruta = round(total_horas / total_dias, 1) if total_dias > 0 else 2.5
        ritmo_proj = min(max(media_bruta, 2.0), 4.5)
        horas_semana_est = round(ritmo_proj * 6, 1)
        questoes_por_hora = (total_questoes / total_horas) if total_horas > 0 else 8.0
        questoes_proj = int(questoes_por_hora * ritmo_proj * dias)
        ponto3_variacoes = [
            f"⏳ **Volume & Cadência na Fase '{zona}':** Restam **{dias} dias**. Em ritmo recomendado de **{ritmo_proj}h/dia** (~{horas_semana_est}h/semana), a projeção é resolver cerca de **{questoes_proj} questões** da banca {banca} até o dia da prova.",
            f"⏳ **Projeção Tática até o Dia D:** Com **{dias} dias restantes** e mantendo {ritmo_proj}h diárias, você adicionará cerca de **{questoes_proj} itens** ao seu repertório prático da banca.",
            f"⚡ **Gestão de Energia & Tempo:** Na fase '{zona}', **{ritmo_proj}h líquidas diárias** garantem cobertura de mais **{questoes_proj} itens** da {banca} sem gerar estafa mental antes da prova."
        ]
        pontos.append(random.choice(ponto3_variacoes))
    else:
        pontos.append("🏁 **Fase Concluída:** Registre seus acertos na aba Resultados & Raio-X.")

    # Ponto 4: Prescrição do Coach
    if dados["gargalos"]:
        foco = dados["gargalos"][0]["nome"]
        ponto4_variacoes = [
            f"💡 **Prescrição Inédita do Coach:** Aloque os primeiros 2 blocos da semana para bateria comentada focada em **{foco}**. Não avance sem entender o motivo de cada gabarito da {banca}.",
            f"💡 **Ajuste de Rota Semanal:** Isole os 3 principais subtemas de **{foco}** e crie 20 cards no Anki com conceitos-chave para revisão diária acelerada.",
            f"🎯 **Direcionamento Estratégico:** Reduza temporariamente o tempo das disciplinas já dominadas e concentre **60% da carga da semana** em exercícios práticos de **{foco}**."
        ]
        pontos.append(random.choice(ponto4_variacoes))
    else:
        ponto4_variacoes = [
            f"💡 **Prescrição Inédita do Coach:** Implemente simulados parciais cronometrados de 40 questões em blocos mistos para treinar gestão de tempo e resistência mental sob pressão.",
            f"🎯 **Direcionamento Estratégico:** Intensifique revisões ativas no Anki no primeiro bloco do dia e dedique os demais exclusivamente a baterias inéditas da banca {banca}."
        ]
        pontos.append(random.choice(ponto4_variacoes))

    agora = datetime.now()
    return {
        "titulo": "INSIGHTS DE IA",
        "subtitulo": "Leitura dos indicadores a cada hora ou ao atualizar",
        "resumo_executivo": resumo_executivo,
        "pontos_analise": pontos,
        "modelo_origem": "Coach IA Orbis (Heurístico Dinâmico)",
        "timestamp": agora.strftime("%H:%M"),
        "data_atualizacao": agora.isoformat()
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

    agora = datetime.now()
    if config.ultimo_insight_ia and config.data_insight_ia:
        delta = (agora - config.data_insight_ia).total_seconds()
        if delta < 30:
            try:
                dados_cache = json.loads(config.ultimo_insight_ia)
                return dados_cache
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
    config.data_insight_ia = agora
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
