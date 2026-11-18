import os
import re
import json
import asyncio
import httpx
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session

from app.models.edital import Edital
from app.models.disciplina import Disciplina
from app.models.topico import Topico
from app.models.ciclo import CicloEstudos, BlocoCiclo
from app.models.sessao import SessaoEstudo
from app.models.configuracao_prova import ConfiguracaoPainelProva
from app.routers.ia_insights import (
    MODELOS_GEMINI_ATIVOS,
    extrair_json_resiliente,
    selecionar_modelos_gemini_rapidos,
    rebaixar_modelo_gemini_cache,
    remover_modelo_gemini_cache,
)


def extrair_chave_numerica_titulo(titulo: str) -> Tuple[List[int], str]:
    """
    Extrai a numeração hierárquica natural do início do título do tópico
    (ex: '10.4.1 Lei...' -> ([10, 4, 1], 'Lei...')) para corrigir ordenações
    lexicográficas ('1', '10', '2') e identificar tópicos introdutórios/base.
    """
    if not titulo:
        return ([999999], "")
    t = titulo.strip()
    m = re.match(r"^(\d+(?:\.\d+)*)\.?\s+(.*)$", t)
    if m:
        partes = [int(p) for p in m.group(1).split(".") if p.isdigit()]
        return (partes, m.group(2).strip())
    return ([999999], t)


def normalizar_ordem_natural_topicos(disciplina: Disciplina) -> List[Topico]:
    """
    Garante que o campo `ordem` dos tópicos reflita a numeração natural do edital
    (1, 1.1, 1.2, 2, ..., 10, 10.1) em vez da ordem alfabética ASCII (1, 10, 2).
    """
    if not disciplina.topicos:
        return []

    tem_numeracao = sum(
        1 for t in disciplina.topicos
        if extrair_chave_numerica_titulo(t.titulo)[0][0] != 999999
    )

    if tem_numeracao >= max(2, len(disciplina.topicos) // 2):
        ordenados = sorted(
            disciplina.topicos,
            key=lambda t: (extrair_chave_numerica_titulo(t.titulo)[0], t.id or 0)
        )
    else:
        ordenados = sorted(
            disciplina.topicos,
            key=lambda t: (t.ordem if t.ordem is not None else 0, t.id or 0)
        )

    for idx, topico in enumerate(ordenados):
        topico.ordem = idx

    return ordenados


# ==============================================================================
# BASE DE CONHECIMENTO PEDAGÓGICA (PRÉ-REQUISITOS) & PARETO 80/20 POR DISCIPLINA
# ==============================================================================
MAPA_DISCIPLINAS_CONHECIMENTO: List[Dict[str, Any]] = [
    {
        "chaves": ["CONSTITUCIONAL"],
        "nivel_pedagogico": 1,  # Nível 1 = Base Fundamental / Pré-requisito Primário
        "peso_pareto_base": 90,
        "pre_requisitos": "Base Jurídica Primária → Pré-requisito direto para Direito Tributário, Reforma Tributária, Direito Administrativo e Finanças Públicas",
        "justificativa_padrao": "Eixo estruturante do Direito Público. O domínio de Competências Constitucionais, Processo Legislativo, Ordem Econômica/Financeira e Sistema Tributário destrava o aprendizado de Direito Tributário e Reforma Tributária (EC 132/2023)."
    },
    {
        "chaves": ["ADMINISTRATIVO"],
        "nivel_pedagogico": 1,
        "peso_pareto_base": 88,
        "pre_requisitos": "Base Jurídica Primária → Pré-requisito para Processo Administrativo Tributário, Auditoria Fiscal e Governança/Contratos de TI",
        "justificativa_padrao": "Fornece os conceitos de Atos Administrativos, Poderes, Agentes e Lei 14.133/2021 (Licitações e Contratos). É pré-requisito para compreender lançamentos fiscais, fiscalização de contratos de TI e processo administrativo."
    },
    {
        "chaves": ["MATEMATICA FINANCEIRA", "MATEMÁTICA FINANCEIRA", "RACIOCINIO LOGICO", "RACIOCÍNIO LÓGICO"],
        "nivel_pedagogico": 1,
        "peso_pareto_base": 82,
        "pre_requisitos": "Base Quantitativa Primária → Pré-requisito para Contabilidade Geral, Economia, Finanças Públicas e Auditoria Fiscal",
        "justificativa_padrao": "Fundamento matemático essencial. Taxas efetivas/equivalentes, juros compostos, descontos e sistemas de amortização (SAC/Price) são pré-requisitos para avaliação de ativos/passivos em Contabilidade e análise econômica."
    },
    {
        "chaves": ["ESTATISTICA", "ESTATÍSTICA"],
        "nivel_pedagogico": 1,
        "peso_pareto_base": 86,
        "pre_requisitos": "Base Analítica Primária → Pré-requisito direto para Ciência de Dados, Inteligência Artificial e Amostragem em Auditoria",
        "justificativa_padrao": "Pilar matemático indispensável para TI e Fisco moderno: Estatística Descritiva, Probabilidade, Inferência e Regressão são pré-requisitos obrigatórios para compreender Machine Learning, Ciência de Dados e cruzamento de malhas fiscais."
    },
    {
        "chaves": ["CONTABILIDADE GERAL"],
        "nivel_pedagogico": 1,
        "peso_pareto_base": 89,
        "pre_requisitos": "Base Contábil Primária → Pré-requisito obrigatório para Contabilidade Pública e Auditoria Fiscal (EFD/SPED)",
        "justificativa_padrao": "Sem dominar Patrimônio, Fatos Contábeis, Escrituração, CPCs, Balanço Patrimonial e DRE, é impossível avançar com solidez em Contabilidade Pública (PCASP/DCASP) ou em Auditoria Fiscal (omissão de receitas e EFD)."
    },
    {
        "chaves": ["PORTUGUES", "PORTUGUÊS", "LINGUA PORTUGUESA", "LÍNGUA PORTUGUESA"],
        "nivel_pedagogico": 1,
        "peso_pareto_base": 85,
        "pre_requisitos": "Base Instrumental Universal → Auxilia interpretação de enunciados complexos e prova discursiva",
        "justificativa_padrao": "Disciplina de altíssimo retorno na Regra de Pareto: compreensão textual, reescrita e sintaxe garantem pontos preciosos e blindam contra armadilhas semânticas da banca."
    },
    {
        "chaves": ["TRIBUTARIO", "TRIBUTÁRIO"],
        "nivel_pedagogico": 2,  # Nível 2 = Núcleo Estruturante (depende do Nível 1 e destrava o Nível 3)
        "peso_pareto_base": 96,
        "pre_requisitos": "Requer base de: Direito Constitucional e Administrativo → Pré-requisito direto para: Reforma Tributária, Legislação Tributária Estadual e Auditoria Fiscal",
        "justificativa_padrao": "Coração jurídico da prova fiscal. Limitações ao poder de tributar, obrigação, fato gerador, lançamento, crédito tributário (CTN) e responsabilidade tributária são pré-requisitos absolutos para Reforma Tributária e ICMS/IPVA/ITCD."
    },
    {
        "chaves": ["ECONOMIA"],
        "nivel_pedagogico": 2,
        "peso_pareto_base": 80,
        "pre_requisitos": "Requer base de: Matemática Financeira → Pré-requisito direto para: Finanças Públicas e Tributação Econômica",
        "justificativa_padrao": "A compreensão de Microeconomia (elasticidades, estruturas de mercado) e Macroeconomia (contas nacionais, política fiscal/monetária) fornece a base conceitual imediata para Finanças Públicas e incidência econômica dos tributos."
    },
    {
        "chaves": ["CONTABILIDADE PUBLICA", "CONTABILIDADE PÚBLICA"],
        "nivel_pedagogico": 2,
        "peso_pareto_base": 91,
        "pre_requisitos": "Requer base de: Contabilidade Geral → Conecta-se com: Finanças Públicas (PPA/LDO/LOA) e Auditoria",
        "justificativa_padrao": "Altíssima incidência na banca. Estuda-se logo após a base de Contabilidade Geral, focando nos 20% mais cobrados: Variações Patrimoniais (VPA/VPD), Procedimentos Contábeis Orçamentários, Restos a Pagar, DEA, PCASP e DCASP (MCASP)."
    },
    {
        "chaves": ["FINANCAS PUBLICAS", "FINANÇAS PÚBLICAS", "ORCAMENTO", "ORÇAMENTO", "AFO"],
        "nivel_pedagogico": 2,
        "peso_pareto_base": 92,
        "pre_requisitos": "Requer base de: Constitucional e Economia → Complementa: Contabilidade Pública e Reforma Tributária",
        "justificativa_padrao": "Núcleo clássico de provas fiscais: Funções do Estado (Musgrave), Falhas de Mercado, Orçamento Público (PPA, LDO, LOA), Princípios Orçamentários, Estágios da Receita/Despesa, Créditos Adicionais e LRF (LC 101/2000)."
    },
    {
        "chaves": ["DESENVOLVIMENTO DE SISTEMAS", "ENGENHARIA DE SOFTWARE"],
        "nivel_pedagogico": 2,
        "peso_pareto_base": 87,
        "pre_requisitos": "Base de TI & Engenharia → Pré-requisito para Arquitetura de Dados, Segurança de Aplicações e Auditoria de Sistemas",
        "justificativa_padrao": "Forma a base de Engenharia de Software para TI: Scrum/Kanban, BPMN, Arquitetura de Microsserviços, APIs REST, Padrões de Projeto e DevSecOps/OWASP, preparando o terreno para Infraestrutura e Ciência de Dados."
    },
    {
        "chaves": ["INFRAESTRUTURA DE TIC", "SEGURANCA DA INFORMACAO", "SEGURANÇA DA INFORMAÇÃO", "REDES"],
        "nivel_pedagogico": 2,
        "peso_pareto_base": 93,
        "pre_requisitos": "Base de Arquitetura & Segurança → Auxilia Ciência de Dados (Cloud/Big Data) e Auditoria Fiscal Digital (ICP-Brasil/Assinatura)",
        "justificativa_padrao": "Uma das disciplinas mais cobradas pela banca em cargos de TI: Cloud Computing (IaaS/PaaS/SaaS, Kubernetes), DevSecOps, ITIL v4, Forense Computacional, Zero Trust, Gestão de Riscos (ISO 27001/27005) e Certificação Digital (ICP-Brasil)."
    },
    {
        "chaves": ["CIENCIA DE DADOS", "CIÊNCIA DE DADOS", "BANCO DE DADOS", "DADOS"],
        "nivel_pedagogico": 2,
        "peso_pareto_base": 99,
        "pre_requisitos": "Requer base de: Estatística e Probabilidade → Pré-requisito direto para: Inteligência Artificial e Cruzamento de Dados em Auditoria Fiscal",
        "justificativa_padrao": "Maior peso relativo da prova específica (Pareto #1 de TI): Modelagem Relacional e Dimensional (Star/Snowflake), SQL Avançado, ETL/Data Warehouse, CRISP-DM, Mineração de Dados e fundamentos de Machine Learning."
    },
    {
        "chaves": ["REFORMA TRIBUTARIA", "REFORMA TRIBUTÁRIA"],
        "nivel_pedagogico": 3,  # Nível 3 = Especialização Avançada de Alto Peso (depende da base Nível 1 e 2)
        "peso_pareto_base": 98,
        "pre_requisitos": "Requer base de: Direito Constitucional e Direito Tributário → Conecta-se com: Legislação Tributária Estadual e Auditoria Fiscal",
        "justificativa_padrao": "Disciplina de altíssimo valor estratégico (15 questões). Com a base de Direito Tributário consolidada, o estudo foca em EC 132/2023, LC 214/2025, IBS/CBS/Imposto Seletivo, Princípio do Destino, Não Cumulatividade Plena, Split Payment e Comitê Gestor."
    },
    {
        "chaves": ["LEGISLACAO TRIBUTARIA", "LEGISLAÇÃO TRIBUTÁRIA"],
        "nivel_pedagogico": 3,
        "peso_pareto_base": 90,
        "pre_requisitos": "Requer base de: Direito Tributário (CTN) → Pré-requisito direto para: Auditoria Fiscal (ICMS/EFD/NF-e)",
        "justificativa_padrao": "Aplicação direta do Direito Tributário aos tributos estaduais: Lei do ICMS (fato gerador, base de cálculo, substituição tributária, não cumulatividade), IPVA, ITCD e Processo Administrativo Tributário (PAT)."
    },
    {
        "chaves": ["AUDITORIA FISCAL", "AUDITORIA"],
        "nivel_pedagogico": 3,
        "peso_pareto_base": 97,
        "pre_requisitos": "Requer base de: Contabilidade Geral, Direito Tributário e Legislação Estadual → Síntese prática da função de Auditor Fiscal",
        "justificativa_padrao": "Disciplina-fim de altíssimo peso (15 questões). Une Contabilidade, Tributário e TI na prática fiscal: SPED, NF-e/NFC-e (MOC), EFD ICMS/IPI, CFOP/CST/cBenef, cruzamento de malhas eletrônicas e auditoria de omissão de receitas."
    },
    {
        "chaves": ["INTELIGENCIA ARTIFICIAL", "INTELIGÊNCIA ARTIFICIAL"],
        "nivel_pedagogico": 3,
        "peso_pareto_base": 89,
        "pre_requisitos": "Requer base de: Estatística e Ciência de Dados (Machine Learning) → Tópico avançado de TI",
        "justificativa_padrao": "Evolução direta de Ciência de Dados: Redes Neurais, Deep Learning, Processamento de Linguagem Natural (NLP), LLMs/Transformers, RAG e IA Generativa, temas em altíssima evidência nas provas recentes da banca."
    }
]


def diagnosticar_disciplina_trilha(disc: Disciplina, banca: str) -> Dict[str, Any]:
    """
    Avalia a disciplina combinando:
    1) Nível pedagógico (Pré-requisitos que destravam outras matérias)
    2) Peso e número de questões na prova (Regra de Pareto 80/20)
    3) Perfil histórico da banca examinadora
    """
    nome_upper = (disc.nome or "").upper()
    peso = float(disc.peso_prova or 1.0)
    questoes = int(disc.qtd_questoes_prova or 10)
    dificuldade = int(disc.relevancia_dificuldade or 3)
    qtd_topicos = len(disc.topicos) if disc.topicos else 1

    info_match = None
    for item in MAPA_DISCIPLINAS_CONHECIMENTO:
        if any(k in nome_upper for k in item["chaves"]):
            info_match = item
            break

    if info_match:
        nivel_pedagogico = info_match["nivel_pedagogico"]
        peso_pareto_base = info_match["peso_pareto_base"]
        pre_req = info_match["pre_requisitos"]
        justificativa = f"[{banca} • Pareto 80/20] {info_match['justificativa_padrao']}"
    else:
        nivel_pedagogico = 1 if disc.grupo_conhecimento == "BASICOS" else 2
        peso_pareto_base = 80
        pre_req = (
            "Base Conceitual do Ciclo → Fundamenta a progressão nos tópicos avançados do edital"
            if disc.grupo_conhecimento == "BASICOS"
            else "Disciplina Específica do Cargo → Consolida a pontuação decisiva na prova"
        )
        justificativa = (
            f"[{banca} • Pareto 80/20] Disciplina estruturada na trilha combinando progressão de pré-requisitos "
            f"e peso de prova ({questoes} questões estimadas)."
        )

    # Score híbrido para ordenar na Trilha:
    # Queremos intercalar/ordenar de modo que:
    # - As disciplinas-base de altíssimo impacto e pré-requisito venham logo no início da trilha,
    # - Seguidas imediatamente pelas disciplinas de altíssimo peso (Pareto) que dependem delas!
    score_pareto_prova = (questoes * 3.5) + (peso * 15.0) + (dificuldade * 3.0) + (peso_pareto_base * 0.6)
    # Penalidade leve por nível pedagógico mais avançado para garantir que pré-requisitos diretos venham antes
    score_trilha = score_pareto_prova - ((nivel_pedagogico - 1) * 14.0)

    return {
        "nivel_pedagogico": nivel_pedagogico,
        "score_pareto_prova": round(score_pareto_prova, 2),
        "score_trilha": round(score_trilha, 2),
        "pre_requisitos_ia": pre_req,
        "justificativa_trilha_ia": justificativa
    }


# ==============================================================================
# HEURÍSTICA ESPECIALISTA DE TÓPICOS (PARETO 80/20 + PRÉ-REQUISITOS + BANCA)
# ==============================================================================
TERMOS_ALTA_INCIDENCIA_PARETO = [
    # Direito Constitucional & Administrativo
    "controle de constitucionalidade", "súmula vinculante", "direitos e garantias",
    "direitos e deveres", "administração pública", "organização político-administrativa",
    "processo legislativo", "fiscalização contábil", "ordem econômica", "finanças públicas",
    "ato administrativo", "anulação, revogação e convalidação", "poderes administrativos",
    "poder de polícia", "agentes públicos", "processo administrativo", "licitações e contratos",
    "14.133", "improbidade", "8.429", "responsabilidade civil", "controle da administração",
    "serviços públicos", "organização administrativa",
    # Direito Tributário, Reforma Tributária e Legislação Estadual
    "sistema tributário nacional", "princípios", "limitações do poder de tributar",
    "imunidades", "competência tributária", "obrigação tributária", "fato gerador",
    "responsabilidade tributária", "crédito tributário", "lançamento", "suspensão",
    "extinção", "exclusão", "administração tributária", "dívida ativa", "certidões",
    "icms", "ipva", "itcd", "processo administrativo tributário", "132/2023",
    "214/2025", "ibs", "cbs", "imposto seletivo", "princípio do destino",
    "não cumulatividade", "split payment", "comitê gestor", "transição", "cashback",
    # Contabilidade Geral, Pública e Finanças Públicas
    "patrimônio", "fatos administrativos", "fatos permutativos", "escrituração",
    "balanço patrimonial", "demonstração de resultado", "dre", "ativo", "passivo",
    "variações patrimoniais", "pcasp", "dcasp", "balanço orçamentário", "balanço financeiro",
    "restos a pagar", "despesas de exercícios anteriores", "suprimento de fundos",
    "receita orçamentária", "despesa orçamentária", "estágios", "créditos adicionais",
    "ppa", "ldo", "loa", "princípios orçamentários", "lei complementar nº 101",
    "responsabilidade fiscal", "lrf", "funções do estado", "alocativa", "distributiva",
    "estabilizadora", "falhas de mercado", "bens públicos", "externalidades",
    # Auditoria Fiscal
    "sped", "nf-e", "nfc-e", "efd icms/ipi", "cfop", "cst", "cbenef",
    "cruzamento", "omissão de receitas", "créditos indevidos", "divergências",
    # TI, Ciência de Dados e IA
    "bancos de dados relacionais", "modelagem relacional", "dimensional", "multidimensional",
    "sql", "crisp-dm", "pré-processamento", "mineração de dados", "classificação",
    "regressão", "clusterização", "aprendizado de máquina", "machine learning",
    "big data", "business intelligence", "coleta, tratamento", "redes neurais",
    "deep learning", "processamento de linguagem natural", "llm", "generativa",
    "scrum", "kanban", "metodologias ágeis", "arquitetura", "microsserviços",
    "api", "rest", "devsecops", "devops", "owasp", "segurança", "nuvem",
    "iaas, paas, saas", "docker", "kubernetes", "itil", "forense", "cadeia de custódia",
    "zero trust", "gestão de identidade", "gestão de riscos", "vulnerabilidades",
    "chaves públicas", "certificação digital", "incidentes",
    # Exatas, Matemática Financeira, Estatística e Economia
    "juros simples e compostos", "taxas de juros", "efetiva", "equivalente",
    "amortização", "price", "sac", "estatística descritiva", "medidas descritivas",
    "probabilidade", "inferência", "hipóteses", "correlação", "oferta e demanda",
    "elasticidades", "contas nacionais", "política fiscal", "política monetária"
]

TERMOS_BASE_PRE_REQUISITO = [
    "conceito", "conceitos", "conceituação", "fundamentos", "princípios",
    "introdução", "disposições gerais", "objeto", "definições básicas",
    "estrutura", "sistema tributário", "patrimônio", "juros simples",
    "estatística descritiva", "dado, informação", "bancos de dados relacionais",
    "emenda constitucional nº 132", "lei complementar nº 214", "sped",
    "lei estadual nº 5.900", "constituição da república", "estado, governo"
]


def classificar_topicos_disciplina_heuristica(
    disc: Disciplina,
    banca: str,
    sessoes_por_topico: Dict[int, Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Analisa todos os tópicos de uma disciplina aplicando:
    1) Detecção de Tópicos-Base (Pré-requisitos que devem ser estudados primeiro na disciplina)
    2) Regra de Pareto 80/20 (Os ~25-30% tópicos mais cobrados pela banca recebem Mais Cobrado 🔥 e P1 ⚡)
    3) Sequenciamento didático (`ordem_trilha`):
       - 1º: Tópicos P1 que são Pré-requisito/Base da matéria
       - 2º: Tópicos P1 de altíssima incidência na banca (Núcleo Pareto 80/20)
       - 3º: Tópicos P2 (Importância intermediária / Consolidação)
       - 4º: Tópicos P3 (Complementares da trilha)
       - 5º: Demais tópicos na ordem natural do edital
    """
    topicos_ordenados = normalizar_ordem_natural_topicos(disc)
    n = len(topicos_ordenados)
    if n == 0:
        return []

    avaliacoes = []
    for idx, t in enumerate(topicos_ordenados):
        titulo_lower = (t.titulo or "").lower()
        partes_num, texto_limpo = extrair_chave_numerica_titulo(t.titulo or "")
        profundidade_topico = len(partes_num) if partes_num[0] != 999999 else 1
        num_principal = partes_num[0] if partes_num[0] != 999999 else (idx + 1)

        # Verifica se é tópico base/fundamento (pré-requisito interno da disciplina)
        eh_base = (
            idx == 0
            or num_principal in (1, 2)
            or any(tb in titulo_lower for tb in TERMOS_BASE_PRE_REQUISITO)
        )

        # Conta quantos termos de alta incidência Pareto aparecem no título
        hits_pareto = sum(1 for termo in TERMOS_ALTA_INCIDENCIA_PARETO if termo in titulo_lower)

        # Posição relativa no edital e especificidade
        score_incidencia = (hits_pareto * 28.0)
        if eh_base:
            score_incidencia += 22.0
        if profundidade_topico == 1:
            score_incidencia += 12.0
        elif profundidade_topico == 2:
            score_incidencia += 8.0

        # Bônus se o aluno já fez questões e errou (gargalo real identificado)
        stats_top = sessoes_por_topico.get(t.id)
        teve_gargalo = False
        if stats_top and stats_top.get("questoes", 0) >= 5:
            taxa_t = stats_top["acertos"] / stats_top["questoes"] * 100.0
            if taxa_t < 72.0:
                score_incidencia += 25.0
                teve_gargalo = True

        # Determinismo fino baseado na posição para desempatar com consistência
        score_incidencia += max(0.0, (n - idx) / max(1.0, float(n)) * 10.0)

        avaliacoes.append({
            "topico": t,
            "idx_edital": idx,
            "num_principal": num_principal,
            "eh_base": eh_base,
            "hits_pareto": hits_pareto,
            "teve_gargalo": teve_gargalo,
            "score": score_incidencia
        })

    # Ordena por score decrescente para definir os cortes de Pareto (80/20)
    ranking_score = sorted(avaliacoes, key=lambda x: (-x["score"], x["idx_edital"]))

    # Proporções da Regra de Pareto 80/20:
    # - P1 (Alta Prioridade / Núcleo Pareto + Base): ~24% dos tópicos (mínimo 1, ou 2 se n >= 4)
    # - Mais Cobrados (🔥): ~26% dos tópicos (os de maior incidência na banca)
    # - P2 (Média Prioridade / Consolidação): próximos ~24% dos tópicos
    # - P3 (Baixa Prioridade / Complementar): próximos ~20% dos tópicos
    # - Sem Prioridade (Residual): ~32% restantes (em matérias grandes)
    qtd_p1 = max(1, min(n, int(round(n * 0.25))))
    if n >= 5 and qtd_p1 < 2:
        qtd_p1 = 2
    qtd_mc = max(1, min(n, int(round(n * 0.26))))
    qtd_p2 = max(1 if n >= 3 else 0, min(max(0, n - qtd_p1), int(round(n * 0.25))))
    qtd_p3 = max(1 if n >= 6 else 0, min(max(0, n - qtd_p1 - qtd_p2), int(round(n * 0.20))))

    ids_p1 = set(x["topico"].id for x in ranking_score[:qtd_p1])
    ids_p2 = set(x["topico"].id for x in ranking_score[qtd_p1:qtd_p1 + qtd_p2])
    ids_p3 = set(x["topico"].id for x in ranking_score[qtd_p1 + qtd_p2:qtd_p1 + qtd_p2 + qtd_p3])

    # Para Mais Cobrados, priorizamos os de maior hits_pareto + score
    ranking_mc = sorted(
        avaliacoes,
        key=lambda x: (-(x["hits_pareto"] * 35.0 + x["score"]), x["idx_edital"])
    )
    ids_mc = set(x["topico"].id for x in ranking_mc[:qtd_mc])

    # Garante que o tópico introdutório/base #1 de toda disciplina seja no mínimo P1 ou P2
    # para que o aluno nunca comece a matéria por um tópico avançado sem base!
    primeiro_item = avaliacoes[0]
    if primeiro_item["topico"].id not in ids_p1:
        ids_p1.add(primeiro_item["topico"].id)
        ids_p2.discard(primeiro_item["topico"].id)
        ids_p3.discard(primeiro_item["topico"].id)

    # Agora construímos a Trilha de Aprendizado dentro da disciplina:
    # Dentro de P1, os tópicos que são Pré-requisito/Base vêm na ordem natural do edital PRIMEIRO,
    # seguidos pelos demais P1 na ordem natural, depois P2, depois P3, depois os demais!
    for av in avaliacoes:
        tid = av["topico"].id
        mc = tid in ids_mc
        if tid in ids_p1:
            pri = 1
        elif tid in ids_p2:
            pri = 2
        elif tid in ids_p3:
            pri = 3
        else:
            pri = None

        av["prioridade"] = pri
        av["mais_cobrado"] = mc

        # Define a faixa de ordenação na Trilha de Aprendizado:
        # Faixa 1: P1 que é Base/Pré-requisito (aprender os fundamentos essenciais primeiro!)
        # Faixa 2: P1 de Alta Incidência Pareto (focar no que mais cai logo após a base!)
        # Faixa 3: Mais Cobrado com P2
        # Faixa 4: Demais P2 (consolidação intermediária)
        # Faixa 5: P3 (complementares)
        # Faixa 6: Residual (baixa incidência histórica na banca)
        # Faixas da Trilha seguindo a Regra de Ouro:
        # Faixa 1: Tópico-Base e Pré-requisito estrito (estudo inicial indispensável)
        # Faixa 2: PREFERÊNCIA 01 = Mais Cobrados P1 (o núcleo que mais cai na banca!)
        # Faixa 3: Mais Cobrados P2 (se houver)
        # Faixa 4: Demais tópicos P1 (alta relevância)
        # Faixa 5: Tópicos P2 (média relevância / consolidação)
        # Faixa 6: Tópicos P3 (baixa relevância / complementares)
        # Faixa 7: Sem prioridade / Residual por último
        if pri == 1 and av["eh_base"] and not mc:
            faixa_trilha = 1
        elif mc and pri == 1:
            faixa_trilha = 2
        elif mc:
            faixa_trilha = 3
        elif pri == 1:
            faixa_trilha = 4
        elif pri == 2:
            faixa_trilha = 5
        elif pri == 3:
            faixa_trilha = 6
        else:
            faixa_trilha = 7

        av["faixa_trilha"] = faixa_trilha

        # Gera a explicação pedagógica + Pareto da IA para o tópico
        titulo_curto = (t.titulo or "")[:45]
        if av["teve_gargalo"] and pri == 1:
            motivo = f"🚨 Gargalo detectado ({titulo_curto}) + Núcleo Pareto {banca}: priorizar teoria e bateria urgente."
        elif pri == 1 and av["eh_base"] and mc:
            motivo = f"🔥 Base Estruturante & Top Pareto {banca}: conceito fundamental indispensável para o cargo."
        elif pri == 1 and av["eh_base"]:
            motivo = f"🧱 Tópico-Base e Pré-requisito: estude primeiro para destravar a compreensão dos temas seguintes."
        elif pri == 1 and mc:
            motivo = f"🔥 Núcleo Pareto 80/20 ({banca}): altíssima incidência histórica nas provas do cargo."
        elif pri == 1:
            motivo = f"⚡ Prioridade Alta (P1): tema estruturante de elevado custo-benefício na {banca}."
        elif pri == 2 and mc:
            motivo = f"⭐ Recorrente na {banca} (P2): alta frequência, consolidar logo após os temas P1."
        elif pri == 2 and av["eh_base"]:
            motivo = f"⭐ Conexão Intermediária (P2): fundamenta a transição entre tópicos essenciais."
        elif pri == 2:
            motivo = f"⭐ Consolidação Estratégica (P2): incidência intermediária consistente na {banca}."
        elif pri == 3:
            motivo = f"🔹 Tópico Complementar (P3): menor incidência relativa, indicado para leitura rápida e questões."
        else:
            motivo = f"📋 Tópico Residual: baixa incidência histórica na {banca}; estudar após fechar o núcleo P1/P2."

        av["motivo_ia"] = motivo

    # Ordena para atribuir `ordem_trilha` (1, 2, 3, ..., N) priorizando Pareto dentro de cada faixa
    ordenados_trilha = sorted(
        avaliacoes,
        key=lambda x: (x["faixa_trilha"], -x["score"], x["idx_edital"])
    )

    resultado = []
    for passo_idx, av in enumerate(ordenados_trilha, start=1):
        av["ordem_trilha"] = passo_idx
        resultado.append(av)

    return resultado


async def consultar_gemini_para_trilha(
    api_key: str,
    banca: str,
    estilo_banca: str,
    concurso: str,
    cargo: str,
    especialidade: str,
    disciplinas_info: List[Dict[str, Any]],
    area_concurso: str = "Fiscal",
    formato_prova: str = "160 itens + Discursiva",
    nota_corte: float = 78.5,
    status_edital: str = "Pós-Edital (Edital Publicado)",
    dias_restantes: Optional[int] = None
) -> Optional[Dict[str, Any]]:
    """
    Aciona a IA Google Gemini de forma rápida e enxuta para:
    - Validar e refinar a ordem pedagógica das disciplinas (`ordem_trilha`) considerando pré-requisitos e peso na prova
    - Personalizar `pre_requisitos_ia` e `justificativa_trilha_ia` segundo o perfil da banca cadastrada
    - Gerar o `resumo_estrategico` da Trilha de Aprendizado & Pareto 80/20.
    """
    resumo_discs = [
        {
            "id": d["id"],
            "nome": d["nome"],
            "grupo": d["grupo"],
            "questoes_prova": d["qtd_questoes_prova"],
            "qtd_topicos": len(d["topicos"]),
            "amostra_topicos": [t["titulo"][:65] for t in d["topicos"][:5]]
        }
        for d in disciplinas_info
    ]

    info_tempo = f"{dias_restantes} dias até o exame" if dias_restantes is not None else status_edital
    prompt = f"""Você é o Coordenador Pedagógico e Estrategista Chefe de Concursos Públicos do sistema Orbis.
Sua missão é estruturar a TRILHA DE ESTUDOS VISANDO O APRENDIZADO E A REGRA DE PARETO (80/20),
utilizando estritamente como parâmetros oficiais os dados cadastrados no PAINEL DE PROVA do aluno:

================================================================================
📋 PARÂMETROS OFICIAIS DO PAINEL DE PROVA:
- Concurso / Órgão: {concurso}
- Área do Concurso: {area_concurso} (Ex: Fiscal, Controle, Tribunais, Policial, TI, Administrativa)
- Cargo Alvo: {cargo}
- Especialidade / Foco: {especialidade}
- Banca Examinadora: {banca}
- Estilo e Critério da Banca: {estilo_banca}
- Formato da Prova: {formato_prova}
- Nota de Corte Prevista: {nota_corte}%
- Status do Edital & Horizonte de Tempo: {status_edital} ({info_tempo})
================================================================================

DIRETRIZES DE ANÁLISE:
1. PERFIL DA BANCA ({banca}) & CRITÉRIO ({estilo_banca}):
   - Se for Cebraspe Certo/Errado (1 anula 1): o aluno é apenado por erro; isole os tópicos de jurisprudência pacificada, literalidade e alta recorrência para garantir assertividade sem chutes.
   - Se for Múltipla Escolha (FGV, FCC, etc.): foque nas pegadinhas clássicas da banca, eliminação de distratores e resolução pragmática de casos.
2. ÁREA DO CONCURSO ({area_concurso}) & CARGO ({cargo}):
   - Calibre a prioridade das matérias segundo as exigências da Área {area_concurso}. Na área Fiscal, as matérias tributárias, fiscais, contábeis e de auditoria combinadas com a especialidade formam o núcleo de pontuação decisivo.
3. CONEXÃO PEDAGÓGICA (PRÉ-REQUISITOS) E PARETO (80/20) EM CADA DISCIPLINA:
   - A trilha de estudo é construída DENTRO de cada disciplina.
   - Em cada disciplina, o Passo #1 deve cobrir os fundamentos/pré-requisitos conceituais que destravam o aprendizado dos tópicos seguintes, seguidos imediatamente pelos tópicos de maior recorrência histórica na banca {banca}.
   - Para cada disciplina, gere `pre_requisitos_ia` (máx 120 caracteres) e `justificativa_trilha_ia` (máx 180 caracteres).
4. SÍNTESE ESTRATÉGICA:
   - Escreva um `resumo_estrategico` conciso (3 a 4 linhas) detalhando como a Banca {banca}, o Perfil {estilo_banca} e a Área {area_concurso} direcionam a preparação e o filtro Pareto 80/20.

DISCIPLINAS DO EDITAL:
{json.dumps(resumo_discs, ensure_ascii=False)}

RETORNE ESTRITAMENTE UM JSON VÁLIDO NO FORMATO:
{{
  "resumo_estrategico": "Texto conciso explicando a trilha calibrada pela banca {banca}, perfil {estilo_banca} e área {area_concurso}...",
  "disciplinas": [
    {{
      "id": 1,
      "pre_requisitos_ia": "Conexão pedagógica e pré-requisitos essenciais",
      "justificativa_trilha_ia": "O que mais cai pela banca {banca} na área {area_concurso}"
    }}
  ]
}}"""

    modelos_rest = await selecionar_modelos_gemini_rapidos(api_key, max_modelos=4)
    async with httpx.AsyncClient(timeout=15.0) as http_client:
        for modelo in modelos_rest:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent?key={api_key}"
                payload = {
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "responseMimeType": "application/json",
                        "temperature": 0.2,
                        "thinkingConfig": {"thinkingBudget": 0},
                    }
                }
                resp = await http_client.post(url, json=payload)
                if resp.status_code == 400 and "thinkingConfig" in payload["generationConfig"]:
                    payload["generationConfig"].pop("thinkingConfig", None)
                    resp = await http_client.post(url, json=payload)
                if resp.status_code == 200:
                    resp_json = resp.json()
                    texto = resp_json["candidates"][0]["content"]["parts"][0]["text"].strip()
                    parsed = extrair_json_resiliente(texto)
                    if isinstance(parsed, dict) and "disciplinas" in parsed:
                        parsed["_modelo_usado"] = f"Google Gemini ({modelo})"
                        print(f"[TRILHA IA] Sucesso via Gemini ({modelo})")
                        return parsed
                elif resp.status_code in (401, 403) or "API_KEY_INVALID" in resp.text:
                    print(f"[TRILHA IA] Status {resp.status_code} em {modelo}: {resp.text[:100]}")
                    break
                elif resp.status_code in (404, 429):
                    remover_modelo_gemini_cache(api_key, modelo)
                elif resp.status_code == 503:
                    rebaixar_modelo_gemini_cache(api_key, modelo)
            except Exception as e_rest:
                print(f"[TRILHA IA] Aviso REST com {modelo}: {e_rest}")
                continue

    return None



async def consultar_gemini_topicos_disciplina(
    api_key: str,
    banca: str,
    estilo_banca: str,
    concurso: str,
    cargo: str,
    especialidade: str,
    area_concurso: str,
    disciplina_nome: str,
    topicos_list: List[Dict[str, Any]],
    timeout_segundos: float = 40.0
) -> Optional[List[Dict[str, Any]]]:
    """
    Analisa individualmente TODOS os tópicos de uma disciplina com Gemini:
    - Aplica a Regra de Pareto (80/20) segundo a banca, estilo, área e cargo.
    - Define a sequência pedagógica real de estudo (ordem_trilha: 1..N):
      Passo #1 = Tópico base/pré-requisito que destrava a matéria, seguido imediatamente
      pelos tópicos de maior peso e incidência histórica na banca.
    - Sinaliza 'mais_cobrado': True para o núcleo de alta incidência (aproximadamente 20% a 30%).
    - Define prioridades: 1 (P1 Alta), 2 (P2 Média), 3 (P3 Baixa).
    - Gera justificativa real e contextualizada ('motivo_ia') sem textos genéricos.
    """
    if not topicos_list:
        return []

    prompt = f"""Você é o Estrategista-Chefe de Concursos Públicos do Orbis, especialista absoluto na banca {banca} ({estilo_banca}) para a Área {area_concurso} (concurso {concurso}, cargo {cargo}, especialidade {especialidade}).
Analise todos os tópicos da disciplina "{disciplina_nome}":
{json.dumps(topicos_list, ensure_ascii=False)}

DIRETRIZ ESTRATÉGICA E REGRA DE OURO DA TRILHA DE ESTUDOS:
Analise criticamente o conteúdo real de cada tópico dentro da disciplina "{disciplina_nome}", avaliando a incidência histórica real da banca {banca} ({estilo_banca}) na Área {area_concurso} (cargo {cargo}, especialidade {especialidade}), aplicando a REGRA DE PARETO (80/20) sem se prender à ordem numérica do edital.

HIERARQUIA OBRIGATÓRIA DA SEQUÊNCIA DE ESTUDO (`ordem_trilha`: 1 a {len(topicos_list)}):
1. PRÉ-REQUISITO CONCEITUAL INDISPENSÁVEL (`eh_prerequisito: true`) — APENAS SE HOUVER:
   - Inclua antes dos Mais Cobrados SOMENTE tópicos que sejam estritamente um fundamento conceitual indispensável para compreender e resolver questões dos tópicos Mais Cobrados da disciplina.
   - Se nenhum tópico for pré-requisito indispensável para os temas Mais Cobrados, NÃO force `eh_prerequisito: true` e comece diretamente pelos Mais Cobrados.
   - ATENÇÃO: Nunca confunda "primeiro tópico numérico do edital" ou tópico introdutório genérico com pré-requisito conceitual; tópicos apenas descritivos ou introdutórios sem dependência lógica real devem ir para P2 ou P3.
2. MAIS COBRADOS (`mais_cobrado: true`, `prioridade: 1`):
   - Logo após eventuais pré-requisitos indispensáveis (ou desde o Passo #1 se não houver pré-requisito), posicione o núcleo de maior recorrência e peso histórico na banca {banca} (~20% a 30% dos tópicos que concentram ~80% da pontuação).
3. DEMAIS TÓPICOS P1 (`prioridade: 1`, `mais_cobrado: false`):
   - Tópicos de alta relevância que não compõem o núcleo principal de mais cobrados entram imediatamente após os Mais Cobrados.
4. TÓPICOS P2 — MÉDIOS (`prioridade: 2`):
   - Tópicos de relevância intermediária e consolidação entram após todos os P1.
5. TÓPICOS P3 — BAIXOS (`prioridade: 3`):
   - Tópicos complementares e de baixa incidência na banca {banca} entram após os P2.
6. SEM MARCAÇÃO (`prioridade: null`):
   - Tópicos residuais ou de incidência quase nula na {banca} ficam por último na trilha.

CLASSIFICAÇÃO DE CADA TÓPICO:
- `mais_cobrado`: true se pertencer ao núcleo mais cobrado pela banca {banca} (~20% a 30% dos tópicos).
- `prioridade`: 1 (P1 Alta), 2 (P2 Média), 3 (P3 Baixa), ou null (Residual).
- `eh_prerequisito`: true SOMENTE quando o tópico for base conceitual estritamente indispensável para compreender um ou mais tópicos Mais Cobrados.
- `ordem_trilha`: número sequencial (1 a {len(topicos_list)}) respeitando rigorosamente a ordem: Pré-requisitos (se houver) -> Mais Cobrados -> Demais P1 -> P2 (Médios) -> P3 (Baixos) -> Residuais.
- `motivo_ia`: Justificativa técnica e contextualizada de 1 linha mencionando a {banca} e o papel real do tópico (pré-requisito, alta incidência, médio ou baixo).

Retorne ESTRITAMENTE um JSON no seguinte formato:
{{
  "topicos": [
    {{
      "id": 1,
      "ordem_trilha": 1,
      "prioridade": 1,
      "mais_cobrado": true,
      "eh_prerequisito": false,
      "motivo_ia": "Explicação real, técnica e contextualizada na banca {banca}"
    }}
  ]
}}"""

    modelos_rest = await selecionar_modelos_gemini_rapidos(api_key, max_modelos=3)
    async with httpx.AsyncClient(timeout=min(25.0, timeout_segundos)) as http_client:
        for modelo in modelos_rest:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent?key={api_key}"
                payload = {
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "responseMimeType": "application/json",
                        "temperature": 0.25
                    }
                }
                resp = await http_client.post(url, json=payload)
                if resp.status_code == 200:
                    resp_json = resp.json()
                    texto = resp_json["candidates"][0]["content"]["parts"][0]["text"].strip()
                    if texto.startswith("```json"):
                        texto = texto[7:]
                    if texto.startswith("```"):
                        texto = texto[3:]
                    if texto.endswith("```"):
                        texto = texto[:-3]
                    parsed = json.loads(texto.strip())
                    if isinstance(parsed, dict) and "topicos" in parsed and isinstance(parsed["topicos"], list):
                        return parsed["topicos"]
                elif resp.status_code in (400, 401, 403):
                    print(f"[TRILHA IA TOPICOS] Status {resp.status_code} em {modelo}: {resp.text[:100]}")
                    if "API_KEY_INVALID" in resp.text or resp.status_code in (401, 403):
                        break
            except Exception as e:
                print(f"[TRILHA IA TOPICOS] Erro com {modelo} para {disciplina_nome}: {e}")
                continue

    return None


async def consultar_gemini_lote_disciplinas(
    api_key: str,
    banca: str,
    estilo_banca: str,
    concurso: str,
    cargo: str,
    especialidade: str,
    area_concurso: str,
    disciplinas_lote: List[Dict[str, Any]],
    timeout_segundos: float = 20.0,
) -> Tuple[Optional[Dict[int, Dict[str, Any]]], Optional[str]]:
    """
    Analisa um lote de 1 ou mais disciplinas (até ~95 tópicos no total) em UMA única chamada
    ao Gemini com JSON tabular ultra-compacto `{"t":[[id,ordem,prio,mc,pre]]}`,
    `temperature=0.0` e `thinkingBudget=0`, garantindo:
    - ~5x a 7x menos tokens de saída (~3s por lote de 74-95 tópicos!)
    - Zero timeout e baixíssimo risco de rate-limit (apenas 4 lotes para 369 tópicos)
    - Classificação 100% via IA com determinismo entre execuções
    Retorna (mapa_por_topico_id, nome_modelo_usado).
    """
    if not disciplinas_lote:
        return {}, None

    total_topicos_lote = sum(len(d["topicos"]) for d in disciplinas_lote)
    payload_compacto = [
        {
            "d": d["nome"],
            "n": len(d["topicos"]),
            "mc_alvo": max(1, round(len(d["topicos"]) * 0.22)),
            "t": [[t["id"], t["titulo"]] for t in d["topicos"]],
        }
        for d in disciplinas_lote
    ]

    prompt = f"""Você é o Estrategista-Chefe de Concursos Públicos do Orbis, especialista absoluto na banca {banca} ({estilo_banca}) para a Área {area_concurso} (concurso {concurso}, cargo {cargo}, especialidade {especialidade}).
Analise TODOS os {total_topicos_lote} tópicos das disciplinas abaixo de forma independente por disciplina, aplicando a REGRA DE PARETO (80/20) sem se prender à ordem numérica do edital.

HIERARQUIA OBRIGATÓRIA DENTRO DE CADA DISCIPLINA (ordem de 1 até `n` da disciplina):
1. PRÉ-REQUISITO CONCEITUAL INDISPENSÁVEL (`pre=1`) — APENAS SE HOUVER:
   - Marque `pre=1` SOMENTE se o tópico for estritamente um fundamento conceitual indispensável para compreender e resolver questões dos tópicos Mais Cobrados daquela disciplina.
   - Se nenhum tópico for pré-requisito indispensável, não marque nenhum como `pre=1` e comece diretamente pelos Mais Cobrados.
   - Nunca confunda tópico meramente introdutório ou primeiro item numérico do edital com pré-requisito conceitual.
2. MAIS COBRADOS (`mc=1`, `prio=1`):
   - Em CADA disciplina, selecione exatamente `mc_alvo` tópicos (~22% da disciplina, mínimo 1) que representam os assuntos de maior cobrança histórica real na banca {banca}.
3. DEMAIS TÓPICOS P1 (`prio=1`, `mc=0`): alta relevância na banca {banca} (~15% a 20% adicionais).
4. TÓPICOS P2 — MÉDIOS (`prio=2`, `mc=0`): relevância intermediária e consolidação (~25% a 30%).
5. TÓPICOS P3 — BAIXOS (`prio=3`, `mc=0`): tópicos complementares e de baixa incidência (~20% a 25%).
6. RESIDUAIS (`prio=0`, `mc=0`): incidência quase nula na {banca}, por último na trilha.

RETORNE ESTRITAMENTE UM JSON COMPACTO NO FORMATO:
{{"t":[[id,ordem,prio,mc,pre]]}}
Regras do formato:
- Inclua TODOS os {total_topicos_lote} IDs enviados, sem omitir nenhum.
- `id`: inteiro exato do tópico recebido.
- `ordem`: inteiro 1..n dentro da respectiva disciplina (pré-requisitos -> mais cobrados -> demais P1 -> P2 -> P3 -> residuais).
- `prio`: 1 (P1 Alta), 2 (P2 Média), 3 (P3 Baixa) ou 0 (Residual).
- `mc`: 1 (Mais Cobrado) ou 0.
- `pre`: 1 (Pré-requisito conceitual indispensável) ou 0.

DISCIPLINAS DO LOTE (`d`=nome, `n`=qtd, `mc_alvo`=qtd exata de Mais Cobrados, `t`=[[id,titulo]]):
{json.dumps(payload_compacto, ensure_ascii=False)}"""

    def _gerar_motivo_ia_classificado(pri: Optional[int], mc: bool, pre: bool) -> str:
        if pre and not mc:
            return f"🧱 Pré-requisito conceitual indispensável (IA • {banca}): base necessária para os tópicos mais cobrados."
        if mc and pri == 1:
            return f"🔥 Núcleo Pareto 80/20 (IA • {banca}): altíssima incidência histórica para {area_concurso}."
        if mc:
            return f"🔥 Recorrente na {banca} (IA): alta frequência histórica em {area_concurso}."
        if pri == 1:
            return f"⚡ Prioridade Alta P1 (IA • {banca}): tema relevante de alto custo-benefício."
        if pri == 2:
            return f"⭐ Prioridade Média P2 (IA • {banca}): consolidação intermediária após o núcleo P1."
        if pri == 3:
            return f"🔹 Prioridade Baixa P3 (IA • {banca}): tópico complementar de menor incidência."
        return f"📋 Residual (IA • {banca}): baixa incidência histórica; estudar por último."

    def _parse_resposta_lote(texto: str) -> Optional[Dict[int, Dict[str, Any]]]:
        parsed = extrair_json_resiliente(texto)
        if not isinstance(parsed, dict):
            return None
        lista = parsed.get("t") if isinstance(parsed.get("t"), list) else parsed.get("topicos")
        if not isinstance(lista, list) or not lista:
            return None
        mapa: Dict[int, Dict[str, Any]] = {}
        for item in lista:
            if isinstance(item, list) and len(item) >= 5:
                try:
                    tid = int(str(item[0]).strip())
                except Exception:
                    continue
                try:
                    ord_val = int(item[1])
                except Exception:
                    ord_val = 999
                try:
                    pri_raw = int(item[2]) if item[2] is not None else 0
                except Exception:
                    pri_raw = 0
                pri_val = pri_raw if pri_raw in (1, 2, 3) else None
                mc_val = bool(int(item[3])) if isinstance(item[3], (int, float, bool)) else str(item[3]).lower() in ("1", "true")
                pre_val = bool(int(item[4])) if isinstance(item[4], (int, float, bool)) else str(item[4]).lower() in ("1", "true")
                if mc_val and pri_val is None:
                    pri_val = 1
                motivo_val = _gerar_motivo_ia_classificado(pri_val, mc_val, pre_val)
            elif isinstance(item, dict):
                raw_id = item.get("id")
                if raw_id is None:
                    continue
                try:
                    tid = int(str(raw_id).strip())
                except Exception:
                    continue
                pri_raw = item.get("p", item.get("prioridade"))
                try:
                    pri_val = int(pri_raw) if pri_raw is not None else None
                except Exception:
                    pri_val = None
                if pri_val not in (1, 2, 3):
                    pri_val = None
                mc_val = bool(item.get("mc", item.get("mais_cobrado", False)))
                if mc_val and pri_val is None:
                    pri_val = 1
                pre_val = bool(item.get("pre", item.get("eh_prerequisito", False)))
                ord_raw = item.get("o", item.get("ordem_trilha"))
                try:
                    ord_val = int(ord_raw) if ord_raw is not None else 999
                except Exception:
                    ord_val = 999
                motivo_val = str(item.get("m", item.get("motivo_ia", "")) or "").strip() or _gerar_motivo_ia_classificado(pri_val, mc_val, pre_val)
            else:
                continue

            mapa[tid] = {
                "id": tid,
                "ordem_trilha": ord_val,
                "prioridade": pri_val,
                "mais_cobrado": mc_val,
                "eh_prerequisito": pre_val,
                "motivo_ia": motivo_val,
            }
        return mapa if mapa else None

    modelos_candidatos = await selecionar_modelos_gemini_rapidos(api_key, max_modelos=3)

    async with httpx.AsyncClient(timeout=timeout_segundos) as http_client:
        # Até 2 rodadas rápidas para absorver picos momentâneos de 503 sem estourar o orçamento de tempo
        for rodada in range(2):
            if rodada > 0:
                await asyncio.sleep(1.0)
                modelos_candidatos = await selecionar_modelos_gemini_rapidos(api_key, max_modelos=3)

            for modelo in list(modelos_candidatos):
                try:
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent?key={api_key}"
                    payload = {
                        "contents": [{"parts": [{"text": prompt}]}],
                        "generationConfig": {
                            "responseMimeType": "application/json",
                            "temperature": 0.0,
                            "maxOutputTokens": 4096,
                            "thinkingConfig": {"thinkingBudget": 0},
                        },
                    }
                    resp = await http_client.post(url, json=payload)
                    if resp.status_code == 400 and "thinkingConfig" in payload["generationConfig"]:
                        payload["generationConfig"].pop("thinkingConfig", None)
                        resp = await http_client.post(url, json=payload)

                    if resp.status_code == 200:
                        resp_json = resp.json()
                        partes = resp_json.get("candidates", [{}])[0].get("content", {}).get("parts", [])
                        texto = "".join(p.get("text", "") for p in partes if "text" in p).strip()
                        mapa = _parse_resposta_lote(texto)
                        if mapa:
                            return mapa, modelo
                    elif resp.status_code in (401, 403) or "API_KEY_INVALID" in resp.text:
                        print(f"[TRILHA IA LOTE] Chave recusada ({resp.status_code}) em {modelo}")
                        return None, None
                    elif resp.status_code in (404, 429):
                        remover_modelo_gemini_cache(api_key, modelo)
                        print(f"[TRILHA IA LOTE] HTTP {resp.status_code} em {modelo}; removido da fila ativa.")
                        continue
                    elif resp.status_code == 503:
                        rebaixar_modelo_gemini_cache(api_key, modelo)
                        print(f"[TRILHA IA LOTE] HTTP 503 (alta demanda) em {modelo}; tentando próximo modelo...")
                        continue
                    else:
                        print(f"[TRILHA IA LOTE] HTTP {resp.status_code} em {modelo}: {resp.text[:120]}")
                except Exception as e:
                    rebaixar_modelo_gemini_cache(api_key, modelo)
                    print(f"[TRILHA IA LOTE] Erro com {modelo}: {type(e).__name__}: {e}")
                    continue

    return None, None



def obter_proximo_topico_trilha_disciplina(
    disc: Disciplina,
    topicos_vistos_ids: Optional[set] = None,
    banca_nome: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Retorna o próximo tópico apontado pela Trilha de Aprendizado & Pareto para uma disciplina.
    Respeita:
    1) Tópicos ainda não concluídos / não vistos em sessão
    2) Ordem da Trilha IA (`ordem_trilha`), priorizando P1 -> Mais Cobrado -> P2 -> P3 -> Ordem Natural
    """
    if not disc or not disc.topicos or disc.categoria == "REVISAO_ANKI":
        return None


    vistos = topicos_vistos_ids or set()

    def esta_concluido_ou_visto(t: Topico) -> bool:
        return bool(t.concluido) or (t.id in vistos)

    def chave_ordenacao_trilha(t: Topico):
        if t.prioridade == 1:
            peso_p = 1
        elif t.mais_cobrado and t.prioridade == 2:
            peso_p = 2
        elif t.prioridade == 2:
            peso_p = 3
        elif t.mais_cobrado:
            peso_p = 4
        elif t.prioridade == 3:
            peso_p = 5
        else:
            peso_p = 6

        ord_trilha = t.ordem_trilha if t.ordem_trilha is not None else 999999
        ord_edital = t.ordem if t.ordem is not None else (t.id or 999999)
        return (ord_trilha, peso_p, ord_edital, t.id or 0)

    todos_ordenados = sorted(disc.topicos, key=chave_ordenacao_trilha)
    pendentes = [t for t in todos_ordenados if not esta_concluido_ou_visto(t)]
    escolhido = pendentes[0] if pendentes else (todos_ordenados[0] if todos_ordenados else None)

    if not escolhido:
        return None


    from app.services.tec_matching_service import montar_dados_vinculo_topico
    return {
        "id": escolhido.id,
        "titulo": escolhido.titulo,
        "ordem": escolhido.ordem if escolhido.ordem is not None else 0,
        "ordem_trilha": escolhido.ordem_trilha,
        "prioridade": escolhido.prioridade,
        "mais_cobrado": bool(escolhido.mais_cobrado),
        "motivo_ia": escolhido.motivo_ia,
        "concluido": bool(escolhido.concluido),
        "visto": esta_concluido_ou_visto(escolhido),
        "tec_vinculo": montar_dados_vinculo_topico(escolhido, getattr(escolhido, "vinculo_tec", None), banca_nome=banca_nome)
    }


def sincronizar_ordem_ciclo_ativo_com_trilha(db: Session, edital: Edital) -> Optional[CicloEstudos]:
    """
    Garante que o Ciclo de Estudos ativo do edital tenha seus blocos de disciplinas
    ordenados de acordo com a Trilha de Aprendizado & Pareto (`Disciplina.ordem_trilha`),
    preservando os IDs dos blocos (`BlocoCiclo.id`) para manter o vínculo com as sessões
    registradas e mantendo os blocos de REVISÃO ANKI intercalados estrategicamente.
    """
    ciclo = (
        db.query(CicloEstudos)
        .filter(CicloEstudos.edital_id == edital.id, CicloEstudos.ativo == True)
        .first()
    )
    if not ciclo or not ciclo.blocos:
        return ciclo

    blocos_atuais = list(ciclo.blocos)
    bloco_em_foco_antigo = (
        blocos_atuais[ciclo.bloco_atual_index]
        if 0 <= (ciclo.bloco_atual_index or 0) < len(blocos_atuais)
        else blocos_atuais[0]
    )

    blocos_estudo = [
        b for b in blocos_atuais
        if b.disciplina and b.disciplina.categoria != "REVISAO_ANKI" and b.disciplina.nome != "REVISÃO ANKI"
    ]
    blocos_revisao = [
        b for b in blocos_atuais
        if not b.disciplina or b.disciplina.categoria == "REVISAO_ANKI" or b.disciplina.nome == "REVISÃO ANKI"
    ]

    # Ordena os blocos de estudo seguindo rigorosamente a ordem da Trilha de Aprendizado IA
    blocos_estudo.sort(
        key=lambda b: (
            b.disciplina.ordem_trilha if (b.disciplina and b.disciplina.ordem_trilha is not None) else 999,
            -(b.duracao_minutos or 60),
            b.id or 0
        )
    )

    # Intercala os blocos de REVISÃO ANKI no meio e no final da esteira (como no padrão do ciclo)
    nova_sequencia: List[BlocoCiclo] = []
    if len(blocos_revisao) == 0:
        nova_sequencia = blocos_estudo
    elif len(blocos_revisao) == 1:
        meio = len(blocos_estudo) // 2
        nova_sequencia = blocos_estudo[:meio] + [blocos_revisao[0]] + blocos_estudo[meio:]
    else:
        meio = len(blocos_estudo) // 2
        nova_sequencia = (
            blocos_estudo[:meio]
            + [blocos_revisao[0]]
            + blocos_estudo[meio:]
            + blocos_revisao[1:]
        )

    for nova_ordem, bloco in enumerate(nova_sequencia):
        bloco.ordem = nova_ordem

    # Se o bloco em foco anterior era REVISÃO ANKI ou se queremos apontar para a disciplina ativa,
    # mantemos o índice apontando para a primeira disciplina da trilha (ou preservamos se válido)
    if bloco_em_foco_antigo and bloco_em_foco_antigo in nova_sequencia:
        novo_idx = nova_sequencia.index(bloco_em_foco_antigo)
        # Se estava apontando para REVISÃO ANKI, avança para a próxima disciplina de estudo
        if (
            bloco_em_foco_antigo.disciplina
            and bloco_em_foco_antigo.disciplina.categoria == "REVISAO_ANKI"
            and len(blocos_estudo) > 0
        ):
            novo_idx = (novo_idx + 1) % len(nova_sequencia)
        ciclo.bloco_atual_index = novo_idx
    else:
        ciclo.bloco_atual_index = 0

    db.flush()
    return ciclo


async def analisar_e_gerar_trilha_edital(
    db: Session,
    edital_id: Optional[int] = None,
    forcar: bool = False,
    api_key: Optional[str] = None
) -> Dict[str, Any]:
    """
    Executa a análise completa de todas as disciplinas e tópicos do edital (apenas uma vez
    automaticamente, ou sob demanda quando `forcar=True`), persistindo no banco de dados:
    - Ordem de aprendizado das disciplinas (`Disciplina.ordem_trilha`)
    - Pré-requisitos e justificativa Pareto da banca (`pre_requisitos_ia`, `justificativa_trilha_ia`)
    - Tópicos mais cobrados (`Topico.mais_cobrado`), prioridades (`Topico.prioridade` P1/P2/P3),
      ordem didática dos tópicos (`Topico.ordem_trilha`) e explicação (`Topico.motivo_ia`)
    - Sincronização da ordem das disciplinas no ciclo atual (`BlocoCiclo.ordem`).
    """
    config = db.query(ConfiguracaoPainelProva).first()
    if not config:
        config = ConfiguracaoPainelProva(id=1)
        db.add(config)
        db.commit()
        db.refresh(config)

    banca = (config.banca or "Cebraspe").strip()
    estilo_banca = (config.estilo_banca or "Certo / Errado (1 anula 1)").strip()
    concurso = (config.concurso or "SEFAZ ALAGOAS").strip()
    cargo = (config.cargo or "Auditor Fiscal da Receita Estadual").strip()
    especialidade = (config.especialidade or "Tecnologia da Informação").strip()
    area_concurso = (getattr(config, "area_concurso", None) or "Fiscal").strip()
    formato_prova = (config.formato_prova or "160 itens + Discursiva").strip()
    nota_corte = float(config.nota_corte if config.nota_corte is not None else 78.5)
    status_edital = (config.status_edital or "Pós-Edital (Edital Publicado)").strip()
    data_prova = config.data_prova or "2026-11-29"
    total_vagas = (config.total_vagas or "35 vagas (28 AC | 7 Cotas)").strip()

    # Cálculo dos dias restantes até a prova
    dias_restantes = None
    if data_prova:
        try:
            from datetime import date
            dt_p = date.fromisoformat(data_prova)
            dias_restantes = (dt_p - date.today()).days
        except Exception:
            dias_restantes = None

    # Localiza o edital alvo
    edital = None
    if edital_id:
        edital = db.query(Edital).filter(Edital.id == edital_id).first()
    if not edital:
        ciclo_ativo = db.query(CicloEstudos).filter(CicloEstudos.ativo == True).first()
        if ciclo_ativo and ciclo_ativo.edital_id:
            edital = db.query(Edital).filter(Edital.id == ciclo_ativo.edital_id).first()
    if not edital:
        edital = db.query(Edital).order_by(Edital.data_criacao.desc()).first()

    if not edital:
        raise ValueError("Nenhum edital encontrado para análise da trilha.")

    disciplinas_validas = [
        d for d in edital.disciplinas
        if d.categoria != "REVISAO_ANKI" and d.nome != "REVISÃO ANKI"
    ]

    # Se já foi analisado anteriormente e não foi forçado pelo botão, retorna o estado salvo no banco!
    if edital.ia_trilha_analisada and not forcar:
        # Garante apenas que nenhum tópico ficou sem ordem_trilha
        algum_sem_trilha = any(
            d.ordem_trilha is None or any(t.ordem_trilha is None for t in d.topicos)
            for d in disciplinas_validas
        )
        if not algum_sem_trilha:
            return montar_resumo_retorno_trilha(db, edital, ja_existia=True)

    # Mapeia histórico de sessões por tópico para detectar pontos vulneráveis reais do aluno
    sessoes = (
        db.query(SessaoEstudo)
        .join(Disciplina)
        .filter(Disciplina.edital_id == edital.id)
        .all()
    )
    sessoes_por_topico: Dict[int, Dict[str, Any]] = {}
    for s in sessoes:
        if s.topico_id:
            if s.topico_id not in sessoes_por_topico:
                sessoes_por_topico[s.topico_id] = {"questoes": 0, "acertos": 0, "minutos": 0}
            sessoes_por_topico[s.topico_id]["questoes"] += (s.qtd_questoes_total or 0)
            sessoes_por_topico[s.topico_id]["acertos"] += (s.qtd_acertos or 0)
            sessoes_por_topico[s.topico_id]["minutos"] += (s.tempo_estudado_minutos or 0)

    # 1. Executa o diagnóstico pedagógico (Pré-requisitos) + Pareto 80/20 base em todas as disciplinas
    diag_por_disc: Dict[int, Dict[str, Any]] = {}
    disciplinas_payload_ia = []
    for d in disciplinas_validas:
        topicos_norm = normalizar_ordem_natural_topicos(d)
        diag = diagnosticar_disciplina_trilha(d, banca)
        diag_por_disc[d.id] = diag

        disciplinas_payload_ia.append({
            "id": d.id,
            "nome": d.nome,
            "grupo": d.grupo_conhecimento,
            "peso_prova": d.peso_prova,
            "qtd_questoes_prova": d.qtd_questoes_prova,
            "topicos": [
                {"id": t.id, "titulo": t.titulo[:110]}
                for t in topicos_norm
            ]
        })

    # Ordena disciplinas pelo score pedagógico + Pareto (base/pré-requisito primeiro + maior peso Pareto)
    disciplinas_ordenadas_base = sorted(
        disciplinas_validas,
        key=lambda d: (
            diag_por_disc[d.id]["nivel_pedagogico"],
            -diag_por_disc[d.id]["score_pareto_prova"],
            d.id
        )
    )
    for pos, d in enumerate(disciplinas_ordenadas_base, start=1):
        d.ordem_trilha = pos
        d.pre_requisitos_ia = diag_por_disc[d.id]["pre_requisitos_ia"]
        d.justificativa_trilha_ia = diag_por_disc[d.id]["justificativa_trilha_ia"]

    # 2. Classifica todos os tópicos pela Heurística Especialista (garantindo 100% de cobertura)
    for d in disciplinas_validas:
        avaliacoes = classificar_topicos_disciplina_heuristica(d, banca, sessoes_por_topico)
        for av in avaliacoes:
            topico_obj: Topico = av["topico"]
            topico_obj.prioridade = av["prioridade"]
            topico_obj.mais_cobrado = av["mais_cobrado"]
            topico_obj.ordem_trilha = av["ordem_trilha"]
            topico_obj.motivo_ia = av["motivo_ia"]

    # 3. Se houver chave Gemini ativa, consulta o modelo Gemini para enriquecer e refinar a análise!
    modelo_origem = f"Motor Especialista Pareto 80/20 & Pré-Requisitos ({banca})"
    info_dias = f" a {dias_restantes} dias da prova" if dias_restantes is not None else ""
    resumo_estrategico_padrao = (
        f"Trilha Estratégica calibrada a partir do Painel de Prova para a Área {area_concurso} ({concurso} - {cargo}), "
        f"focada no perfil da banca {banca} com critério {estilo_banca} ({formato_prova}{info_dias}). "
        f"A Regra de Pareto (80/20) priorizou os ~20% de tópicos com histórico de maior incidência na banca "
        f"necessários para atingir a nota de corte ({nota_corte}%), escalonando-os em P1 (Alta/Núcleo Pareto) e Mais Cobrados (🔥), "
        f"enquanto a esteira pedagógica dentro de cada disciplina posiciona os conceitos e pré-requisitos fundamentais como Passo #1."
    )
    resumo_estrategico = resumo_estrategico_padrao

    disciplinas_analisadas_ia = 0
    topicos_analisados_ia = 0
    total_topicos_edital = sum(len(d.topicos or []) for d in disciplinas_validas)
    modelos_usados_ia: List[str] = []

    if api_key:
        # 3.1 Aquece a descoberta dinâmica do modelo mais rápido UMA única vez antes das chamadas paralelas
        await selecionar_modelos_gemini_rapidos(api_key, max_modelos=5)

        # 3.2 Empacota as disciplinas em lotes balanceados (~95 tópicos/lote) para reduzir chamadas
        # (ex.: 16 disciplinas / 369 tópicos -> apenas 4 lotes) e evitar picos de 503/429.
        MAX_TOPICOS_POR_LOTE = 95
        discs_com_topicos = sorted(
            [d for d in disciplinas_validas if d.topicos],
            key=lambda d: len(d.topicos),
            reverse=True,
        )
        lotes_disciplinas: List[List[Disciplina]] = []
        for d_cur in discs_com_topicos:
            qtd_cur = len(d_cur.topicos)
            alocado = False
            for lote in lotes_disciplinas:
                soma_lote = sum(len(x.topicos) for x in lote)
                if soma_lote + qtd_cur <= MAX_TOPICOS_POR_LOTE:
                    lote.append(d_cur)
                    alocado = True
                    break
            if not alocado:
                lotes_disciplinas.append([d_cur])

        print(
            f"[TRILHA IA] Analisando {len(discs_com_topicos)} disciplinas ({total_topicos_edital} tópicos) "
            f"em {len(lotes_disciplinas)} lote(s) balanceado(s) + visão macro em paralelo..."
        )

        # Concorrência suave (2 em paralelo) evita picos de 503 na API gratuita e mantém cada lote rápido!
        sem = asyncio.Semaphore(2)
        mapa_global_ia: Dict[int, Dict[str, Any]] = {}
        resposta_ia_holder: Dict[str, Any] = {"val": None}

        async def _executar_macro():
            async with sem:
                res_m = await consultar_gemini_para_trilha(
                    api_key=api_key,
                    banca=banca,
                    estilo_banca=estilo_banca,
                    concurso=concurso,
                    cargo=cargo,
                    especialidade=especialidade,
                    disciplinas_info=disciplinas_payload_ia,
                    area_concurso=area_concurso,
                    formato_prova=formato_prova,
                    nota_corte=nota_corte,
                    status_edital=status_edital,
                    dias_restantes=dias_restantes,
                )
                resposta_ia_holder["val"] = res_m

        async def _executar_lote(idx_lote: int, lote_discs: List[Disciplina]):
            lote_payload = [
                {
                    "id": d.id,
                    "nome": d.nome,
                    "topicos": [{"id": t.id, "titulo": t.titulo} for t in d.topicos],
                }
                for d in lote_discs
            ]
            async with sem:
                mapa_res, mod_usado = await consultar_gemini_lote_disciplinas(
                    api_key=api_key,
                    banca=banca,
                    estilo_banca=estilo_banca,
                    concurso=concurso,
                    cargo=cargo,
                    especialidade=especialidade,
                    area_concurso=area_concurso,
                    disciplinas_lote=lote_payload,
                    timeout_segundos=14.0,
                )
                if mod_usado and mod_usado not in modelos_usados_ia:
                    modelos_usados_ia.append(mod_usado)
                if isinstance(mapa_res, dict):
                    # Persiste imediatamente no mapa global para que um eventual timeout nunca descarte lotes prontos!
                    mapa_global_ia.update(mapa_res)
                    print(f"[TRILHA IA] Lote {idx_lote}/{len(lotes_disciplinas)} OK ({len(mapa_res)} tópicos via {mod_usado})")

        tasks = [asyncio.create_task(_executar_lote(i, lt)) for i, lt in enumerate(lotes_disciplinas, start=1)]
        tasks.append(asyncio.create_task(_executar_macro()))

        _, pending = await asyncio.wait(tasks, timeout=45.0)
        if pending:
            print(f"[TRILHA IA] {len(pending)} tarefa(s) ainda pendente(s) aos 45s; preservando {len(mapa_global_ia)} tópicos já concluídos.")
            for p_task in pending:
                p_task.cancel()

        resposta_ia = resposta_ia_holder["val"]

        if resposta_ia and isinstance(resposta_ia.get("disciplinas"), list):
            if resposta_ia.get("_modelo_usado"):
                modelos_usados_ia.append(str(resposta_ia["_modelo_usado"]).replace("Google Gemini (", "").rstrip(")"))
            if resposta_ia.get("resumo_estrategico"):
                resumo_estrategico = str(resposta_ia["resumo_estrategico"]).strip()

            disc_map_db = {d.id: d for d in disciplinas_validas}
            ordens_recebidas = []

            for d_ia in resposta_ia["disciplinas"]:
                if not isinstance(d_ia, dict):
                    continue
                try:
                    d_id = int(str(d_ia.get("id")).strip())
                except Exception:
                    continue
                disc_db = disc_map_db.get(d_id)
                if not disc_db:
                    continue

                if d_ia.get("ordem_trilha") is not None:
                    try:
                        ordens_recebidas.append((int(d_ia["ordem_trilha"]), disc_db))
                    except Exception:
                        pass
                if d_ia.get("pre_requisitos_ia"):
                    disc_db.pre_requisitos_ia = str(d_ia["pre_requisitos_ia"]).strip()
                if d_ia.get("justificativa_trilha_ia"):
                    disc_db.justificativa_trilha_ia = str(d_ia["justificativa_trilha_ia"]).strip()

            if ordens_recebidas:
                ordem_ia_map = {disc_obj.id: ordem_ia for ordem_ia, disc_obj in ordens_recebidas}
                disc_ja_ordenadas = sorted(
                    disciplinas_validas,
                    key=lambda d: (
                        diag_por_disc[d.id]["nivel_pedagogico"],
                        -diag_por_disc[d.id]["score_pareto_prova"],
                        ordem_ia_map.get(d.id, 999),
                        d.id,
                    ),
                )
                for idx_d, d_obj in enumerate(disc_ja_ordenadas, start=1):
                    d_obj.ordem_trilha = idx_d

        # 3.3 Recuperação direcionada: se alguma disciplina ou tópico ficou de fora (falha/omissão),
        # dispara uma rodada de recuperação APENAS para os itens faltantes garantindo 100% IA!
        discs_faltantes_payload: List[Dict[str, Any]] = []
        for d in discs_com_topicos:
            faltantes_d = [{"id": t.id, "titulo": t.titulo} for t in d.topicos if t.id not in mapa_global_ia]
            if faltantes_d:
                discs_faltantes_payload.append({"id": d.id, "nome": d.nome, "topicos": faltantes_d})

        if discs_faltantes_payload:
            qtd_falt = sum(len(x["topicos"]) for x in discs_faltantes_payload)
            print(f"[TRILHA IA] Recuperando {qtd_falt} tópico(s) pendente(s) em {len(discs_faltantes_payload)} disciplina(s)...")
            lotes_rec: List[List[Dict[str, Any]]] = []
            for item_f in discs_faltantes_payload:
                aloc = False
                for lt_r in lotes_rec:
                    if sum(len(x["topicos"]) for x in lt_r) + len(item_f["topicos"]) <= MAX_TOPICOS_POR_LOTE:
                        lt_r.append(item_f)
                        aloc = True
                        break
                if not aloc:
                    lotes_rec.append([item_f])

            async def _exec_rec(lt_r):
                async with sem:
                    return await consultar_gemini_lote_disciplinas(
                        api_key=api_key,
                        banca=banca,
                        estilo_banca=estilo_banca,
                        concurso=concurso,
                        cargo=cargo,
                        especialidade=especialidade,
                        area_concurso=area_concurso,
                        disciplinas_lote=lt_r,
                        timeout_segundos=14.0,
                    )

            try:
                recs = await asyncio.wait_for(
                    asyncio.gather(*[_exec_rec(lt_r) for lt_r in lotes_rec], return_exceptions=True),
                    timeout=25.0,
                )
                for r_rec in recs:
                    if isinstance(r_rec, tuple) and isinstance(r_rec[0], dict):
                        mapa_global_ia.update(r_rec[0])
                        if r_rec[1] and r_rec[1] not in modelos_usados_ia:
                            modelos_usados_ia.append(r_rec[1])
            except Exception as e_rec:
                print(f"[TRILHA IA] Aviso na recuperação de tópicos faltantes: {e_rec}")

        # 3.4 Aplica os resultados da IA em cada disciplina preservando estritamente a hierarquia:
        # Pré-requisito indispensável (se houver) -> Mais Cobrados -> Demais P1 -> P2 -> P3 -> Residual
        for disc_db in discs_com_topicos:
            qtd_match_d = sum(1 for t in disc_db.topicos if t.id in mapa_global_ia)
            if qtd_match_d == 0:
                continue

            disciplinas_analisadas_ia += 1
            topicos_analisados_ia += qtd_match_d

            itens_preparados = []
            for t_obj in disc_db.topicos:
                t_ia = mapa_global_ia.get(t_obj.id)
                if t_ia:
                    pri = t_ia.get("prioridade")
                    if pri not in (1, 2, 3):
                        pri = None
                    mc = bool(t_ia.get("mais_cobrado", False))
                    eh_prereq = bool(t_ia.get("eh_prerequisito", False))
                    ord_ia = t_ia.get("ordem_trilha", 999)
                    motivo = t_ia.get("motivo_ia") or t_obj.motivo_ia
                else:
                    # Fallback seguro apenas se 1 tópico isolado não veio no JSON
                    pri = t_obj.prioridade
                    mc = bool(t_obj.mais_cobrado)
                    eh_prereq = False
                    ord_ia = t_obj.ordem_trilha if t_obj.ordem_trilha is not None else 999
                    motivo = t_obj.motivo_ia

                itens_preparados.append({
                    "t_obj": t_obj,
                    "prioridade": pri,
                    "mais_cobrado": mc,
                    "eh_prerequisito": eh_prereq,
                    "ordem_trilha_ia": ord_ia,
                    "idx_edital": t_obj.ordem if t_obj.ordem is not None else 999,
                    "motivo_ia": motivo,
                })

            def chave_trilha_usuario(x):
                eh_p = x["eh_prerequisito"]
                mc = x["mais_cobrado"]
                pri = x["prioridade"]

                if eh_p and not mc:
                    # Tier 1: Pré-requisito conceitual indispensável apontado pela IA
                    tier = 1
                elif mc and pri == 1:
                    # Tier 2: Mais Cobrados P1 (núcleo Pareto 80/20)
                    tier = 2
                elif mc:
                    # Tier 3: Mais Cobrados P2/P3
                    tier = 3
                elif pri == 1:
                    # Tier 4: Demais P1 (Alta relevância)
                    tier = 4
                elif pri == 2:
                    # Tier 5: P2 (Média relevância)
                    tier = 5
                elif pri == 3:
                    # Tier 6: P3 (Baixa relevância)
                    tier = 6
                else:
                    # Tier 7: Residual / sem marcação
                    tier = 7
                return (tier, x["ordem_trilha_ia"], x["idx_edital"])

            itens_preparados.sort(key=chave_trilha_usuario)
            for idx_passo, item in enumerate(itens_preparados, start=1):
                t_obj = item["t_obj"]
                t_obj.ordem_trilha = idx_passo
                t_obj.prioridade = item["prioridade"]
                t_obj.mais_cobrado = item["mais_cobrado"]
                if item["motivo_ia"]:
                    t_obj.motivo_ia = item["motivo_ia"].strip()
                else:
                    t_obj.motivo_ia = f"Tópico complementar conforme edital {banca}."

        if modelos_usados_ia:
            modelo_origem = f"Google Gemini ({', '.join(dict.fromkeys(modelos_usados_ia))})"

        print(
            f"[TRILHA IA] Concluída! Cobertura IA: {disciplinas_analisadas_ia}/{len(discs_com_topicos)} disciplinas "
            f"({topicos_analisados_ia}/{total_topicos_edital} tópicos) via {modelo_origem}"
        )

    # 4. Atualiza os metadados da Trilha IA no Edital
    agora = datetime.now(timezone.utc)
    cobertura_ia = {
        "disciplinas_analisadas_ia": disciplinas_analisadas_ia,
        "total_disciplinas": len([d for d in disciplinas_validas if d.topicos]),
        "topicos_analisados_ia": topicos_analisados_ia,
        "total_topicos": total_topicos_edital,
        "percentual_cobertura_ia": round((topicos_analisados_ia / total_topicos_edital) * 100.0, 1) if total_topicos_edital else 0.0,
    }
    resumo_json = {
        "resumo_estrategico": resumo_estrategico,
        "banca": banca,
        "estilo_banca": estilo_banca,
        "area_concurso": area_concurso,
        "concurso": concurso,
        "cargo": cargo,
        "especialidade": especialidade,
        "formato_prova": formato_prova,
        "nota_corte": nota_corte,
        "status_edital": status_edital,
        "dias_restantes": dias_restantes,
        "total_vagas": total_vagas,
        "modelo_origem": modelo_origem,
        "cobertura_ia": cobertura_ia,
        "data_analise": agora.isoformat()
    }
    edital.ia_trilha_analisada = True
    edital.ia_trilha_data = agora
    edital.ia_trilha_banca = banca
    edital.ia_trilha_resumo = json.dumps(resumo_json, ensure_ascii=False)

    # 5. Reordena os blocos do Ciclo de Estudos ativo de acordo com a Trilha IA
    sincronizar_ordem_ciclo_ativo_com_trilha(db, edital)

    # Limpa o cache do último insight da IA para que o painel reflita os novos quantitativos Pareto
    if config:
        config.ultimo_insight_ia = None

    db.commit()
    db.refresh(edital)

    return montar_resumo_retorno_trilha(db, edital, ja_existia=False, modelo_origem=modelo_origem)


def montar_resumo_retorno_trilha(
    db: Session,
    edital: Edital,
    ja_existia: bool = False,
    modelo_origem: Optional[str] = None
) -> Dict[str, Any]:
    disciplinas_validas = [
        d for d in edital.disciplinas
        if d.categoria != "REVISAO_ANKI" and d.nome != "REVISÃO ANKI"
    ]
    disciplinas_ordenadas = sorted(
        disciplinas_validas,
        key=lambda d: (d.ordem_trilha if d.ordem_trilha is not None else 999, d.id)
    )

    todos_topicos = [t for d in disciplinas_ordenadas for t in d.topicos]
    total_topicos = len(todos_topicos)
    total_mais_cobrados = sum(1 for t in todos_topicos if t.mais_cobrado)
    total_p1 = sum(1 for t in todos_topicos if t.prioridade == 1)
    total_p2 = sum(1 for t in todos_topicos if t.prioridade == 2)
    total_p3 = sum(1 for t in todos_topicos if t.prioridade == 3)
    total_prioritarios = sum(1 for t in todos_topicos if t.prioridade is not None or t.mais_cobrado)

    resumo_meta = {}
    if edital.ia_trilha_resumo:
        try:
            resumo_meta = json.loads(edital.ia_trilha_resumo)
        except Exception:
            resumo_meta = {"resumo_estrategico": edital.ia_trilha_resumo}

    sessoes = (
        db.query(SessaoEstudo)
        .join(Disciplina)
        .filter(Disciplina.edital_id == edital.id)
        .all()
    )
    topicos_vistos_ids = set(s.topico_id for s in sessoes if s.topico_id is not None)

    vistos_mais_cobrados = sum(1 for t in todos_topicos if t.mais_cobrado and (t.id in topicos_vistos_ids or bool(t.concluido)))
    vistos_p1 = sum(1 for t in todos_topicos if t.prioridade == 1 and (t.id in topicos_vistos_ids or bool(t.concluido)))
    vistos_p2 = sum(1 for t in todos_topicos if t.prioridade == 2 and (t.id in topicos_vistos_ids or bool(t.concluido)))
    vistos_p3 = sum(1 for t in todos_topicos if t.prioridade == 3 and (t.id in topicos_vistos_ids or bool(t.concluido)))

    trilha_disciplinas = []
    for d in disciplinas_ordenadas:
        prox = obter_proximo_topico_trilha_disciplina(d, topicos_vistos_ids)
        trilha_disciplinas.append({
            "id": d.id,
            "nome": d.nome,
            "grupo_conhecimento": d.grupo_conhecimento,
            "ordem_trilha": d.ordem_trilha,
            "pre_requisitos_ia": d.pre_requisitos_ia,
            "justificativa_trilha_ia": d.justificativa_trilha_ia,
            "peso_prova": d.peso_prova,
            "qtd_questoes_prova": d.qtd_questoes_prova,
            "total_topicos": len(d.topicos),
            "total_mais_cobrados": sum(1 for t in d.topicos if t.mais_cobrado),
            "total_p1": sum(1 for t in d.topicos if t.prioridade == 1),
            "total_p2": sum(1 for t in d.topicos if t.prioridade == 2),
            "total_p3": sum(1 for t in d.topicos if t.prioridade == 3),
            "proximo_topico": prox
        })

    return {
        "sucesso": True,
        "ja_existia": ja_existia,
        "edital_id": edital.id,
        "edital_nome": edital.nome,
        "ia_trilha_analisada": bool(edital.ia_trilha_analisada),
        "ia_trilha_banca": edital.ia_trilha_banca or resumo_meta.get("banca", "Cebraspe"),
        "ia_trilha_area": resumo_meta.get("area_concurso", "Fiscal"),
        "ia_trilha_data": edital.ia_trilha_data.isoformat() if edital.ia_trilha_data else None,
        "modelo_origem": modelo_origem or resumo_meta.get("modelo_origem", "Google Gemini"),
        "cobertura_ia": resumo_meta.get("cobertura_ia"),
        "resumo_estrategico": resumo_meta.get("resumo_estrategico", ""),
        "parametros_prova": {
            "concurso": resumo_meta.get("concurso", "SEFAZ ALAGOAS"),
            "cargo": resumo_meta.get("cargo", "Auditor Fiscal"),
            "especialidade": resumo_meta.get("especialidade", "Tecnologia da Informação"),
            "banca": edital.ia_trilha_banca or resumo_meta.get("banca", "Cebraspe"),
            "estilo_banca": resumo_meta.get("estilo_banca", "Certo / Errado (1 anula 1)"),
            "area_concurso": resumo_meta.get("area_concurso", "Fiscal"),
            "formato_prova": resumo_meta.get("formato_prova", "160 itens + Discursiva"),
            "nota_corte": resumo_meta.get("nota_corte", 78.5),
            "status_edital": resumo_meta.get("status_edital", "Pós-Edital"),
            "dias_restantes": resumo_meta.get("dias_restantes")
        },
        "metricas_pareto": {
            "total_disciplinas": len(disciplinas_ordenadas),
            "total_topicos": total_topicos,
            "total_mais_cobrados": total_mais_cobrados,
            "perc_mais_cobrados": round(total_mais_cobrados / total_topicos * 100, 1) if total_topicos > 0 else 0.0,
            "vistos_mais_cobrados": vistos_mais_cobrados,
            "total_p1": total_p1,
            "perc_p1": round(total_p1 / total_topicos * 100, 1) if total_topicos > 0 else 0.0,
            "vistos_p1": vistos_p1,
            "total_p2": total_p2,
            "perc_p2": round(total_p2 / total_topicos * 100, 1) if total_topicos > 0 else 0.0,
            "vistos_p2": vistos_p2,
            "total_p3": total_p3,
            "perc_p3": round(total_p3 / total_topicos * 100, 1) if total_topicos > 0 else 0.0,
            "vistos_p3": vistos_p3,
            "total_prioritarios": total_prioritarios
        },
        "trilha_disciplinas": trilha_disciplinas
    }
