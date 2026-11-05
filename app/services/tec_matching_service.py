import os
import re
import json
import unicodedata
from difflib import SequenceMatcher
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple, Set
import httpx
from sqlalchemy.orm import Session

from app.models.edital import Edital
from app.models.disciplina import Disciplina
from app.models.topico import Topico
from app.models.configuracao_prova import ConfiguracaoPainelProva
from app.models.tec_taxonomia import TecTaxonomia, TopicoEstudoTecDePara
from app.services.tec_scraper_service import TEC_BASE_URL
from urllib.parse import quote_plus


STOP_WORDS_EDITAL: Set[str] = {
    "a", "as", "o", "os", "de", "da", "do", "das", "dos", "em", "no", "na",
    "nos", "nas", "por", "para", "com", "sem", "sob", "sobre", "entre", "ate",
    "ao", "aos", "um", "uma", "uns", "umas", "e", "ou", "que", "se", "como",
    "art", "arts", "artigo", "artigos", "inciso", "paragrafo", "caput",
    "nocoes", "nocao", "introducao", "aspectos", "gerais", "geral",
    "disposicoes", "basicos", "basicas", "basico", "basica", "aplicada",
    "aplicado", "aplicados", "aplicadas", "estudo", "conceito", "conceitos",
    "definicao", "definicoes", "caracteristicas", "tipos", "classificacao",
}

# Mapeamento de Disciplina do Edital -> Slugs de Matérias do TEC Concursos
MAPA_DISCIPLINA_PARA_SLUGS_TEC: List[Tuple[List[str], List[str]]] = [
    (
        ["MATEMATICA FINANCEIRA"],
        ["matematica-financeira"]
    ),
    (
        ["RACIOCINIO LOGICO", "LOGICA"],
        ["raciocinio-logico"]
    ),
    (
        ["ESTATISTICA", "PROBABILIDADE"],
        ["estatistica"]
    ),
    (
        ["CONSTITUCIONAL"],
        ["direito-constitucional-cf1988-e-doutrina"]
    ),
    (
        ["ADMINISTRATIVO"],
        ["direito-administrativo-doutrina-e-leis-federais"]
    ),
    (
        ["CONTABILIDADE GERAL", "CONTABILIDADE SOCIETARIA"],
        ["contabilidade-geral"]
    ),
    (
        ["CONTABILIDADE PUBLICA"],
        ["afo-direito-financeiro-e-contabilidade-publica"]
    ),
    (
        ["FINANCAS PUBLICAS", "ORCAMENTO", "AFO", "DIREITO FINANCEIRO"],
        ["economia-e-financas-publicas", "afo-direito-financeiro-e-contabilidade-publica"]
    ),
    (
        ["ECONOMIA"],
        ["economia-e-financas-publicas"]
    ),
    (
        ["REFORMA TRIBUTARIA"],
        [
            "direito-tributario",
            "direito-constitucional-cf1988-e-doutrina",
            "legislacao-tributaria-dos-estados-e-do-distrito-federal",
            "legislacao-tributaria-federal"
        ]
    ),
    (
        ["LEGISLACAO TRIBUTARIA"],
        [
            "legislacao-tributaria-dos-estados-e-do-distrito-federal",
            "direito-tributario",
            "legislacao-tributaria-federal"
        ]
    ),
    (
        ["TRIBUTARIO"],
        ["direito-tributario", "direito-constitucional-cf1988-e-doutrina"]
    ),
    (
        ["AUDITORIA"],
        [
            "auditoria-privada",
            "auditoria-governamental-e-controle",
            "legislacao-tributaria-dos-estados-e-do-distrito-federal",
            "contabilidade-geral",
            "direito-tributario"
        ]
    ),
    (
        ["INTELIGENCIA ARTIFICIAL"],
        ["ti-ciencia-de-dados-e-inteligencia-artificial", "estatistica"]
    ),
    (
        ["CIENCIA DE DADOS", "BANCO DE DADOS", "DADOS"],
        [
            "ti-ciencia-de-dados-e-inteligencia-artificial",
            "ti-banco-de-dados",
            "estatistica"
        ]
    ),
    (
        ["DESENVOLVIMENTO DE SISTEMAS", "ENGENHARIA DE SOFTWARE", "PROGRAMACAO"],
        [
            "ti-desenvolvimento-de-sistemas",
            "ti-engenharia-de-software",
            "ti-seguranca-da-informacao",
            "ti-gestao-e-governanca-de-ti"
        ]
    ),
    (
        ["INFRAESTRUTURA", "SEGURANCA DA INFORMACAO", "REDES"],
        [
            "ti-seguranca-da-informacao",
            "ti-redes-de-computadores",
            "ti-sistemas-operacionais",
            "ti-gestao-e-governanca-de-ti",
            "ti-desenvolvimento-de-sistemas",
            "ti-organizacao-e-arquitetura-dos-computadores"
        ]
    ),
    (
        ["PORTUGUES", "LINGUA PORTUGUESA"],
        ["lingua-portuguesa-portugues"]
    ),
    (
        ["PREVIDENCIARIO"],
        ["direito-previdenciario"]
    ),
    (
        ["INFORMATICA"],
        ["informatica", "ti-seguranca-da-informacao", "ti-redes-de-computadores"]
    ),
]

# Expansões semânticas para reconciliar vocabulário de editais (Cebraspe/FGV/FCC) com a árvore do TEC
SINONIMOS_TERMOS_TEC: List[Tuple[List[str], str]] = [
    (["firewall", "waf", "web application firewall", "proxy", "dmz"], "dispositivos de seguranca de perimetro conceitos de firewall proxy e dmz"),
    (["ids", "ips", "prevencao de intrusao", "deteccao de intrusao", "honeypot"], "ids ips e honeypots"),
    (["vpn", "ipsec", "ssl", "tls", "ssh", "https"], "vpn protocolos seguros"),
    (["zero trust", "confianca zero"], "zero trust modelo de confianca zero"),
    (["nac", "controle de acesso a rede", "802 1x", "radius", "tacacs"], "controle de acesso a rede nac protocolos de autenticacao"),
    (["mfa", "2fa", "autenticacao multifator", "oauth", "openid", "saml", "kerberos", "ldap", "iam", "rbac", "abac"], "controle de acesso autenticacao protocolos de autenticacao"),
    (["owasp", "xss", "csrf", "sql injection", "injecao"], "owasp ataques a aplicacoes web seguranca em aplicacoes"),
    (["devsecops", "sast", "dast", "desenvolvimento seguro"], "devsecops testes de seguranca em desenvolvimento sast e dast ciclo de vida de desenvolvimento seguro"),
    (["forense", "cadeia de custodia", "evidencia digital"], "computacao forense auditoria de ti e forense computacional"),
    (["pentest", "teste de invasao", "vulnerabilidade", "cve", "cvss"], "testes de seguranca pentest varreduras"),
    (["siem", "soar", "edr", "xdr", "csirt", "resposta a incidentes"], "eventos e incidentes de seguranca csirt sans handbook e xdr siem"),
    (["27001", "27002", "sgsi"], "sgsi controles e estrutura das normas da familia 27000 iso iec 27001 27002"),
    (["27005", "31000", "gestao de riscos"], "riscos em seguranca da informacao nbr iso iec 27001 27002 e 27005"),
    (["27701", "lgpd", "privacidade"], "nbr iso iec 27701 requisitos e diretrizes"),
    (["22301", "15999", "continuidade de negocios", "continuidade de negocio"], "gestao de continuidade de negocio nbr iso iec"),
    (["nist", "cis controls", "mitre", "stride"], "frameworks de seguranca da informacao nist cis mitre attck stride"),
    (["icp-brasil", "icp brasil", "certificado digital", "certificacao digital", "autoridade certificadora"], "certificado digital icp e autoridades certificadoras"),
    (["assinatura digital", "hash", "sha", "rsa", "aes", "criptografia", "chaves publicas"], "criptografia assinatura digital hashes criptograficos algoritmos de criptografia"),
    (["docker", "kubernetes", "container", "conteiner", "orquestracao"], "docker kubernetes virtualizacao"),
    (["nuvem", "cloud", "iaas", "paas", "saas"], "computacao em nuvem cloud computing"),
    (["itil", "gerenciamento de servicos"], "itil"),
    (["cobit", "governanca de ti"], "cobit governanca de ti"),
    (["scrum", "kanban", "xp", "extreme programming", "metodologias ageis", "ageis", "agil"], "metodologias ageis scrum kanban xp"),
    (["bpmn", "modelagem de processos", "as-is", "to-be"], "bpmn gestao de processos de negocio bpm"),
    (["microsservicos", "microservices", "arquitetura hexagonal", "clean architecture", "ddd", "soa"], "arquitetura de software microsservicos arquitetura orientada a servicos soa"),
    (["rest", "restful", "graphql", "grpc", "soap", "api", "webhook"], "web services soap e rest arquitetura orientada a servicos"),
    (["git", "ci cd", "integracao continua", "entrega continua", "devops"], "devops integracao continua controle de versao git"),
    (["padroes de projeto", "design patterns", "gof", "solid", "orientacao a objetos", "uml"], "padroes de projeto design patterns programacao orientada a objetos uml"),
    (["crisp-dm", "kdd", "semma", "mineracao de dados", "data mining"], "mineracao de dados data mining crisp dm"),
    (["aprendizado de maquina", "machine learning", "supervisionado", "nao supervisionado", "regressao", "classificacao", "clusterizacao", "agrupamento", "random forest", "svm", "kmeans"], "aprendizado de maquina machine learning classificacao regressao agrupamento"),
    (["redes neurais", "deep learning", "aprendizado profundo", "cnn", "rnn", "lstm", "perceptron", "backpropagation"], "redes neurais artificiais deep learning aprendizado profundo"),
    (["processamento de linguagem natural", "pln", "nlp", "tokenizacao", "embeddings", "bert", "gpt", "llm", "transformers", "rag", "generativa"], "processamento de linguagem natural pln grandes modelos de linguagem llm inteligencia artificial"),
    (["data warehouse", "data lake", "lakehouse", "etl", "elt", "olap", "oltp", "star schema", "snowflake", "dimensional", "multidimensional"], "data warehouse dw bi olap modelagem dimensional etl"),
    (["modelagem relacional", "normalizacao", "formas normais", "mer", "der", "entidade-relacionamento", "bancos de dados relacionais"], "modelo relacional modelagem entidade relacionamento normalizacao de dados"),
    (["sql", "ddl", "dml", "dcl", "tcl", "stored procedures", "triggers", "views", "indices", "transacoes", "acid"], "linguagem sql controle de transacoes e concorrencia"),
    (["nosql", "mongodb", "redis", "cassandra", "neo4j", "chave-valor", "orientado a documentos", "grafos"], "bancos de dados nosql"),
    (["big data", "hadoop", "spark", "kafka", "mapreduce"], "big data ecossistema hadoop spark"),
    (["132/2023", "ec 132", "214/2025", "lc 214", "ibs", "cbs", "imposto seletivo", "reforma tributaria", "split payment", "comite gestor", "nao cumulatividade plena", "cashback"], "reforma tributaria ec 132 2023 sistema tributario nacional"),
    (["icms", "lc 87", "lei kandir", "substituicao tributaria", "fato gerador do icms"], "icms imposto sobre operacoes relativas a circulacao de mercadorias"),
    (["ipva"], "ipva imposto sobre a propriedade de veiculos automotores"),
    (["itcd", "itcmd", "causa mortis"], "itcmd imposto sobre transmissao causa mortis e doacao"),
    (["processo administrativo tributario", "pat", "auto de infracao", "julgamento administrativo"], "processo administrativo tributario"),
    (["sped", "efd", "nf-e", "nfc-e", "cfop", "cst", "malha fiscal", "omissao de receitas", "auditoria fiscal"], "escrituracao fiscal digital sped nota fiscal eletronica auditoria fiscal"),
    (["lrf", "lc 101", "101/2000", "responsabilidade fiscal", "despesa com pessoal", "divida e endividamento", "relatorio resumido", "rreo", "rgf"], "lei de responsabilidade fiscal lc 101 2000"),
    (["ppa", "ldo", "loa", "plano plurianual", "diretrizes orcamentarias", "orcamento anual", "ciclo orcamentario", "creditos adicionais"], "instrumentos de planejamento ppa ldo e loa ciclo orcamentario creditos adicionais"),
    (["principios orcamentarios", "anualidade", "universalidade", "exclusividade", "nao afetação"], "principios orcamentarios"),
    (["receita orcamentaria", "estagios da receita", "divida ativa"], "receita publica estagios da receita"),
    (["despesa orcamentaria", "empenho", "liquidacao", "pagamento", "restos a pagar", "dea", "despesas de exercicios anteriores", "suprimento de fundos"], "despesa publica estagios da despesa restos a pagar despesas de exercicios anteriores suprimento de fundos"),
    (["pcasp", "plano de contas aplicado ao setor publico", "natureza da informacao"], "plano de contas aplicado ao setor publico pcasp"),
    (["dcasp", "balanco orcamentario", "balanco financeiro", "balanco patrimonial", "demonstracao das variacoes patrimoniais", "dvp"], "demonstracoes contabeis aplicadas ao setor publico dcasp"),
    (["variacoes patrimoniais", "vpa", "vpd", "qualitativas", "quantitativas"], "variacoes patrimoniais"),
    (["funcoes do estado", "musgrave", "alocativa", "distributiva", "estabilizadora", "falhas de mercado", "bens publicos", "externalidades"], "funcoes do governo alocativa distributiva e estabilizadora falhas de mercado"),
    (["balanco patrimonial", "ativo", "passivo", "patrimonio liquido", "equacao fundamental"], "balanco patrimonial patrimonio"),
    (["dre", "demonstracao do resultado do exercicio", "dfc", "fluxos de caixa", "dva", "dlpa", "dmpl"], "demonstracao do resultado do exercicio dre demonstracao dos fluxos de caixa dfc"),
    (["cpc", "imobilizado", "intangivel", "estoques", "provisoes", "contingencias", "depreciacao", "amortizacao", "exaustao", "impairment", "reducao ao valor recuperavel"], "pronunciamentos contabeis cpcs ativo imobilizado ativo intangivel depreciacao provisoes"),
    (["juros simples", "juros compostos", "desconto simples", "desconto composto", "desconto racional", "desconto comercial"], "juros simples juros compostos descontos"),
    (["taxas de juros", "nominal", "efetiva", "equivalente", "proporcional", "real", "aparente"], "taxas de juros"),
    (["amortizacao", "sistema frances", "price", "sac", "amortizacao constante", "series de pagamentos", "rendas", "fluxo de caixa", "vpl", "tir"], "sistemas de amortizacao rendas uniformes analise de investimentos vpl e tir"),
    (["14.133", "licitacao", "licitacoes", "contratos administrativos", "pregao", "dialogo competitivo", "dispensa", "inexigibilidade"], "licitacoes e contratos administrativos lei 14133 2021"),
    (["8.429", "improbidade administrativa"], "improbidade administrativa lei 8429 1992"),
    (["ato administrativo", "atos administrativos", "atributos", "elementos", "requisitos", "anulacao", "revogacao", "convalidacao"], "atos administrativos"),
    (["poderes administrativos", "poder de policia", "hierarquico", "disciplinar", "regulamentar", "vinculado", "discricionario"], "poderes da administracao"),
    (["agentes publicos", "servidores publicos", "acumulacao", "estabilidade", "provimento", "vacancia"], "agentes publicos"),
    (["organizacao administrativa", "administracao direta", "administracao indireta", "autarquias", "fundacoes", "empresas publicas", "sociedades de economia mista", "descentralizacao", "desconcentracao"], "organizacao administrativa"),
    (["responsabilidade civil do estado", "art 37 6", "teoria do risco administrativo"], "responsabilidade civil do estado"),
    (["controle da administracao", "controle externo", "controle interno", "tribunal de contas"], "controle da administracao publica"),
    (["processo administrativo", "9.784"], "processo administrativo lei 9784 1999"),
    (["controle de constitucionalidade", "adi", "adc", "adpf", "sumula vinculante", "difuso", "concentrado"], "controle de constitucionalidade"),
    (["direitos e garantias fundamentais", "direitos e deveres individuais", "art 5", "remedios constitucionais", "habeas corpus", "mandado de seguranca"], "direitos e deveres individuais e coletivos remedios constitucionais"),
    (["nacionalidade", "nato", "naturalizado"], "da nacionalidade"),
    (["direitos politicos", "partidos politicos", "inelegibilidade", "plebiscito", "referendo"], "direitos politicos partidos politicos"),
    (["organizacao politico-administrativa", "reparticao de competencias", "uniao", "estados", "municipios", "distrito federal", "intervencao"], "da organizacao politico administrativa uniao estados municipios"),
    (["processo legislativo", "emenda constitucional", "lei complementar", "lei ordinaria", "medida provisoria", "veto"], "processo legislativo"),
    (["poder executivo", "presidente da republica"], "poder executivo"),
    (["poder judiciario", "stf", "stj", "cnj"], "poder judiciario"),
    (["sistema tributario nacional", "limitacoes do poder de tributar", "principios tributarios", "imunidades", "competencia tributaria"], "sistema tributario nacional limitacoes do poder de tributar competencia tributaria"),
    (["obrigacao tributaria", "fato gerador", "sujeito ativo", "sujeito passivo", "solidariedade", "domicilio tributario"], "obrigacao tributaria fato gerador"),
    (["responsabilidade tributaria", "sucessores", "terceiros", "infracoes", "denuncia espontanea"], "responsabilidade tributaria"),
    (["credito tributario", "lancamento", "modalidades de lancamento", "suspensao", "extincao", "exclusao", "prescricao", "decadencia", "isencao", "anistia"], "credito tributario lancamento suspensao extincao e exclusao do credito tributario"),
    (["garantias e privilegios", "administracao tributaria", "fiscalizacao", "divida ativa", "certidoes negativas"], "garantias e privilegios do credito tributario administracao tributaria"),
    (["estatistica descritiva", "media", "mediana", "moda", "variancia", "desvio padrao", "coeficiente de variacao", "assimetria", "curtose"], "estatistica descritiva medidas de posicao medidas de dispersao"),
    (["probabilidade", " condicional", "bayes", "binomial", "normal", "poisson", "variaveis aleatorias"], "probabilidade distribuicoes de probabilidade"),
    (["inferencia", "amostragem", "intervalo de confianca", "teste de hipoteses", "testes de hipoteses", "qui-quadrado", "anova"], "amostragem inferencia estatistica estimacao testes de hipoteses"),
    (["correlacao", "regressao linear", "minimos quadrados"], "correlacao e regressao"),
]


def remover_acentos(texto: str) -> str:
    if not texto:
        return ""
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def limpar_numeracao_edital(titulo: str) -> str:
    if not titulo:
        return ""
    t = titulo.strip()
    # Remove numeração inicial tipo "5.1 ", "10.4.1 - ", "I - "
    t = re.sub(r"^(?:\d+(?:\.\d+)*|[IVXLCDM]+)[\.\-\)\s]+", "", t, flags=re.IGNORECASE)
    return t.strip()


def normalizar_texto_topico(texto: str, manter_stop_words: bool = False) -> str:
    """
    Normaliza string para comparação:
    - Remove numeração de edital
    - Remove acentos e converte para caixa baixa
    - Remove caracteres especiais e múltiplos espaços
    - Remove stop words comuns de editais
    """
    sem_num = limpar_numeracao_edital(texto)
    sem_acento = remover_acentos(sem_num).lower()
    # Preserva números de leis importantes juntando pontos em números de leis (ex: 14.133 -> 14133)
    sem_acento = re.sub(r"(\d)\.(\d{3})", r"\1\2", sem_acento)
    limpo = re.sub(r"[^a-z0-9\s]", " ", sem_acento)
    tokens = [tok for tok in limpo.split() if tok]
    if not manter_stop_words:
        tokens = [
            tok for tok in tokens
            if tok not in STOP_WORDS_EDITAL and (len(tok) > 1 or tok.isdigit())
        ]
    return " ".join(tokens)


def expandir_termos_topico(texto_original: str, texto_normalizado: str) -> str:
    """
    Adiciona termos equivalentes da taxonomia do TEC quando o tópico do edital
    utiliza siglas ou jargões específicos da banca.
    """
    base_lower = remover_acentos(texto_original).lower()
    extras: List[str] = []
    for gatilhos, expansao in SINONIMOS_TERMOS_TEC:
        for g in gatilhos:
            # Verifica se o gatilho aparece como palavra/trecho relevante
            if len(g) <= 3:
                if re.search(rf"\b{re.escape(g)}\b", base_lower):
                    extras.append(expansao)
                    break
            else:
                if g in base_lower:
                    extras.append(expansao)
                    break
    if not extras:
        return texto_normalizado
    combinado = f"{texto_normalizado} {' '.join(extras)}"
    # Deduplica tokens preservando ordem
    vistos = []
    for tok in combinado.split():
        if tok not in vistos and tok not in STOP_WORDS_EDITAL:
            vistos.append(tok)
    return " ".join(vistos)


def _trigrams(s: str) -> Set[str]:
    if not s:
        return set()
    padded = f"  {s}  "
    return {padded[i:i + 3] for i in range(len(padded) - 2)}


def _similaridade_trigram(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    ta = _trigrams(a)
    tb = _trigrams(b)
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    union = len(ta | tb)
    return inter / union if union > 0 else 0.0


def obter_slugs_tec_para_disciplina(nome_disciplina: str) -> List[str]:
    """
    Identifica quais matérias do TEC Concursos correspondem à disciplina do edital.
    """
    nome_norm = remover_acentos(nome_disciplina or "").upper()
    slugs: List[str] = []
    for chaves, lista_slugs in MAPA_DISCIPLINA_PARA_SLUGS_TEC:
        if any(ch in nome_norm for ch in chaves):
            for s in lista_slugs:
                if s not in slugs:
                    slugs.append(s)
    return slugs


def calcular_similaridade_topico_no_tec(
    titulo_topico: str,
    norm_topico: str,
    expandido_topico: str,
    tokens_topico: Set[str],
    tokens_expandidos: Set[str],
    no_tec: Dict[str, Any]
) -> Tuple[float, str]:
    """
    Calcula o score de confiança (0.0 a 1.0) e o tipo de vínculo
    (`AUTOMATICO_EXATO` ou `AUTOMATICO_FUZZY`) entre um tópico do edital
    e um nó pré-processado da árvore do TEC Concursos.
    """
    norm_no = no_tec["norm_nome"]
    norm_caminho = no_tec["norm_caminho"]
    tokens_no = no_tec["tokens_nome"]
    tokens_caminho = no_tec["tokens_caminho"]

    if not norm_topico or not norm_no:
        return (0.0, "AUTOMATICO_FUZZY")

    # 1. Match Exato Normalizado
    if norm_topico == norm_no:
        return (1.0, "AUTOMATICO_EXATO")

    # Se o nome do nó está contido exatamente ou vice-versa e tem tamanho significativo
    if len(norm_no) >= 8 and (norm_no == norm_topico or (norm_no in norm_topico and len(norm_no) >= len(norm_topico) * 0.75)):
        return (0.96, "AUTOMATICO_EXATO")
    if len(norm_topico) >= 8 and norm_topico in norm_no and len(norm_topico) >= len(norm_no) * 0.75:
        return (0.95, "AUTOMATICO_EXATO")

    # 2. Overlap de Tokens Nucleares (direto e expandido)
    inter_direto = len(tokens_topico & tokens_no)
    inter_caminho = len(tokens_topico & tokens_caminho)
    inter_exp_no = len(tokens_expandidos & tokens_no)
    inter_exp_caminho = len(tokens_expandidos & tokens_caminho)

    recall_no = inter_direto / max(1, len(tokens_no))
    prec_topico = inter_direto / max(1, len(tokens_topico))
    f1_direto = (2 * recall_no * prec_topico / (recall_no + prec_topico)) if (recall_no + prec_topico) > 0 else 0.0

    recall_exp_no = inter_exp_no / max(1, len(tokens_no))
    cobertura_caminho = inter_exp_caminho / max(1, min(len(tokens_expandidos), 6))

    # 3. Similaridade de Trigramas e Sequência (Levenshtein / Ratcliff-Obershelp)
    sim_trigram_nome = _similaridade_trigram(norm_topico, norm_no)
    sim_trigram_exp = _similaridade_trigram(expandido_topico, norm_no)
    sim_seq = SequenceMatcher(None, norm_topico, norm_no).ratio()

    best_trigram = max(sim_trigram_nome, sim_trigram_exp * 0.95)

    # Combinação ponderada
    score_base = (
        (f1_direto * 0.36)
        + (recall_exp_no * 0.28)
        + (min(1.0, cobertura_caminho) * 0.16)
        + (best_trigram * 0.12)
        + (sim_seq * 0.08)
    )

    # Bônus se TODOS os tokens do nome do assunto do TEC aparecem no tópico (ou expansão)
    if len(tokens_no) >= 1 and tokens_no.issubset(tokens_topico):
        score_base = max(score_base, 0.92 + min(0.06, len(tokens_no) * 0.015))
    elif len(tokens_topico) >= 1 and tokens_topico.issubset(tokens_no):
        score_base = max(score_base, 0.91 + min(0.06, len(tokens_topico) * 0.015))
    elif len(tokens_no) >= 1 and tokens_no.issubset(tokens_expandidos):
        bonus_direto = 0.05 if inter_direto > 0 else 0.0
        score_base = max(score_base, 0.85 + bonus_direto + min(0.06, len(tokens_no) * 0.01))
    elif inter_exp_no >= 2 and recall_exp_no >= 0.65:
        bonus_direto = 0.04 if inter_direto > 0 else 0.0
        score_base = max(score_base, 0.78 + bonus_direto + (recall_exp_no * 0.14))
    elif inter_direto >= 1 and (recall_no >= 0.5 or prec_topico >= 0.5):
        score_base = max(score_base, 0.72 + max(recall_no, prec_topico) * 0.18)

    if inter_direto > 0:
        score_base += min(0.05, inter_direto * 0.02)

    # Ajustes finos por especificidade do nó na árvore do TEC
    nivel = no_tec["nivel"]
    if nivel == 1:
        # Nó de matéria inteira só deve ganhar se nada mais específico casar
        score_base *= 0.65
    elif nivel >= 3:
        score_base += 0.03

    # Penaliza tópicos genéricos "Questões Mescladas / Tópicos Residuais" do TEC
    if "mescladas" in norm_no or "residuais" in norm_no or "outros assuntos" in norm_no:
        score_base -= 0.18

    score_final = round(max(0.0, min(0.99, score_base)), 4)
    tipo = "AUTOMATICO_EXATO" if score_final >= 0.94 else "AUTOMATICO_FUZZY"
    return (score_final, tipo)


def _preparar_catalogo_nos_tec(nos_db: List[TecTaxonomia]) -> List[Dict[str, Any]]:
    catalogo = []
    for n in nos_db:
        norm_nome = normalizar_texto_topico(n.nome)
        norm_caminho = normalizar_texto_topico(n.caminho_completo)
        catalogo.append({
            "id": n.id,
            "tec_id": n.tec_id,
            "is_materia": bool(n.is_materia),
            "materia_tec_id": n.materia_tec_id,
            "nome": n.nome,
            "caminho_completo": n.caminho_completo,
            "slug_url": n.slug_url or "",
            "nivel": n.nivel_profundidade,
            "total_questoes": n.total_questoes or 0,
            "norm_nome": norm_nome,
            "norm_caminho": norm_caminho,
            "tokens_nome": set(norm_nome.split()),
            "tokens_caminho": set(norm_caminho.split()),
            "obj": n,
        })
    return catalogo


async def reconciliar_topicos_via_ia_gemini(
    api_key: str,
    disciplina_nome: str,
    topicos_ambiguos: List[Dict[str, Any]],
    candidatos_tec: List[Dict[str, Any]],
    timeout_segundos: float = 25.0
) -> Dict[int, Tuple[int, float]]:
    """
    Usa o motor Google Gemini para reconciliar semanticamente tópicos do edital
    cuja terminologia diverge nominalmente da árvore do TEC Concursos.
    Retorna dict: {topico_id: (tec_taxonomia_db_id, confianca_score)}
    """
    if not api_key or not topicos_ambiguos or not candidatos_tec:
        return {}

    # Limita a lista de candidatos enviada ao prompt aos nós de assuntos da matéria (máx 120)
    catalogo_enxuto = [
        {
            "db_id": c["id"],
            "caminho": c["caminho_completo"],
            "questoes": c["total_questoes"]
        }
        for c in candidatos_tec[:120]
    ]

    prompt = f"""Você é um Especialista em Taxonomia de Concursos Públicos e na plataforma TEC Concursos.
Sua tarefa é fazer o mapeamento De-Para semântico entre os tópicos do edital da disciplina "{disciplina_nome}" e os nós da árvore oficial de assuntos do TEC Concursos.

TÓPICOS DO EDITAL PARA VINCULAR:
{json.dumps(topicos_ambiguos, ensure_ascii=False)}

NÓS DISPONÍVEIS NA ÁRVORE DO TEC CONCURSOS PARA ESTA DISCIPLINA:
{json.dumps(catalogo_enxuto, ensure_ascii=False)}

REGRAS:
1. Para cada tópico do edital, escolha o `db_id` do nó do TEC Concursos que melhor corresponde ao assunto que o aluno deve resolver questões.
2. Exemplo: "Reforma Tributária / IBS / CBS / EC 132" corresponde a "Sistema Tributário Nacional" ou "Reforma Tributária" ou "Competência Tributária / ICMS"; "Firewall e WAF" corresponde a "Conceitos de Firewall, Proxy e DMZ" ou "Dispositivos de Segurança de Perímetro".
3. Atribua um `confianca_score` entre 0.85 e 0.98 refletindo a aderência pedagógica.

RETORNE ESTRITAMENTE UM JSON VÁLIDO NO FORMATO:
{{
  "mapeamentos": [
    {{
      "topico_id": 123,
      "db_id": 456,
      "confianca_score": 0.92
    }}
  ]
}}"""

    modelos = ["gemini-3.5-flash-lite", "gemini-flash-lite-latest", "gemini-3.8-flash"]
    ids_validos = {c["id"] for c in candidatos_tec}

    async with httpx.AsyncClient(timeout=timeout_segundos) as client:
        for mod in modelos:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{mod}:generateContent?key={api_key}"
                payload = {
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "responseMimeType": "application/json",
                        "temperature": 0.15
                    }
                }
                resp = await client.post(url, json=payload)
                if resp.status_code == 200:
                    texto = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                    if texto.startswith("```json"):
                        texto = texto[7:]
                    if texto.startswith("```"):
                        texto = texto[3:]
                    if texto.endswith("```"):
                        texto = texto[:-3]
                    parsed = json.loads(texto.strip())
                    resultado: Dict[int, Tuple[int, float]] = {}
                    for item in parsed.get("mapeamentos", []):
                        t_id = item.get("topico_id")
                        db_id = item.get("db_id")
                        sc = float(item.get("confianca_score") or 0.88)
                        if t_id and db_id in ids_validos:
                            resultado[int(t_id)] = (int(db_id), round(min(0.99, max(0.85, sc)), 4))
                    return resultado
                elif resp.status_code in (400, 401, 403):
                    break
            except Exception as exc:
                print(f"[TEC IA MATCH] Aviso com {mod}: {exc}")
                continue
    return {}


async def executar_matching_edital(
    db: Session,
    edital_id: int,
    sobrescrever_manuais: bool = False,
    usar_ia_se_necessario: bool = True
) -> Dict[str, Any]:
    """
    Executa o Mecanismo de Matching De-Para completo (Heurística + Fuzzy + IA Gemini)
    para todos os tópicos de um edital verticalizado.
    """
    edital = db.query(Edital).filter(Edital.id == edital_id).first()
    if not edital:
        raise ValueError(f"Edital {edital_id} não encontrado.")

    todos_nos_db = db.query(TecTaxonomia).filter(TecTaxonomia.ativo == True).all()
    if not todos_nos_db:
        raise ValueError("A tabela `tec_taxonomia` está vazia. Execute a sincronização da árvore do TEC primeiro.")

    catalogo_global = _preparar_catalogo_nos_tec(todos_nos_db)
    # Agrupa por slug de matéria (primeiro segmento do slug_url)
    nos_por_slug_materia: Dict[str, List[Dict[str, Any]]] = {}
    for item in catalogo_global:
        slug_raiz = (item["slug_url"].split("/")[0] if item["slug_url"] else "").strip()
        if slug_raiz:
            nos_por_slug_materia.setdefault(slug_raiz, []).append(item)

    # Obtém chave Gemini se disponível para fallback semântico
    cfg = db.query(ConfiguracaoPainelProva).first()
    api_key = (
        (cfg.gemini_api_key.strip() if cfg and getattr(cfg, "gemini_api_key", None) else "")
        or os.getenv("GEMINI_API_KEY", "").strip()
    )

    vinculos_atuais = {
        v.topico_id: v
        for v in db.query(TopicoEstudoTecDePara).all()
    }

    now = datetime.now(timezone.utc)
    resumo = {
        "edital_id": edital.id,
        "total_topicos": 0,
        "vinculados_exatos": 0,
        "vinculados_fuzzy": 0,
        "vinculados_ia": 0,
        "preservados_manuais": 0,
        "alta_confianca_85": 0,
    }

    for disc in edital.disciplinas:
        if disc.categoria == "REVISAO_ANKI" or disc.nome == "REVISÃO ANKI" or not disc.topicos:
            continue

        slugs_alvo = obter_slugs_tec_para_disciplina(disc.nome)
        candidatos_disc: List[Dict[str, Any]] = []
        for s in slugs_alvo:
            candidatos_disc.extend(nos_por_slug_materia.get(s, []))

        if not candidatos_disc:
            candidatos_disc = catalogo_global

        # Filtra prioritariamente assuntos (nivel >= 2) para evitar vincular tudo à raiz da matéria
        candidatos_assuntos = [c for c in candidatos_disc if not c["is_materia"]]
        if not candidatos_assuntos:
            candidatos_assuntos = candidatos_disc

        melhores_por_topico: Dict[int, Tuple[Dict[str, Any], float, str]] = {}
        ambiguos_para_ia: List[Dict[str, Any]] = []

        for topico in disc.topicos:
            resumo["total_topicos"] += 1
            v_existente = vinculos_atuais.get(topico.id)
            if v_existente and v_existente.tipo_vinculo == "MANUAL" and not sobrescrever_manuais:
                resumo["preservados_manuais"] += 1
                resumo["alta_confianca_85"] += 1
                continue

            norm_t = normalizar_texto_topico(topico.titulo)
            exp_t = expandir_termos_topico(topico.titulo, norm_t)
            tokens_t = set(norm_t.split())
            tokens_exp = set(exp_t.split())

            melhor_no = None
            melhor_score = -1.0
            melhor_tipo = "AUTOMATICO_FUZZY"

            for cand in candidatos_assuntos:
                sc, tp = calcular_similaridade_topico_no_tec(
                    titulo_topico=topico.titulo,
                    norm_topico=norm_t,
                    expandido_topico=exp_t,
                    tokens_topico=tokens_t,
                    tokens_expandidos=tokens_exp,
                    no_tec=cand
                )
                if sc > melhor_score or (sc == melhor_score and melhor_no and cand["total_questoes"] > melhor_no["total_questoes"]):
                    melhor_score = sc
                    melhor_no = cand
                    melhor_tipo = tp

            # Fallback se nenhum assunto pontuou acima de 0.35: usa o nó raiz da matéria ou o melhor candidato
            if not melhor_no or melhor_score < 0.35:
                no_materia_raiz = next((c for c in candidatos_disc if c["is_materia"]), candidatos_assuntos[0])
                melhor_no = melhor_no or no_materia_raiz
                melhor_score = max(melhor_score, 0.55)
                melhor_tipo = "AUTOMATICO_FUZZY"

            melhores_por_topico[topico.id] = (melhor_no, melhor_score, melhor_tipo)

            if melhor_score < 0.85:
                ambiguos_para_ia.append({
                    "topico_id": topico.id,
                    "titulo": topico.titulo,
                    "sugestao_heuristica": melhor_no["caminho_completo"],
                    "score_heuristico": melhor_score
                })

        # Se houver tópicos com score < 0.85 e IA habilitada/disponível, consulta o Gemini
        mapa_ia: Dict[int, Tuple[int, float]] = {}
        if usar_ia_se_necessario and api_key and ambiguos_para_ia:
            mapa_ia = await reconciliar_topicos_via_ia_gemini(
                api_key=api_key,
                disciplina_nome=disc.nome,
                topicos_ambiguos=ambiguos_para_ia,
                candidatos_tec=candidatos_assuntos
            )

        mapa_cand_por_id = {c["id"]: c for c in candidatos_disc}

        for topico_id, (no_escolhido, score_h, tipo_h) in melhores_por_topico.items():
            if topico_id in mapa_ia:
                db_id_ia, score_ia = mapa_ia[topico_id]
                if db_id_ia in mapa_cand_por_id:
                    no_escolhido = mapa_cand_por_id[db_id_ia]
                    score_h = score_ia
                    tipo_h = "AUTOMATICO_IA"

            validado_auto = bool(score_h >= 0.85)
            if validado_auto:
                resumo["alta_confianca_85"] += 1

            if tipo_h == "AUTOMATICO_EXATO":
                resumo["vinculados_exatos"] += 1
            elif tipo_h == "AUTOMATICO_IA":
                resumo["vinculados_ia"] += 1
            else:
                resumo["vinculados_fuzzy"] += 1

            v_atual = vinculos_atuais.get(topico_id)
            if not v_atual:
                novo_v = TopicoEstudoTecDePara(
                    topico_id=topico_id,
                    tec_taxonomia_id=no_escolhido["id"],
                    tipo_vinculo=tipo_h,
                    confianca_score=score_h,
                    validado=validado_auto,
                    updated_at=now
                )
                db.add(novo_v)
                vinculos_atuais[topico_id] = novo_v
            else:
                v_atual.tec_taxonomia_id = no_escolhido["id"]
                v_atual.tipo_vinculo = tipo_h
                v_atual.confianca_score = score_h
                v_atual.validado = validado_auto
                v_atual.updated_at = now

    db.commit()
    return resumo


def _obter_banca_ativa_para_topico(topico: Topico) -> Optional[str]:
    """
    Recupera o nome da banca ativa a partir do edital vinculado ao tópico
    ou da configuração ativa do painel de provas.
    """
    try:
        disc = getattr(topico, "disciplina", None)
        if disc and getattr(disc, "edital", None):
            banca = disc.edital.ia_trilha_banca
            if banca and str(banca).strip():
                return str(banca).strip()
    except Exception:
        pass

    try:
        from app.database import SessionLocal
        with SessionLocal() as db_session:
            cfg = db_session.query(ConfiguracaoPainelProva).first()
            if cfg and cfg.banca and str(cfg.banca).strip():
                return str(cfg.banca).strip()
    except Exception:
        pass

    return None


def montar_dados_vinculo_topico(
    topico: Topico,
    vinculo: Optional[TopicoEstudoTecDePara] = None,
    banca_nome: Optional[str] = None
) -> Dict[str, Any]:
    """
    Serviço utilitário que recebe o Tópico e seu vínculo `TopicoEstudoTecDePara`,
    recupera os parâmetros do nó TEC mapeado e monta as URLs dinâmicas:
    - `url_caderno`: caderno de questões direto já filtrado pelo tópico e pela banca ativa.
    - `url_tec`: atalho primário apontando para o caderno de questões com banca.
    - `url_assunto`: página teórica do assunto no TEC Concursos.
    - `url_fallback_busca`: busca textual caso não haja vínculo mapeado.
    """
    from app.services.tec_bancas_catalog import resolver_banca_tec

    # 1. Resolução da banca examinadora ativa no TEC
    banca_str = banca_nome or _obter_banca_ativa_para_topico(topico)
    banca_info = resolver_banca_tec(banca_str)
    banca_tec_id = banca_info["id"] if banca_info else None
    banca_tec_nome = banca_info["nome"] if banca_info else (banca_str if banca_str else None)

    termo_limpo = limpar_numeracao_edital(topico.titulo or "")
    palavras_busca = [p for p in re.split(r"[,:;()\-/]", termo_limpo)[0].split() if len(p) > 2][:5]
    query_fallback = quote_plus(" ".join(palavras_busca) if palavras_busca else termo_limpo[:40])
    url_fallback = f"{TEC_BASE_URL}/materias/?filtro={query_fallback}&incluirAssuntos=true"

    if banca_tec_id:
        url_caderno_fallback = f"{TEC_BASE_URL}/questoes/cadernos/novo/?banca_ids[]={banca_tec_id}"
    else:
        url_caderno_fallback = f"{TEC_BASE_URL}/questoes/cadernos/novo/"

    v = vinculo if vinculo is not None else getattr(topico, "vinculo_tec", None)
    if not v or not v.tec_taxonomia:
        return {
            "vinculado": False,
            "topico_id": topico.id,
            "tec_taxonomia_id": None,
            "tec_id": None,
            "materia_tec_id": None,
            "nome_assunto_tec": None,
            "caminho_completo": None,
            "hierarquia_tec": None,
            "tipo_vinculo": None,
            "confianca_score": 0.0,
            "validado": False,
            "total_questoes": 0,
            "banca_nome": banca_tec_nome,
            "banca_tec_id": banca_tec_id,
            "caderno_id": None,
            "url_caderno_criado": None,
            "pasta_tec_nome": None,
            "tem_caderno_gerado": False,
            "url_tec": url_fallback,
            "url_materia_exercicios": url_fallback,
            "url_assunto": url_fallback,
            "url_caderno": url_fallback,
            "url_fallback_busca": url_fallback,
        }

    no: TecTaxonomia = v.tec_taxonomia
    payload = {}
    if no.url_params_payload:
        try:
            payload = json.loads(no.url_params_payload)
        except Exception:
            payload = {}

    slug_limpo = (no.slug_url or payload.get("slug_url") or "").lstrip("/")

    # 1. Determina ID da matéria e ID do assunto no TEC
    materia_id = no.materia_tec_id or (no.tec_id if no.is_materia else 69)
    assunto_id = no.tec_id

    # 2. Constrói a URL nativa do TEC para abrir os exercícios com a banca filtrada:
    # Ex: https://www.tecconcursos.com.br/aulas/materias/69/assuntos/6228?exercicio=1&filtroAno=&filtroBanca=4
    param_banca = f"&filtroBanca={banca_tec_id}" if banca_tec_id else ""
    if not no.is_materia:
        url_materia_exercicios = f"{TEC_BASE_URL}/aulas/materias/{materia_id}/assuntos/{assunto_id}?exercicio=1&filtroAno={param_banca}"
        url_teoria_direta = f"{TEC_BASE_URL}/aulas/materias/{materia_id}/assuntos/{assunto_id}"
    else:
        url_materia_exercicios = f"{TEC_BASE_URL}/materias/{slug_limpo}" if slug_limpo else url_fallback
        url_teoria_direta = url_materia_exercicios

    url_assunto = payload.get("url_direta") or (f"{TEC_BASE_URL}/materias/{slug_limpo}" if slug_limpo else url_teoria_direta)

    # 3. Dois comportamentos:
    # - Se o usuário inseriu/vinculou um caderno manualmente: url_tec abre o caderno (/questoes/cadernos/{caderno_id})
    # - Se NÃO houver caderno manual inserido: url_tec abre diretamente as questões da matéria com a banca filtrada
    caderno_id_efetivo = getattr(v, "caderno_id", None)
    url_caderno_criado_efetivo = getattr(v, "url_caderno_criado", None)
    pasta_tec_efetiva = getattr(v, "pasta_tec_nome", None)
    tem_caderno = bool(caderno_id_efetivo)

    if tem_caderno:
        url_tec_final = url_caderno_criado_efetivo or f"{TEC_BASE_URL}/questoes/cadernos/{caderno_id_efetivo}"
    else:
        url_tec_final = url_materia_exercicios

    return {
        "vinculado": True,
        "topico_id": topico.id,
        "tec_taxonomia_id": no.id,
        "tec_id": no.tec_id,
        "materia_tec_id": materia_id,
        "is_materia": bool(no.is_materia),
        "nome_assunto_tec": no.nome,
        "caminho_completo": no.caminho_completo,
        "hierarquia_tec": no.hierarquia_tec,
        "tipo_vinculo": v.tipo_vinculo,
        "confianca_score": round(float(v.confianca_score or 0.0), 4),
        "validado": bool(v.validado or (v.confianca_score or 0.0) >= 0.85 or v.tipo_vinculo == "MANUAL"),
        "total_questoes": int(no.total_questoes or payload.get("total_questoes") or 0),
        "banca_nome": banca_tec_nome,
        "banca_tec_id": banca_tec_id,
        "caderno_id": caderno_id_efetivo,
        "url_caderno_criado": url_caderno_criado_efetivo,
        "pasta_tec_nome": pasta_tec_efetiva,
        "tem_caderno_gerado": tem_caderno,
        "url_tec": url_tec_final,  # Comportamento 1 (link da matéria+banca) ou Comportamento 2 (caderno manual)
        "url_materia_exercicios": url_materia_exercicios,
        "url_assunto": url_assunto,  # Página da matéria / aula teórica
        "url_caderno": url_tec_final,
        "url_fallback_busca": url_fallback,
    }
