import json
import sys
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


@router.post("/anki-focar-janela")
def focar_ou_piscar_janela_anki() -> Dict[str, Any]:
    """
    Quando o backend roda localmente no Windows, localiza a janela Qt do Anki Desktop,
    restaura caso esteja minimizada, tenta trazer para frente e pisca o ícone na barra
    de tarefas (FlashWindowEx) para sinalizar que o baralho foi aberto via AnkiConnect.
    Em servidores remotos (Linux/nuvem), retorna graciosamente sem erro.
    """
    if sys.platform != "win32":
        return {"sucesso": False, "motivo": "disponivel_apenas_local_windows"}

    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        EnumWindows = user32.EnumWindows
        EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        GetWindowTextLengthW = user32.GetWindowTextLengthW
        GetWindowTextW = user32.GetWindowTextW
        GetClassNameW = user32.GetClassNameW
        IsWindowVisible = user32.IsWindowVisible
        IsIconic = user32.IsIconic
        ShowWindow = user32.ShowWindow
        SetForegroundWindow = user32.SetForegroundWindow

        class FLASHWINFO(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.UINT),
                ("hwnd", wintypes.HWND),
                ("dwFlags", wintypes.DWORD),
                ("uCount", wintypes.UINT),
                ("dwTimeout", wintypes.DWORD),
            ]

        encontrada = []

        def _callback(hwnd, _lparam):
            if IsWindowVisible(hwnd):
                length = GetWindowTextLengthW(hwnd)
                if length > 0:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    GetWindowTextW(hwnd, buf, length + 1)
                    titulo = buf.value
                    cls_buf = ctypes.create_unicode_buffer(128)
                    GetClassNameW(hwnd, cls_buf, 128)
                    cls_name = cls_buf.value.lower()
                    t_low = titulo.lower().strip()
                    # Garante que é a janela Qt do Anki Desktop (evita abas de navegador)
                    if ("qt" in cls_name) and (t_low == "anki" or t_low.endswith("- anki") or "anki" in t_low):
                        encontrada.append((hwnd, titulo))
            return True

        EnumWindows(EnumWindowsProc(_callback), 0)
        if not encontrada:
            return {"sucesso": False, "motivo": "janela_anki_nao_encontrada"}

        hwnd, titulo = encontrada[0]
        SW_RESTORE = 9
        if IsIconic(hwnd):
            ShowWindow(hwnd, SW_RESTORE)
        try:
            SetForegroundWindow(hwnd)
        except Exception:
            pass

        # Pisca o ícone do Anki na barra de tarefas (FLASHW_ALL=3 | FLASHW_TIMERNOFG=12)
        finfo = FLASHWINFO(
            cbSize=ctypes.sizeof(FLASHWINFO),
            hwnd=hwnd,
            dwFlags=3 | 12,
            uCount=4,
            dwTimeout=0,
        )
        user32.FlashWindowEx(ctypes.byref(finfo))
        return {"sucesso": True, "focado": True, "titulo": titulo}
    except Exception as e:
        return {"sucesso": False, "motivo": str(e)}
