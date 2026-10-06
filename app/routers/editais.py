from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.edital import Edital
from app.models.disciplina import Disciplina
from app.models.topico import Topico
from app.schemas.edital import (
    EditalResponse,
    EditalCreate,
    DisciplinaResponse,
    DisciplinaUpdate,
    TopicoCreate,
    TopicoResponse
)
from app.services.ingestao_service import processar_arquivo_edital

router = APIRouter(prefix="/api/editais", tags=["Editais"])

@router.get("", response_model=List[EditalResponse])
def listar_editais(db: Session = Depends(get_db)):
    return db.query(Edital).order_by(Edital.data_criacao.desc()).all()

@router.get("/{edital_id}", response_model=EditalResponse)
def obter_edital(edital_id: int, db: Session = Depends(get_db)):
    edital = db.query(Edital).filter(Edital.id == edital_id).first()
    if not edital:
        raise HTTPException(status_code=404, detail="Edital não encontrado")
    return edital

@router.post("", response_model=EditalResponse)
def criar_edital(dados: EditalCreate, db: Session = Depends(get_db)):
    edital = Edital(
        nome=dados.nome,
        orgao=dados.orgao,
        cargo=dados.cargo,
        ativo=True
    )
    db.add(edital)
    db.flush()

    if dados.disciplinas:
        for d in dados.disciplinas:
            disciplina = Disciplina(
                edital_id=edital.id,
                nome=d.nome,
                categoria=d.categoria,
                peso_prova=d.peso_prova,
                relevancia_dificuldade=d.relevancia_dificuldade
            )
            db.add(disciplina)
            db.flush()
            if d.topicos:
                for t in d.topicos:
                    topico = Topico(
                        disciplina_id=disciplina.id,
                        titulo=t.titulo,
                        ordem=t.ordem
                    )
                    db.add(topico)

    db.commit()
    db.refresh(edital)
    return edital

@router.post("/upload")
async def upload_edital(
    arquivo: UploadFile = File(...),
    nome_edital: str = Form(...),
    orgao: Optional[str] = Form(None),
    cargo: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """
    Ingestão de Edital Verticalizado por upload de arquivo CSV ou Excel (RF01).
    """
    conteudo = await arquivo.read()
    if not conteudo:
        raise HTTPException(status_code=400, detail="Arquivo vazio")

    try:
        edital, total_disc, total_top = processar_arquivo_edital(
            db=db,
            conteudo_bytes=conteudo,
            nome_arquivo=arquivo.filename or "edital.csv",
            nome_edital=nome_edital,
            orgao=orgao,
            cargo=cargo
        )
        return {
            "mensagem": "Edital verticalizado importado com sucesso!",
            "edital_id": edital.id,
            "nome": edital.nome,
            "total_disciplinas": total_disc,
            "total_topicos": total_top
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Erro ao processar planilha: {str(e)}")

from app.schemas.edital import EditalTextoPuro
from app.services.ingestao_service import processar_texto_puro_edital

@router.post("/texto")
def criar_edital_texto_puro(dados: EditalTextoPuro, db: Session = Depends(get_db)):
    try:
        edital, total_disc, total_top = processar_texto_puro_edital(
            db=db,
            nome_edital=dados.nome,
            texto_basicos=dados.texto_basicos,
            texto_especificos=dados.texto_especificos
        )
        return {
            "mensagem": "Edital verticalizado importado com sucesso via texto puro!",
            "edital_id": edital.id,
            "nome": edital.nome,
            "total_disciplinas": total_disc,
            "total_topicos": total_top
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Erro ao processar texto do edital: {str(e)}")

@router.put("/disciplinas/{disciplina_id}", response_model=DisciplinaResponse)
def atualizar_disciplina(disciplina_id: int, dados: DisciplinaUpdate, db: Session = Depends(get_db)):
    """
    RF02: Configuração de pesos, dificuldade e categoria da disciplina.
    """
    disc = db.query(Disciplina).filter(Disciplina.id == disciplina_id).first()
    if not disc:
        raise HTTPException(status_code=404, detail="Disciplina não encontrada")

    if dados.nome is not None:
        disc.nome = dados.nome
    if dados.categoria is not None:
        disc.categoria = dados.categoria
    if dados.peso_prova is not None:
        disc.peso_prova = dados.peso_prova
    if dados.relevancia_dificuldade is not None:
        disc.relevancia_dificuldade = dados.relevancia_dificuldade
    if dados.incluir_no_ciclo is not None:
        disc.incluir_no_ciclo = dados.incluir_no_ciclo
    if dados.qtd_questoes_prova is not None:
        disc.qtd_questoes_prova = dados.qtd_questoes_prova

    db.commit()
    db.refresh(disc)
    return disc

@router.post("/disciplinas/{disciplina_id}/topicos", response_model=TopicoResponse)
def adicionar_topico(disciplina_id: int, dados: TopicoCreate, db: Session = Depends(get_db)):
    disc = db.query(Disciplina).filter(Disciplina.id == disciplina_id).first()
    if not disc:
        raise HTTPException(status_code=404, detail="Disciplina não encontrada")

    topico = Topico(
        disciplina_id=disciplina_id,
        titulo=dados.titulo,
        ordem=dados.ordem or len(disc.topicos),
        concluido=dados.concluido
    )
    db.add(topico)
    db.commit()
    db.refresh(topico)
    return topico

@router.delete("/{edital_id}")
def excluir_edital(edital_id: int, db: Session = Depends(get_db)):
    edital = db.query(Edital).filter(Edital.id == edital_id).first()
    if not edital:
        raise HTTPException(status_code=404, detail="Edital não encontrado")
    db.delete(edital)
    db.commit()
    return {"mensagem": "Edital excluído com sucesso"}

@router.get("/exemplo-csv", response_class=PlainTextResponse)
def obter_modelo_csv():
    """Retorna template de exemplo para upload de edital"""
    csv_conteudo = (
        "Disciplina;Topico;Categoria;Peso;Dificuldade\n"
        "Língua Portuguesa;Interpretação de Texto;TEORICA_DIREITO;1.5;3\n"
        "Língua Portuguesa;Sintaxe do Período;TEORICA_DIREITO;1.5;4\n"
        "Raciocínio Lógico e Matemático;Estruturas Lógicas;EXATAS_LOGICA;1.0;4\n"
        "Raciocínio Lógico e Matemático;Probabilidade e Análise Combinatória;EXATAS_LOGICA;1.0;5\n"
        "Direito Constitucional;Direitos e Garantias Fundamentais;TEORICA_DIREITO;2.0;2\n"
        "Direito Constitucional;Organização dos Poderes;TEORICA_DIREITO;2.0;3\n"
        "Direito Administrativo;Princípios da Administração Pública;TEORICA_DIREITO;2.0;2\n"
        "Direito Administrativo;Licitações e Contratos (Lei 14.133);TEORICA_DIREITO;2.0;4\n"
        "Tecnologia da Informação;Banco de Dados Relacional e SQL;EXATAS_LOGICA;3.0;3\n"
        "Tecnologia da Informação;Engenharia de Software e Scrum;EXATAS_LOGICA;3.0;2\n"
        "Tecnologia da Informação;Segurança da Informação e LGPD;EXATAS_LOGICA;3.0;4\n"
    )
    return csv_conteudo
