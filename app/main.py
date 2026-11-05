
from pydantic import BaseModel, field_validator
from typing import Optional, List
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse


class ResultadoAvulso(BaseModel):
    id: Optional[int] = None
    nome_prova: str
    banca: Optional[str] = None
    data_prova: Optional[str] = None
    nota_final: float
    nota_corte: Optional[float] = None
    total_pontos_prova: Optional[float] = None
    acertos_basicos: Optional[int] = None
    erros_basicos: Optional[int] = None
    nota_basicos: Optional[float] = None
    acertos_especificos: Optional[int] = None
    erros_especificos: Optional[int] = None
    nota_especificos: Optional[float] = None
    nota_discursiva: Optional[float] = None
    posicao: Optional[int] = None
    resultado_final: str = "Aprovado"

    @field_validator(
        'banca', 'data_prova', 'nota_corte', 'total_pontos_prova',
        'acertos_basicos', 'erros_basicos', 'nota_basicos',
        'acertos_especificos', 'erros_especificos', 'nota_especificos',
        'nota_discursiva', 'posicao',
        mode='before'
    )
    @classmethod
    def empty_str_to_none(cls, v):
        if v == "" or v is None:
            return None
        return v



from dotenv import load_dotenv
load_dotenv()

from app.database import Base, engine
import app.models  # Garante registro dos modelos no SQLAlchemy
from app.routers import editais, ciclos, sessoes, dashboard, resultados, configuracao_prova, ia_insights, tec_integracao

# MIGRACAO AUTOMATICA E CRIACAO DE TABELAS (POSTGRES / SQLITE)
from sqlalchemy import inspect, text

def auto_upgrade_db():
    try:
        inspector = inspect(engine)
        existing_tables = inspector.get_table_names()

        # 1. Coluna 'encerrado' na tabela 'editais'
        if "editais" in existing_tables:
            col_names = [col["name"] for col in inspector.get_columns("editais")]
            if "encerrado" not in col_names:
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE editais ADD COLUMN encerrado BOOLEAN DEFAULT FALSE;"))
                print("Coluna 'encerrado' adicionada na tabela editais.")

        # 2. Cria novas tabelas do SQLAlchemy se não existirem
        Base.metadata.create_all(bind=engine)

        # Atualiza o inspector apos create_all
        inspector = inspect(engine)
        existing_tables = inspector.get_table_names()

        # 3. Coluna 'total_pontos_prova' na tabela 'resultados_concurso'
        if "resultados_concurso" in existing_tables:
            col_names = [col["name"] for col in inspector.get_columns("resultados_concurso")]
            if "total_pontos_prova" not in col_names:
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE resultados_concurso ADD COLUMN total_pontos_prova REAL;"))
                print("Coluna 'total_pontos_prova' adicionada na tabela resultados_concurso.")

        # 4. Colunas complementares na tabela 'resultados_avulsos'
        if "resultados_avulsos" in existing_tables:
            col_names = [col["name"] for col in inspector.get_columns("resultados_avulsos")]
            cols_def = {
                "banca": "TEXT",
                "data_prova": "TEXT",
                "total_pontos_prova": "REAL",
                "nota_corte": "REAL",
                "acertos_basicos": "INTEGER",
                "erros_basicos": "INTEGER",
                "nota_basicos": "REAL",
                "acertos_especificos": "INTEGER",
                "erros_especificos": "INTEGER",
                "nota_especificos": "REAL",
                "nota_discursiva": "REAL",
                "posicao": "INTEGER"
            }
            for col, col_type in cols_def.items():
                if col not in col_names:
                    try:
                        with engine.begin() as conn:
                            conn.execute(text(f"ALTER TABLE resultados_avulsos ADD COLUMN {col} {col_type};"))
                        print(f"Coluna '{col}' adicionada na tabela resultados_avulsos.")
                    except Exception as col_err:
                        print(f"Nota: coluna {col} em resultados_avulsos: {col_err}")

        # 5. Colunas de IA em 'configuracao_painel_prova'
        if "configuracao_painel_prova" in existing_tables:
            col_names = [col["name"] for col in inspector.get_columns("configuracao_painel_prova")]
            if "ultimo_insight_ia" not in col_names:
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE configuracao_painel_prova ADD COLUMN ultimo_insight_ia TEXT;"))
                print("Coluna 'ultimo_insight_ia' adicionada em configuracao_painel_prova.")
            if "data_insight_ia" not in col_names:
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE configuracao_painel_prova ADD COLUMN data_insight_ia TIMESTAMP;"))
                print("Coluna 'data_insight_ia' adicionada em configuracao_painel_prova.")
            if "gemini_api_key" not in col_names:
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE configuracao_painel_prova ADD COLUMN gemini_api_key VARCHAR(255);"))
                print("Coluna 'gemini_api_key' adicionada em configuracao_painel_prova.")
            if "area_concurso" not in col_names:
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE configuracao_painel_prova ADD COLUMN area_concurso VARCHAR(100) DEFAULT 'Fiscal';"))
                print("Coluna 'area_concurso' adicionada em configuracao_painel_prova.")

        # 6. Colunas 'mais_cobrado', 'prioridade', 'ordem_trilha' e 'motivo_ia' na tabela 'topicos'
        if "topicos" in existing_tables:
            col_names = [col["name"] for col in inspector.get_columns("topicos")]
            if "mais_cobrado" not in col_names:
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE topicos ADD COLUMN mais_cobrado BOOLEAN DEFAULT FALSE;"))
                print("Coluna 'mais_cobrado' adicionada na tabela topicos.")
            if "prioridade" not in col_names:
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE topicos ADD COLUMN prioridade INTEGER;"))
                print("Coluna 'prioridade' adicionada na tabela topicos.")
            if "ordem_trilha" not in col_names:
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE topicos ADD COLUMN ordem_trilha INTEGER;"))
                print("Coluna 'ordem_trilha' adicionada na tabela topicos.")
            if "motivo_ia" not in col_names:
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE topicos ADD COLUMN motivo_ia TEXT;"))
                print("Coluna 'motivo_ia' adicionada na tabela topicos.")

        # 7. Colunas de Trilha IA em 'disciplinas'
        if "disciplinas" in existing_tables:
            col_names = [col["name"] for col in inspector.get_columns("disciplinas")]
            if "ordem_trilha" not in col_names:
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE disciplinas ADD COLUMN ordem_trilha INTEGER;"))
                print("Coluna 'ordem_trilha' adicionada na tabela disciplinas.")
            if "pre_requisitos_ia" not in col_names:
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE disciplinas ADD COLUMN pre_requisitos_ia TEXT;"))
                print("Coluna 'pre_requisitos_ia' adicionada na tabela disciplinas.")
            if "justificativa_trilha_ia" not in col_names:
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE disciplinas ADD COLUMN justificativa_trilha_ia TEXT;"))
                print("Coluna 'justificativa_trilha_ia' adicionada na tabela disciplinas.")

        # 8. Colunas de Trilha IA em 'editais'
        if "editais" in existing_tables:
            col_names = [col["name"] for col in inspector.get_columns("editais")]
            if "ia_trilha_analisada" not in col_names:
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE editais ADD COLUMN ia_trilha_analisada BOOLEAN DEFAULT FALSE;"))
                print("Coluna 'ia_trilha_analisada' adicionada na tabela editais.")
            if "ia_trilha_data" not in col_names:
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE editais ADD COLUMN ia_trilha_data TIMESTAMP;"))
                print("Coluna 'ia_trilha_data' adicionada na tabela editais.")
            if "ia_trilha_banca" not in col_names:
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE editais ADD COLUMN ia_trilha_banca VARCHAR(100);"))
                print("Coluna 'ia_trilha_banca' adicionada na tabela editais.")
            if "ia_trilha_resumo" not in col_names:
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE editais ADD COLUMN ia_trilha_resumo TEXT;"))
                print("Coluna 'ia_trilha_resumo' adicionada na tabela editais.")

        # 9. Colunas de Caderno em 'topico_estudo_tec_de_para'
        if "topico_estudo_tec_de_para" in existing_tables:
            col_names = [col["name"] for col in inspector.get_columns("topico_estudo_tec_de_para")]
            if "caderno_id" not in col_names:
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE topico_estudo_tec_de_para ADD COLUMN caderno_id VARCHAR(50);"))
                print("Coluna 'caderno_id' adicionada na tabela topico_estudo_tec_de_para.")
            if "url_caderno_criado" not in col_names:
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE topico_estudo_tec_de_para ADD COLUMN url_caderno_criado VARCHAR(300);"))
                print("Coluna 'url_caderno_criado' adicionada na tabela topico_estudo_tec_de_para.")
            if "pasta_tec_nome" not in col_names:
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE topico_estudo_tec_de_para ADD COLUMN pasta_tec_nome VARCHAR(100);"))
                print("Coluna 'pasta_tec_nome' adicionada na tabela topico_estudo_tec_de_para.")
            if "data_geracao_caderno" not in col_names:
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE topico_estudo_tec_de_para ADD COLUMN data_geracao_caderno TIMESTAMP;"))
                print("Coluna 'data_geracao_caderno' adicionada na tabela topico_estudo_tec_de_para.")
    except Exception as e:
        print(f"Aviso no auto_upgrade_db: {e}")

auto_upgrade_db()


app = FastAPI(
    title="Sistema de Gestão de Ciclo de Estudos",
    description="Planejamento, execução e monitoramento de estudos para concursos públicos",
    version="1.0.0"
)

# Habilita CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Registra os Routers da API REST
app.include_router(editais.router)
app.include_router(ciclos.router)
app.include_router(sessoes.router)
app.include_router(dashboard.router)
app.include_router(resultados.router)
app.include_router(configuracao_prova.router)
app.include_router(ia_insights.router)
app.include_router(tec_integracao.router)

# Configuração dos Arquivos Estáticos e SPA Frontend
STATIC_DIR = Path(__file__).resolve().parent / "static"
STATIC_DIR.mkdir(exist_ok=True)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/", include_in_schema=False)
def serve_index():
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return FileResponse(
            str(index_path),
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
                "Pragma": "no-cache",
                "Expires": "0"
            }
        )
    return {"mensagem": "API do Ciclo de Estudos online. Acesse /docs para documentação interativa."}


# ---------------------
# RESULTADOS AVULSOS
# ---------------------

@app.get("/api/resultados_avulsos", response_model=List[ResultadoAvulso])
def get_resultados_avulsos():
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT * FROM resultados_avulsos ORDER BY CASE WHEN data_prova IS NULL OR data_prova = '' THEN 1 ELSE 0 END, data_prova DESC, id DESC")).fetchall()
            return [dict(row._mapping) for row in result]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



@app.post("/api/resultados_avulsos", response_model=ResultadoAvulso)
def create_resultado_avulso(res: ResultadoAvulso):
    try:
        from sqlalchemy.orm import Session
        import app.models.resultado_avulso
        with Session(engine) as session:
            novo = app.models.resultado_avulso.ResultadoAvulsoDB(
                nome_prova=res.nome_prova,
                banca=res.banca,
                data_prova=res.data_prova,
                nota_final=res.nota_final,
                nota_corte=res.nota_corte,
                total_pontos_prova=res.total_pontos_prova,
                acertos_basicos=res.acertos_basicos,
                erros_basicos=res.erros_basicos,
                nota_basicos=res.nota_basicos,
                acertos_especificos=res.acertos_especificos,
                erros_especificos=res.erros_especificos,
                nota_especificos=res.nota_especificos,
                nota_discursiva=res.nota_discursiva,
                posicao=res.posicao,
                resultado_final=res.resultado_final
            )
            session.add(novo)
            session.commit()
            session.refresh(novo)
            res.id = novo.id
            return res
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))



@app.put("/api/resultados_avulsos/{av_id}", response_model=ResultadoAvulso)
def update_resultado_avulso(av_id: int, res: ResultadoAvulso):
    try:
        from sqlalchemy.orm import Session
        import app.models.resultado_avulso
        with Session(engine) as session:
            item = session.query(app.models.resultado_avulso.ResultadoAvulsoDB).filter_by(id=av_id).first()
            if not item:
                raise HTTPException(status_code=404, detail="Resultado não encontrado")
            item.nome_prova = res.nome_prova
            item.banca = res.banca
            item.data_prova = res.data_prova
            item.nota_final = res.nota_final
            item.nota_corte = res.nota_corte
            item.total_pontos_prova = res.total_pontos_prova
            item.acertos_basicos = res.acertos_basicos
            item.erros_basicos = res.erros_basicos
            item.nota_basicos = res.nota_basicos
            item.acertos_especificos = res.acertos_especificos
            item.erros_especificos = res.erros_especificos
            item.nota_especificos = res.nota_especificos
            item.nota_discursiva = res.nota_discursiva
            item.posicao = res.posicao
            item.resultado_final = res.resultado_final
            session.commit()
            session.refresh(item)
            res.id = item.id
            return res
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))



@app.delete("/api/resultados_avulsos/{av_id}")
def delete_resultado_avulso(av_id: int):
    try:
        with engine.connect() as conn:
            conn.execute(text("DELETE FROM resultados_avulsos WHERE id = :id"), {"id": av_id})
            conn.commit()
            return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


