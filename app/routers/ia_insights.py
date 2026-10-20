import os
import json
from datetime import datetime, date, timezone
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.models.configuracao_prova import ConfiguracaoPainelProva
from app.models.sessao import SessaoEstudo
from app.models.disciplina import Disciplina
from app.models.ciclo import CicloEstudos, BlocoCiclo
from app.models.edital import Edital

router = APIRouter(prefix="/api/ia", tags=["Insights de IA"])

def calcular_dados_estudo(db: Session) -> Dict[str, Any]:
    # 1. Configuração da Prova
    config = db.query(ConfiguracaoPainelProva).first()
    if not config:
        config = ConfiguracaoPainelProva(id=1)
        db.add(config)
        db.commit()
        db.refresh(config)

    hoje = date.today()
    dias_restantes = None
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

    # 2. Sessões de Estudo
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

    # 3. Estatísticas por Disciplina
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

    # Ordenar por taxa de acerto e por questões
    disciplinas_analise.sort(key=lambda x: (x["questoes"], x["taxa_acerto"]), reverse=True)

    # Fortalezas (>= 80% e com questões)
    fortalezas = [d for d in disciplinas_analise if d["questoes"] >= 10 and d["taxa_acerto"] >= 80.0]
    # Gargalos (taxa < 70% com questões resolvidas ou 0%)
    gargalos = [d for d in disciplinas_analise if d["questoes"] > 0 and d["taxa_acerto"] < 70.0]
    # Pouco estudadas ou sem questões
    sem_questoes = [d for d in disciplinas_analise if d["questoes"] == 0]

    # 4. Ciclo de Estudos Ativo
    ciclo = db.query(CicloEstudos).filter(CicloEstudos.ativo == True).first()
    ciclo_nome = ciclo.nome if ciclo else "Ciclo de Estudos"
    voltas_ciclo = ciclo.voltas_completas if ciclo else 0

    nota_corte = config.nota_corte or 78.5
    diff_corte = round(taxa_global - nota_corte, 1)

    return {
        "concurso": config.concurso or "SEFAZ ALAGOAS",
        "cargo": config.cargo or "Auditor Fiscal da Receita Estadual",
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

def gerar_insight_heuristico(dados: Dict[str, Any]) -> Dict[str, Any]:
    concurso = dados["concurso"]
    banca = dados["banca"]
    dias = dados["dias_restantes"]
    total_horas = dados["total_horas"]
    total_dias = dados["total_dias_estudados"]
    total_questoes = dados["total_questoes"]
    taxa = dados["taxa_global"]
    corte = dados["nota_corte"]
    diff = dados["diff_corte"]
    zona = dados["zona_tag"]

    # Texto de comparação com corte
    if diff >= 0:
        comp_corte_resumo = f"+{diff} p.p. acima da nota de corte estimada ({corte}%)"
    else:
        comp_corte_resumo = f"{abs(diff)} p.p. abaixo da nota de corte alvo ({corte}%)"

    fortalezas_nomes = [f"{d['nome']} ({d['taxa_acerto']}%)" for d in dados["fortalezas"][:2]]
    gargalos_nomes = [f"{d['nome']} ({d['taxa_acerto']}%)" for d in dados["gargalos"][:2]]

    resumo_executivo = (
        f"A {dias} dias da prova do {concurso} ({banca}), seu histórico registra {dados['total_sessoes']} sessões "
        f"e {total_horas}h de estudo ativo em {total_dias} dias cumpridos, com taxa geral de acerto de {taxa}% — {comp_corte_resumo}. "
        f"A esteira indica excelente consolidação em {', '.join(fortalezas_nomes) if fortalezas_nomes else 'disciplinas-base'}, "
        f"mas exige intervenção tática imediata em {', '.join(gargalos_nomes) if gargalos_nomes else 'disciplinas de menor rendimento'} "
        f"para blindar a pontuação líquida."
    )

    pontos_analise = []

    # Ponto 1: Desempenho e Comparativo de Corte
    if dados["fortalezas"]:
        top = dados["fortalezas"][0]
        seg = dados["fortalezas"][1] if len(dados["fortalezas"]) > 1 else None
        detalhe_top = f"{top['nome']} domina com {top['taxa_acerto']}% de acerto em {top['questoes']} questões"
        if seg:
            detalhe_top += f", seguido por {seg['nome']} com {seg['taxa_acerto']}% ({seg['questoes']} questões)"
        pontos_analise.append(
            f"Competitividade & Corte: Taxa global de {taxa}% ({comp_corte_resumo}). {detalhe_top}; ritmo seguro para a linha de corte."
        )
    else:
        pontos_analise.append(
            f"Competitividade & Corte: Taxa global em {taxa}%. Intensifique baterias para consolidar percentual acima de {corte}%."
        )

    # Ponto 2: Gargalos e Vulnerabilidades
    if dados["gargalos"]:
        critico = dados["gargalos"][0]
        pontos_analise.append(
            f"Gargalo Crítico de Prova: {critico['nome']} registra {critico['taxa_acerto']}% de acerto em {critico['questoes']} itens — ponto de máxima vulnerabilidade no modelo {banca} (questões erradas penalizam acertos)."
        )
    elif dados["sem_questoes"]:
        sem_q = dados["sem_questoes"][0]
        pontos_analise.append(
            f"Atenção a Disciplinas Ocultas: {sem_q['nome']} acumula horas de teoria mas nenhuma questão registrada. Aplicação de teoria sem teste gera falsa sensação de domínio."
        )
    else:
        pontos_analise.append(
            f"Vulnerabilidades & Erros: Mantenha caderno de erros ativo em todas as disciplinas com aproveitamento limítrofe."
        )

    # Ponto 3: Ritmo e Projeção até a Prova
    if dias > 0:
        media_bruta = round(total_horas / total_dias, 1) if total_dias > 0 else 2.5
        # Ritmo sustentável de concurso (entre 2h e 5h diárias para projeção realista)
        ritmo_proj = min(max(media_bruta, 2.0), 4.5)
        horas_semana_est = round(ritmo_proj * 6, 1)
        questoes_por_hora = (total_questoes / total_horas) if total_horas > 0 else 8.0
        questoes_proj = int(questoes_por_hora * ritmo_proj * dias)
        pontos_analise.append(
            f"Volume & Cadência na Fase '{zona}': Restam {dias} dias. Em ritmo recomendado de {ritmo_proj}h/dia (~{horas_semana_est}h/semana), a projeção é resolver cerca de {questoes_proj} questões da banca {banca} até o dia da prova."
        )
    else:
        pontos_analise.append(
            f"Fase de Prova Concluída: Registre seu gabarito e pontuações na aba Resultados & Raio-X."
        )

    # Ponto 4: Direcionamento do Coach
    if dados["gargalos"]:
        foco_coach = dados["gargalos"][0]["nome"]
        pontos_analise.append(
            f"Direcionamento do Coach: Dedique 2 a 3 blocos prioritários desta semana exclusivamente para bateria comentada em {foco_coach}, aliando revisão ativa no Anki para decorebas da banca {banca}."
        )
    else:
        pontos_analise.append(
            f"Direcionamento do Coach: Acelere resolução cronometrada em blocos mistos para treinar gestão de tempo e resistência mental para a banca {banca}."
        )

    agora = datetime.now()
    return {
        "titulo": "INSIGHTS DE IA",
        "subtitulo": "Leitura dos indicadores a cada hora ou ao atualizar",
        "resumo_executivo": resumo_executivo,
        "pontos_analise": pontos_analise,
        "modelo_origem": "Coach IA Orbis",
        "timestamp": agora.strftime("%H:%M"),
        "data_atualizacao": agora.isoformat()
    }

async def tentar_gerar_com_gemini(dados: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None

    prompt = f"""Você é o Coach de Estudos e Mentor Estratégico Especialista em Concursos Públicos do app Orbis.
Analise com rigor técnico os dados reais deste candidato e produza um diagnóstico executivo com direcionamento tático preciso.

DADOS REAIS DO CANDIDATO:
- Concurso Alvo: {dados['concurso']}
- Cargo: {dados['cargo']}
- Banca Examinadora: {dados['banca']} (Estilo: {dados['estilo_banca']})
- Dias Restantes para a Prova: {dados['dias_restantes']} dias (Zona: {dados['zona_tag']} - {dados['zona_fase']})
- Nota de Corte Alvo: {dados['nota_corte']}%
- Total Horas Estudadas: {dados['total_horas']}h em {dados['total_dias_estudados']} dias estudados ({dados['total_sessoes']} sessões)
- Total Questões Resolvidas: {dados['total_questoes']} ({dados['total_acertos']} acertos, {dados['total_erros']} erros)
- Taxa Geral de Acerto: {dados['taxa_global']}% (Diferença para o corte: {dados['diff_corte']} p.p.)
- Voltas no Ciclo: {dados['voltas_ciclo']}

DESEMPENHO POR DISCIPLINA:
{json.dumps(dados['disciplinas'], indent=2, ensure_ascii=False)}

RETORNE ESTRITAMENTE UM JSON NO SEGUINTE FORMATO (SEM NENHUM TEXTO ADICIONAL):
{{
  "resumo_executivo": "Parágrafo executivo em tom de coach profissional, direto e assertivo, destacando os números-chave, o tempo até a prova, o comparativo com a nota de corte e as prioridades.",
  "pontos_analise": [
    "Primeiro bullet: análise quantitativa de desempenho e competitividade frente à banca e corte.",
    "Segundo bullet: gargalos críticos ou disciplinas com baixo rendimento ou sem questões (com dados numéricos).",
    "Terceiro bullet: ritmo, projeção de horas e questões até a data da prova considerando os dias restantes.",
    "Quarto bullet: direcionamento tático e plano de ação imediato para esta semana."
  ]
}}"""

    try:
        # Tenta utilizar o novo google-genai
        from google import genai
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
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
            "subtitulo": "Leitura dos indicadores a cada hora ou ao atualizar",
            "resumo_executivo": parsed.get("resumo_executivo"),
            "pontos_analise": parsed.get("pontos_analise", []),
            "modelo_origem": "Gemini 2.5 Flash",
            "timestamp": agora.strftime("%H:%M"),
            "data_atualizacao": agora.isoformat()
        }
    except Exception as e:
        print(f"Tentativa com google-genai falhou: {e}. Tentando fallback...")
        try:
            import google.generativeai as legacy_genai
            legacy_genai.configure(api_key=api_key)
            model = legacy_genai.GenerativeModel("gemini-1.5-flash")
            response = model.generate_content(prompt)
            texto = response.text.strip()
            if texto.startswith("```json"):
                texto = texto[7:]
            if texto.endswith("```"):
                texto = texto[:-3]
            parsed = json.loads(texto.strip())
            agora = datetime.now()
            return {
                "titulo": "INSIGHTS DE IA",
                "subtitulo": "Leitura dos indicadores a cada hora ou ao atualizar",
                "resumo_executivo": parsed.get("resumo_executivo"),
                "pontos_analise": parsed.get("pontos_analise", []),
                "modelo_origem": "Gemini 1.5 Flash",
                "timestamp": agora.strftime("%H:%M"),
                "data_atualizacao": agora.isoformat()
            }
        except Exception as e2:
            print(f"Fallback Gemini falhou: {e2}")
            return None

@router.get("/insights")
async def obter_insights_ia(db: Session = Depends(get_db)):
    config = db.query(ConfiguracaoPainelProva).first()
    if not config:
        config = ConfiguracaoPainelProva(id=1)
        db.add(config)
        db.commit()
        db.refresh(config)

    # Verifica cache existente (menos de 60 minutos)
    agora = datetime.now()
    if config.ultimo_insight_ia and config.data_insight_ia:
        delta = (agora - config.data_insight_ia).total_seconds()
        if delta < 3600:  # menos de 1 hora
            try:
                dados_cache = json.loads(config.ultimo_insight_ia)
                return dados_cache
            except Exception:
                pass

    # Gerar nova análise
    dados_estudo = calcular_dados_estudo(db)
    insight = await tentar_gerar_com_gemini(dados_estudo)
    if not insight:
        insight = gerar_insight_heuristico(dados_estudo)

    # Salva no cache da tabela
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
    insight = await tentar_gerar_com_gemini(dados_estudo)
    if not insight:
        insight = gerar_insight_heuristico(dados_estudo)

    config.ultimo_insight_ia = json.dumps(insight, ensure_ascii=False)
    config.data_insight_ia = agora
    db.commit()

    return insight
