import json
import re
import unicodedata
from pathlib import Path
from typing import Optional, Dict, Any, List

_BANCAS_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "bancas_tec.json"
if not _BANCAS_PATH.exists():
    _BANCAS_PATH = Path(__file__).resolve().parent.parent / "data" / "bancas_tec.json"

_BANCAS_TEC: List[Dict[str, Any]] = []
_MAPA_EXATO: Dict[str, int] = {}
_MAPA_NOMES: Dict[int, str] = {}


def _normalizar(s: str) -> str:
    if not s:
        return ""
    nfkd = unicodedata.normalize("NFKD", s)
    sem_acento = "".join(c for c in nfkd if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]", "", sem_acento)


ALIAS_BANCAS: Dict[str, int] = {
    "cebraspe": 4,
    "cespe": 4,
    "cespeunb": 4,
    "fcc": 3,
    "carloschagas": 3,
    "fundacaocarloschagas": 3,
    "fgv": 5,
    "getulio": 5,
    "fundacaogetuliovargas": 5,
    "vunesp": 6,
    "fundacaovunesp": 6,
    "ibfc": 92,
    "idecan": 95,
    "aocp": 79,
    "institutoaocp": 106,
    "quadrix": 125,
    "institutoquadrix": 125,
    "iades": 108,
    "consulplan": 36,
    "institutoconsulplan": 37,
    "fundatec": 110,
    "fepese": 69,
    "funcab": 77,
    "fapec": 242,
    "fundep": 213,
    "selecon": 501,
}


def _carregar_catalogo_bancas():
    global _BANCAS_TEC, _MAPA_EXATO, _MAPA_NOMES
    if _BANCAS_TEC:
        return
    if _BANCAS_PATH.exists():
        try:
            with open(_BANCAS_PATH, "r", encoding="utf-8") as f:
                _BANCAS_TEC = json.load(f)
            for b in _BANCAS_TEC:
                b_id = b["id"]
                _MAPA_NOMES[b_id] = b.get("banca") or b.get("nome") or str(b_id)
                for field in ["banca", "nome", "url"]:
                    val = b.get(field)
                    if val:
                        norm = _normalizar(val)
                        if norm:
                            _MAPA_EXATO[norm] = b_id
        except Exception as e:
            print(f"[TEC BANCAS] Erro ao carregar catalogo: {e}")


def resolver_banca_tec(nome_banca: Optional[str]) -> Optional[Dict[str, Any]]:
    """
    Retorna o dicionário com {'id': int, 'nome': str} da banca correspondente
    no TEC Concursos, ou None se não for encontrada.
    """
    if not nome_banca:
        return None
    _carregar_catalogo_bancas()
    norm = _normalizar(nome_banca)
    if not norm:
        return None

    # 1. Alias rápido
    if norm in ALIAS_BANCAS:
        b_id = ALIAS_BANCAS[norm]
        return {"id": b_id, "nome": _MAPA_NOMES.get(b_id, nome_banca)}

    # 2. Match Exato no índice
    if norm in _MAPA_EXATO:
        b_id = _MAPA_EXATO[norm]
        return {"id": b_id, "nome": _MAPA_NOMES.get(b_id, nome_banca)}

    # 3. Substring em aliases
    for alias, b_id in ALIAS_BANCAS.items():
        if alias in norm or norm in alias:
            return {"id": b_id, "nome": _MAPA_NOMES.get(b_id, nome_banca)}

    # 4. Substring no catálogo completo
    for b in _BANCAS_TEC:
        b_norm = _normalizar(b.get("nome", ""))
        if norm in b_norm or b_norm in norm:
            b_id = b["id"]
            return {"id": b_id, "nome": b.get("nome", nome_banca)}

    return None
