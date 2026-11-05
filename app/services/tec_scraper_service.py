import re
import json
import time
import asyncio
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple, Set
import httpx
from sqlalchemy.orm import Session

from app.models.tec_taxonomia import TecTaxonomia

TEC_BASE_URL = "https://www.tecconcursos.com.br"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
}

# Catálogo base das matérias essenciais do TEC Concursos (Fiscal, TI, Controle, Geral)
SLUGS_MATERIAS_PADRAO: List[str] = [
    "matematica-financeira",
    "direito-constitucional-cf1988-e-doutrina",
    "direito-administrativo-doutrina-e-leis-federais",
    "contabilidade-geral",
    "direito-tributario",
    "estatistica",
    "afo-direito-financeiro-e-contabilidade-publica",
    "economia-e-financas-publicas",
    "legislacao-tributaria-dos-estados-e-do-distrito-federal",
    "legislacao-tributaria-federal",
    "ti-ciencia-de-dados-e-inteligencia-artificial",
    "ti-desenvolvimento-de-sistemas",
    "ti-engenharia-de-software",
    "ti-seguranca-da-informacao",
    "ti-redes-de-computadores",
    "ti-banco-de-dados",
    "ti-gestao-e-governanca-de-ti",
    "ti-sistemas-operacionais",
    "ti-organizacao-e-arquitetura-dos-computadores",
    "auditoria-governamental-e-controle",
    "auditoria-privada",
    "lingua-portuguesa-portugues",
    "raciocinio-logico",
    "direito-previdenciario",
    "informatica",
]


def _extrair_json_materia_do_html(html: str) -> Optional[Dict[str, Any]]:
    """
    Faz o parse do objeto `var jsonMateria = {...};` embutido na página pública
    de matéria do TEC Concursos (`/materias/{slug}`).
    """
    if not html:
        return None
    match = re.search(r"var\s+jsonMateria\s*=\s*(\{.*?\});\s*</script>", html, re.S)
    if not match:
        match = re.search(r"var\s+jsonMateria\s*=\s*(\{.*\});", html)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except Exception as exc:
        print(f"[TEC SCRAPER] Erro ao decodificar jsonMateria: {exc}")
        return None


async def buscar_slugs_materia_por_filtro(
    client: httpx.AsyncClient,
    termo_busca: str,
    max_resultados: int = 3
) -> List[str]:
    """
    Consulta a busca pública `/materias/?filtro=...` do TEC Concursos para descobrir
    novos slugs de matérias que não estejam no catálogo padrão.
    """
    try:
        resp = await client.get(
            f"{TEC_BASE_URL}/materias/",
            params={"filtro": termo_busca, "incluirAssuntos": "false"},
            headers=DEFAULT_HEADERS,
            follow_redirects=True
        )
        if resp.status_code != 200:
            return []
        links = re.findall(
            r'href=["\'](?:https://www\.tecconcursos\.com\.br)?/materias/([a-z0-9\-]+)["\']',
            resp.text
        )
        vistos: List[str] = []
        for s in links:
            if s and s not in vistos:
                vistos.append(s)
            if len(vistos) >= max_resultados:
                break
        return vistos
    except Exception as exc:
        print(f"[TEC SCRAPER] Aviso ao buscar filtro '{termo_busca}': {exc}")
        return []


async def baixar_arvore_materia_tec(
    client: httpx.AsyncClient,
    slug: str,
    max_tentativas: int = 3,
    delay_base: float = 0.35
) -> Optional[Dict[str, Any]]:
    """
    Extrai o `jsonMateria` completo de uma disciplina do TEC Concursos com
    rate limiting defensivo e retry exponencial.
    """
    url = f"{TEC_BASE_URL}/materias/{slug.strip('/')}"
    for tentativa in range(1, max_tentativas + 1):
        try:
            await asyncio.sleep(delay_base)
            resp = await client.get(url, headers=DEFAULT_HEADERS, follow_redirects=True)
            if resp.status_code == 200:
                dados = _extrair_json_materia_do_html(resp.text)
                if dados and dados.get("id"):
                    return dados
                return None
            if resp.status_code in (429, 500, 502, 503, 504):
                espera = delay_base * (2 ** tentativa)
                print(f"[TEC SCRAPER] HTTP {resp.status_code} em {slug}. Aguardando {espera:.1f}s (tentativa {tentativa})...")
                await asyncio.sleep(espera)
                continue
            print(f"[TEC SCRAPER] Status inesperado {resp.status_code} ao acessar {url}")
            return None
        except Exception as exc:
            espera = delay_base * (2 ** tentativa)
            print(f"[TEC SCRAPER] Erro de rede em {slug} (tentativa {tentativa}): {exc}")
            await asyncio.sleep(espera)
    return None


def _montar_payload_url(
    tec_id: int,
    materia_id: int,
    slug_url: Optional[str],
    hierarquia: Optional[str],
    descendentes: Optional[str],
    total_questoes: int,
    total_comentadas: int = 0,
    total_aulas: int = 0,
    is_materia: bool = False
) -> str:
    slug_limpo = (slug_url or "").lstrip("/")
    url_direta = f"{TEC_BASE_URL}/materias/{slug_limpo}" if slug_limpo else f"{TEC_BASE_URL}/materias"
    if is_materia:
        url_caderno = f"{TEC_BASE_URL}/questoes/cadernos/novo?materia_ids[]={tec_id}"
    else:
        url_caderno = f"{TEC_BASE_URL}/questoes/cadernos/novo?assunto_ids[]={tec_id}"

    payload = {
        "tec_id": tec_id,
        "id_materia": materia_id,
        "is_materia": is_materia,
        "hierarquia": hierarquia,
        "slug_url": slug_limpo,
        "descendentes": descendentes,
        "url_direta": url_direta,
        "url_caderno": url_caderno,
        "query_param": f"materia_ids[]={tec_id}" if is_materia else f"assunto_ids[]={tec_id}",
        "total_questoes": total_questoes,
        "total_comentadas": total_comentadas,
        "total_aulas": total_aulas,
    }
    return json.dumps(payload, ensure_ascii=False)


def persistir_arvore_materia_idempotente(
    db: Session,
    json_materia: Dict[str, Any],
    cache_existentes: Optional[Dict[Tuple[int, bool], TecTaxonomia]] = None
) -> Dict[str, int]:
    """
    Salva/atualiza de forma idempotente a matéria (Nível 1) e toda a sua árvore
    recursiva de assuntos e subassuntos (Níveis 2, 3, 4+) na tabela `tec_taxonomia`.
    Detecta nós novos, renomeados ou descontinuados.
    """
    now = datetime.now(timezone.utc)
    materia_tec_id = int(json_materia["id"])
    materia_nome = (json_materia.get("nome") or "").strip()
    materia_slug = (json_materia.get("url") or "").strip()
    materia_questoes = int(json_materia.get("totalQuestoes") or 0)
    materia_comentadas = int(json_materia.get("totalQuestoesComentadas") or 0)
    materia_aulas = int(json_materia.get("totalAulas") or 0)

    if cache_existentes is None:
        nos_materia = (
            db.query(TecTaxonomia)
            .filter(TecTaxonomia.materia_tec_id == materia_tec_id)
            .all()
        )
        cache_existentes = {(n.tec_id, bool(n.is_materia)): n for n in nos_materia}

    stats = {"inseridos": 0, "atualizados": 0, "descontinuados": 0, "total_nos": 0}
    chaves_vistas: Set[Tuple[int, bool]] = set()

    # 1. Upsert do Nó Raiz (Nível 1: Disciplina / Matéria)
    chave_raiz = (materia_tec_id, True)
    chaves_vistas.add(chave_raiz)
    payload_raiz = _montar_payload_url(
        tec_id=materia_tec_id,
        materia_id=materia_tec_id,
        slug_url=materia_slug,
        hierarquia="00",
        descendentes=None,
        total_questoes=materia_questoes,
        total_comentadas=materia_comentadas,
        total_aulas=materia_aulas,
        is_materia=True
    )

    no_raiz = cache_existentes.get(chave_raiz)
    if not no_raiz:
        no_raiz = (
            db.query(TecTaxonomia)
            .filter(TecTaxonomia.tec_id == materia_tec_id, TecTaxonomia.is_materia == True)
            .first()
        )

    if not no_raiz:
        no_raiz = TecTaxonomia(
            tec_id=materia_tec_id,
            is_materia=True,
            materia_tec_id=materia_tec_id,
            nome=materia_nome,
            parent_id=None,
            nivel_profundidade=1,
            hierarquia_tec="00",
            caminho_completo=materia_nome,
            slug_url=materia_slug,
            total_questoes=materia_questoes,
            url_params_payload=payload_raiz,
            ativo=True,
            updated_at=now
        )
        db.add(no_raiz)
        db.flush()
        cache_existentes[chave_raiz] = no_raiz
        stats["inseridos"] += 1
    else:
        no_raiz.nome = materia_nome
        no_raiz.materia_tec_id = materia_tec_id
        no_raiz.parent_id = None
        no_raiz.nivel_profundidade = 1
        no_raiz.caminho_completo = materia_nome
        no_raiz.slug_url = materia_slug
        no_raiz.total_questoes = materia_questoes
        no_raiz.url_params_payload = payload_raiz
        no_raiz.ativo = True
        no_raiz.updated_at = now
        db.flush()
        stats["atualizados"] += 1

    stats["total_nos"] += 1

    # 2. Função recursiva para Assuntos (Nível 2) e Subassuntos (Nível 3+)
    def _processar_filhos(
        lista_assuntos: List[Dict[str, Any]],
        parent_db_id: int,
        caminho_pai: str,
        nivel: int
    ):
        for item in lista_assuntos:
            raw_id = item.get("id")
            if raw_id is None:
                # Ignora linha sintética "Sem Classificação de Assunto" sem ID
                continue

            assunto_tec_id = int(raw_id)
            nome_assunto = (item.get("nome") or "").strip()
            hierarquia = item.get("hierarquia")
            slug_assunto = item.get("url")
            descendentes = item.get("descendentes")
            t_questoes = int(item.get("totalQuestoes") or 0)
            t_comentadas = int(item.get("totalComentadas") or 0)
            t_aulas = int(item.get("totalAulas") or 0)

            caminho_atual = f"{caminho_pai} > {nome_assunto}"
            chave_no = (assunto_tec_id, False)
            chaves_vistas.add(chave_no)

            payload_str = _montar_payload_url(
                tec_id=assunto_tec_id,
                materia_id=materia_tec_id,
                slug_url=slug_assunto,
                hierarquia=hierarquia,
                descendentes=descendentes,
                total_questoes=t_questoes,
                total_comentadas=t_comentadas,
                total_aulas=t_aulas,
                is_materia=False
            )

            no_db = cache_existentes.get(chave_no)
            if not no_db:
                no_db = TecTaxonomia(
                    tec_id=assunto_tec_id,
                    is_materia=False,
                    materia_tec_id=materia_tec_id,
                    nome=nome_assunto,
                    parent_id=parent_db_id,
                    nivel_profundidade=nivel,
                    hierarquia_tec=hierarquia,
                    caminho_completo=caminho_atual,
                    slug_url=slug_assunto,
                    total_questoes=t_questoes,
                    url_params_payload=payload_str,
                    ativo=True,
                    updated_at=now
                )
                db.add(no_db)
                db.flush()
                cache_existentes[chave_no] = no_db
                stats["inseridos"] += 1
            else:
                no_db.nome = nome_assunto
                no_db.materia_tec_id = materia_tec_id
                no_db.parent_id = parent_db_id
                no_db.nivel_profundidade = nivel
                no_db.hierarquia_tec = hierarquia
                no_db.caminho_completo = caminho_atual
                no_db.slug_url = slug_assunto
                no_db.total_questoes = t_questoes
                no_db.url_params_payload = payload_str
                no_db.ativo = True
                no_db.updated_at = now
                stats["atualizados"] += 1

            stats["total_nos"] += 1

            filhos = item.get("filhos") or []
            if filhos:
                _processar_filhos(filhos, no_db.id, caminho_atual, nivel + 1)

    _processar_filhos(
        lista_assuntos=json_materia.get("assuntos") or [],
        parent_db_id=no_raiz.id,
        caminho_pai=materia_nome,
        nivel=2
    )

    # 3. Marca como descontinuados (ativo=False) os nós daquela matéria que sumiram do TEC
    for chave_antiga, no_antigo in list(cache_existentes.items()):
        if no_antigo.materia_tec_id == materia_tec_id and chave_antiga not in chaves_vistas:
            if no_antigo.ativo:
                no_antigo.ativo = False
                no_antigo.updated_at = now
                stats["descontinuados"] += 1

    return stats


async def sincronizar_taxonomia_tec(
    db: Session,
    slugs_adicionais: Optional[List[str]] = None,
    delay_entre_requisicoes: float = 0.25
) -> Dict[str, Any]:
    """
    Executa o job completo de sincronização da Árvore de Taxonomia do TEC Concursos.
    É totalmente idempotente e seguro para execuções periódicas.
    """
    inicio = time.time()
    slugs_para_baixar = list(dict.fromkeys(SLUGS_MATERIAS_PADRAO + (slugs_adicionais or [])))

    # Pré-carrega todo o cache existente no banco para evitar N+1 queries
    todos_existentes = db.query(TecTaxonomia).all()
    cache_global: Dict[Tuple[int, bool], TecTaxonomia] = {
        (n.tec_id, bool(n.is_materia)): n for n in todos_existentes
    }

    resumo = {
        "materias_processadas": 0,
        "materias_Com_erro": 0,
        "nos_inseridos": 0,
        "nos_atualizados": 0,
        "nos_descontinuados": 0,
        "total_nos_processados": 0,
        "detalhes_materias": [],
    }

    async with httpx.AsyncClient(timeout=25.0) as client:
        for slug in slugs_para_baixar:
            json_mat = await baixar_arvore_materia_tec(
                client=client,
                slug=slug,
                delay_base=delay_entre_requisicoes
            )
            if not json_mat:
                resumo["materias_Com_erro"] += 1
                continue

            st = persistir_arvore_materia_idempotente(db, json_mat, cache_global)
            db.commit()

            resumo["materias_processadas"] += 1
            resumo["nos_inseridos"] += st["inseridos"]
            resumo["nos_atualizados"] += st["atualizados"]
            resumo["nos_descontinuados"] += st["descontinuados"]
            resumo["total_nos_processados"] += st["total_nos"]
            resumo["detalhes_materias"].append({
                "tec_id": json_mat.get("id"),
                "nome": json_mat.get("nome"),
                "slug": slug,
                "total_nos": st["total_nos"],
                "inseridos": st["inseridos"],
                "atualizados": st["atualizados"]
            })

    resumo["tempo_segundos"] = round(time.time() - inicio, 2)
    return resumo
