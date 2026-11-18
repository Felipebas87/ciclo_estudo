import json
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, Query, Body
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.configuracao_prova import ConfiguracaoPainelProva
from app.services.revisoes_service import diagnosticar_fila_revisoes_anki

router = APIRouter(prefix="/api/revisoes", tags=["Central de Revisões & Anki"])


def _obter_ou_criar_config(db: Session) -> ConfiguracaoPainelProva:
    cfg = db.query(ConfiguracaoPainelProva).first()
    if not cfg:
        cfg = ConfiguracaoPainelProva(id=1)
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
    return cfg


@router.get("")
def obter_central_revisoes(
    edital_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    dados = diagnosticar_fila_revisoes_anki(db=db, edital_id=edital_id)
    cfg = _obter_ou_criar_config(db)
    try:
        marcos = json.loads(cfg.marcos_alertados or "{}")
        dados["anki_config"] = marcos.get("anki_integracao", {}) if isinstance(marcos, dict) else {}
    except Exception:
        dados["anki_config"] = {}
    return dados


@router.get("/anki-config")
def obter_anki_config(db: Session = Depends(get_db)) -> Dict[str, Any]:
    cfg = _obter_ou_criar_config(db)
    try:
        marcos = json.loads(cfg.marcos_alertados or "{}")
        if isinstance(marcos, dict) and isinstance(marcos.get("anki_integracao"), dict):
            return marcos["anki_integracao"]
    except Exception:
        pass
    return {"auto_abrir": True, "url": "http://127.0.0.1:8765", "mapa_disciplinas": {}, "mapa_topicos": {}}


@router.post("/anki-config")
def salvar_anki_config(
    payload: Dict[str, Any] = Body(default={}),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    cfg = _obter_ou_criar_config(db)
    try:
        marcos = json.loads(cfg.marcos_alertados or "{}")
        if not isinstance(marcos, dict):
            marcos = {}
    except Exception:
        marcos = {}

    atual = marcos.get("anki_integracao") if isinstance(marcos.get("anki_integracao"), dict) else {}
    if "auto_abrir" in payload:
        atual["auto_abrir"] = bool(payload["auto_abrir"])
    if "url" in payload and payload["url"]:
        atual["url"] = str(payload["url"]).strip()
    if isinstance(payload.get("mapa_disciplinas"), dict):
        atual["mapa_disciplinas"] = payload["mapa_disciplinas"]
    if isinstance(payload.get("mapa_topicos"), dict):
        atual["mapa_topicos"] = payload["mapa_topicos"]

    marcos["anki_integracao"] = atual
    cfg.marcos_alertados = json.dumps(marcos, ensure_ascii=False)
    db.commit()
    return {"sucesso": True, "anki_config": atual}
