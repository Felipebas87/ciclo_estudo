import json
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.configuracao_prova import ConfiguracaoPainelProva
from app.schemas.configuracao_prova import ConfiguracaoPainelProvaBase, ConfiguracaoPainelProvaResponse

router = APIRouter(prefix="/api/configuracao-prova", tags=["Configuração Painel Prova"])

@router.get("", response_model=ConfiguracaoPainelProvaResponse)
def obter_configuracao_prova(db: Session = Depends(get_db)):
    config = db.query(ConfiguracaoPainelProva).first()
    if not config:
        config = ConfiguracaoPainelProva(id=1)
        db.add(config)
        db.commit()
        db.refresh(config)
    return config

@router.put("", response_model=ConfiguracaoPainelProvaResponse)
def salvar_configuracao_prova(dados: ConfiguracaoPainelProvaBase, db: Session = Depends(get_db)):
    config = db.query(ConfiguracaoPainelProva).first()
    if not config:
        config = ConfiguracaoPainelProva(id=1)
        db.add(config)
    
    campos = dados.model_dump(exclude_unset=False)
    for campo, valor in campos.items():
        if hasattr(config, campo) and campo != 'id':
            setattr(config, campo, valor)
            
    db.commit()
    db.refresh(config)
    return config

@router.post("/marcar-alerta", response_model=ConfiguracaoPainelProvaResponse)
def marcar_alerta_visto(payload: dict, db: Session = Depends(get_db)):
    marco = str(payload.get("marco"))
    data_prova = payload.get("data_prova")
    config = db.query(ConfiguracaoPainelProva).first()
    if not config:
        config = ConfiguracaoPainelProva(id=1)
        db.add(config)
    
    marcos = {}
    try:
        if config.marcos_alertados:
            marcos = json.loads(config.marcos_alertados)
    except Exception:
        marcos = {}
    
    chave = data_prova or config.data_prova or "padrao"
    if chave not in marcos:
        marcos[chave] = {}
    marcos[chave][marco] = True
    try:
        marco_int = int(marco)
        if marco_int <= 60:
            marcos[chave]["90"] = True
        if marco_int <= 30:
            marcos[chave]["60"] = True
    except Exception:
        pass

    config.marcos_alertados = json.dumps(marcos)
    db.commit()
    db.refresh(config)
    return config

@router.post("/resetar-alertas", response_model=ConfiguracaoPainelProvaResponse)
def resetar_alertas_vistos(db: Session = Depends(get_db)):
    config = db.query(ConfiguracaoPainelProva).first()
    if not config:
        config = ConfiguracaoPainelProva(id=1)
        db.add(config)
    config.marcos_alertados = "{}"
    db.commit()
    db.refresh(config)
    return config
