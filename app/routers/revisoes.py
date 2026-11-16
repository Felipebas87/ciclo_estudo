from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.revisoes_service import diagnosticar_fila_revisoes_anki

router = APIRouter(prefix="/api/revisoes", tags=["Central de Revisões & Anki"])


@router.get("")
def obter_central_revisoes(
    edital_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    return diagnosticar_fila_revisoes_anki(db=db, edital_id=edital_id)
