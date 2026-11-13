
from pydantic import BaseModel, field_validator
from typing import Optional, List
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
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
from app.routers import editais, ciclos, sessoes, dashboard, resultados, configuracao_prova, ia_insights, tec_integracao, mapa_aprovacao

# MIGRACAO AUTOMATICA E CRIACAO DE TABELAS (POSTGRES / SQLITE)
from sqlalchemy import inspect, text

def safe_add_column(target_engine, table_name: str, col_name: str, col_sql_type: str):
    try:
        insp = inspect(target_engine)
        if table_name not in insp.get_table_names():
            return
        existing_cols = [c["name"] for c in insp.get_columns(table_name)]
        if col_name not in existing_cols:
            with target_engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_sql_type};"))
            print(f"[AUTO-UPGRADE] Coluna '{col_name}' adicionada com sucesso na tabela '{table_name}'.")
    except Exception as col_err:
        print(f"[AUTO-UPGRADE] Aviso ao checar/adicionar '{col_name}' em '{table_name}': {col_err}")

def auto_upgrade_db():
    try:
        # 1. Cria novas tabelas do SQLAlchemy se não existirem
        Base.metadata.create_all(bind=engine)
    except Exception as e_create:
        print(f"[AUTO-UPGRADE] Aviso em create_all: {e_create}")

    # 2. Migrações individuais com isolamento total para PostgreSQL e SQLite
    colunas_migracao = [
        # editais
        ("editais", "encerrado", "BOOLEAN DEFAULT FALSE"),
        ("editais", "ia_trilha_analisada", "BOOLEAN DEFAULT FALSE"),
        ("editais", "ia_trilha_data", "TIMESTAMP"),
        ("editais", "ia_trilha_banca", "VARCHAR(100)"),
        ("editais", "ia_trilha_resumo", "TEXT"),

        # configuracao_painel_prova
        ("configuracao_painel_prova", "area_concurso", "VARCHAR(100) DEFAULT 'Fiscal'"),
        ("configuracao_painel_prova", "tipo_data_prova", "VARCHAR(50) DEFAULT 'Confirmada'"),
        ("configuracao_painel_prova", "qtd_questoes_total_prova", "INTEGER DEFAULT 160"),
        ("configuracao_painel_prova", "nota_minima_geral", "REAL DEFAULT 60.0"),
        ("configuracao_painel_prova", "nota_minima_basicos", "REAL DEFAULT 50.0"),
        ("configuracao_painel_prova", "nota_minima_especificos", "REAL DEFAULT 60.0"),
        ("configuracao_painel_prova", "nota_minima_disciplina", "REAL DEFAULT 0.0"),
        ("configuracao_painel_prova", "nao_zerar_disciplina", "BOOLEAN DEFAULT TRUE"),
        ("configuracao_painel_prova", "fator_penalidade_erro", "REAL DEFAULT 0.0"),
        ("configuracao_painel_prova", "meta_conclusao_edital", "REAL DEFAULT 85.0"),
        ("configuracao_painel_prova", "dias_disponiveis_semana", "INTEGER DEFAULT 6"),
        ("configuracao_painel_prova", "horas_estudo_dia", "REAL DEFAULT 4.0"),
        ("configuracao_painel_prova", "horas_por_topico", "REAL DEFAULT 1.5"),
        ("configuracao_painel_prova", "dias_antecedencia_revisao", "INTEGER DEFAULT 21"),
        ("configuracao_painel_prova", "horas_simulado_semana", "REAL DEFAULT 4.0"),
        ("configuracao_painel_prova", "ultimo_mapa_ia", "TEXT"),
        ("configuracao_painel_prova", "data_mapa_ia", "TIMESTAMP"),
        ("configuracao_painel_prova", "marcos_alertados", "TEXT DEFAULT '{}'"),
        ("configuracao_painel_prova", "ultimo_insight_ia", "TEXT"),
        ("configuracao_painel_prova", "data_insight_ia", "TIMESTAMP"),
        ("configuracao_painel_prova", "gemini_api_key", "VARCHAR(255)"),
        ("configuracao_painel_prova", "tec_email", "VARCHAR(150) DEFAULT 'fbasantos10@gmail.com'"),
        ("configuracao_painel_prova", "tec_senha", "VARCHAR(200)"),
        ("configuracao_painel_prova", "tec_pasta_padrao", "VARCHAR(150) DEFAULT 'Sefaz Alagoas Auditor TI'"),
        ("configuracao_painel_prova", "data_atualizacao", "TIMESTAMP"),

        # disciplinas
        ("disciplinas", "ordem_trilha", "INTEGER"),
        ("disciplinas", "pre_requisitos_ia", "TEXT"),
        ("disciplinas", "justificativa_trilha_ia", "TEXT"),
        ("disciplinas", "qtd_questoes_prova", "INTEGER"),

        # topicos
        ("topicos", "mais_cobrado", "BOOLEAN DEFAULT FALSE"),
        ("topicos", "prioridade", "INTEGER"),
        ("topicos", "ordem_trilha", "INTEGER"),
        ("topicos", "motivo_ia", "TEXT"),

        # topico_estudo_tec_de_para
        ("topico_estudo_tec_de_para", "caderno_id", "VARCHAR(50)"),
        ("topico_estudo_tec_de_para", "url_caderno_criado", "VARCHAR(300)"),
        ("topico_estudo_tec_de_para", "pasta_tec_nome", "VARCHAR(100)"),
        ("topico_estudo_tec_de_para", "data_geracao_caderno", "TIMESTAMP"),

        # resultados_concurso
        ("resultados_concurso", "total_pontos_prova", "REAL"),

        # resultados_avulsos
        ("resultados_avulsos", "banca", "TEXT"),
        ("resultados_avulsos", "data_prova", "TEXT"),
        ("resultados_avulsos", "total_pontos_prova", "REAL"),
        ("resultados_avulsos", "nota_corte", "REAL"),
        ("resultados_avulsos", "acertos_basicos", "INTEGER"),
        ("resultados_avulsos", "erros_basicos", "INTEGER"),
        ("resultados_avulsos", "nota_basicos", "REAL"),
        ("resultados_avulsos", "acertos_especificos", "INTEGER"),
        ("resultados_avulsos", "erros_especificos", "INTEGER"),
        ("resultados_avulsos", "nota_especificos", "REAL"),
        ("resultados_avulsos", "nota_discursiva", "REAL"),
        ("resultados_avulsos", "posicao", "INTEGER")
    ]

    for tbl, col, ctype in colunas_migracao:
        safe_add_column(engine, tbl, col, ctype)

    # 3. Garante registro padrão (id=1) em configuracao_painel_prova
    try:
        with engine.begin() as conn:
            insp = inspect(engine)
            if "configuracao_painel_prova" in insp.get_table_names():
                res = conn.execute(text("SELECT count(*) FROM configuracao_painel_prova")).scalar()
                if not res or res == 0:
                    conn.execute(text("INSERT INTO configuracao_painel_prova (id, concurso) VALUES (1, 'SEFAZ ALAGOAS');"))
                    print("[AUTO-UPGRADE] Linha padrão criada em configuracao_painel_prova.")
                conn.execute(text("""
                    UPDATE configuracao_painel_prova SET
                        area_concurso = COALESCE(area_concurso, 'Fiscal'),
                        tipo_data_prova = COALESCE(tipo_data_prova, 'Confirmada'),
                        qtd_questoes_total_prova = COALESCE(qtd_questoes_total_prova, 160),
                        nota_minima_geral = COALESCE(nota_minima_geral, 60.0),
                        nota_minima_basicos = COALESCE(nota_minima_basicos, 50.0),
                        nota_minima_especificos = COALESCE(nota_minima_especificos, 60.0),
                        nota_minima_disciplina = COALESCE(nota_minima_disciplina, 0.0),
                        nao_zerar_disciplina = COALESCE(nao_zerar_disciplina, TRUE),
                        fator_penalidade_erro = COALESCE(fator_penalidade_erro, 0.0),
                        meta_conclusao_edital = COALESCE(meta_conclusao_edital, 85.0),
                        dias_disponiveis_semana = COALESCE(dias_disponiveis_semana, 6),
                        horas_estudo_dia = COALESCE(horas_estudo_dia, 4.0),
                        horas_por_topico = COALESCE(horas_por_topico, 1.5),
                        dias_antecedencia_revisao = COALESCE(dias_antecedencia_revisao, 21),
                        horas_simulado_semana = COALESCE(horas_simulado_semana, 4.0);
                """))
    except Exception as e_row:
        print(f"[AUTO-UPGRADE] Aviso ao verificar linha 1 em configuracao_painel_prova: {e_row}")

    # 3.1. Garante índices de performance para PostgreSQL e SQLite em chaves estrangeiras e colunas de busca
    indices_performance = [
        "CREATE INDEX IF NOT EXISTS ix_disciplinas_edital_id ON disciplinas (edital_id);",
        "CREATE INDEX IF NOT EXISTS ix_topicos_disciplina_id ON topicos (disciplina_id);",
        "CREATE INDEX IF NOT EXISTS ix_sessoes_estudo_disciplina_id ON sessoes_estudo (disciplina_id);",
        "CREATE INDEX IF NOT EXISTS ix_sessoes_estudo_topico_id ON sessoes_estudo (topico_id);",
        "CREATE INDEX IF NOT EXISTS ix_sessoes_estudo_ciclo_id ON sessoes_estudo (ciclo_id);",
        "CREATE INDEX IF NOT EXISTS ix_sessoes_estudo_bloco_ciclo_id ON sessoes_estudo (bloco_ciclo_id);",
        "CREATE INDEX IF NOT EXISTS ix_sessoes_estudo_data ON sessoes_estudo (data);",
        "CREATE INDEX IF NOT EXISTS ix_blocos_ciclo_ciclo_id ON blocos_ciclo (ciclo_id);",
        "CREATE INDEX IF NOT EXISTS ix_blocos_ciclo_disciplina_id ON blocos_ciclo (disciplina_id);",
        "CREATE INDEX IF NOT EXISTS ix_ciclos_estudo_edital_ativo ON ciclos_estudo (edital_id, ativo);"
    ]
    for sql_idx in indices_performance:
        try:
            with engine.begin() as conn:
                conn.execute(text(sql_idx))
        except Exception as e_idx:
            print(f"[AUTO-UPGRADE] Aviso ao criar índice ({sql_idx}): {e_idx}")

    # 4. Garante que os nós de taxonomia e vínculos do TEC estejam carregados a partir do seed embutido
    try:
        from app.database import SessionLocal
        from app.services.tec_seed_service import carregar_seed_tec_taxonomia, carregar_seed_tec_vinculos
        with SessionLocal() as db_session:
            carregar_seed_tec_taxonomia(db_session)
            carregar_seed_tec_vinculos(db_session)
    except Exception as e_seed:
        print(f"[AUTO-UPGRADE] Aviso ao carregar seeds do TEC: {e_seed}")

auto_upgrade_db()


app = FastAPI(
    title="Sistema de Gestão de Ciclo de Estudos",
    description="Planejamento, execução e monitoramento de estudos para concursos públicos",
    version="1.0.0"
)

# Habilita compressão GZip para payloads JSON e assets estáticos
app.add_middleware(GZipMiddleware, minimum_size=500)

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
app.include_router(mapa_aprovacao.router)

# Configuração dos Arquivos Estáticos e SPA Frontend
STATIC_DIR = Path(__file__).resolve().parent / "static"
STATIC_DIR.mkdir(exist_ok=True)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.middleware("http")
async def disable_static_js_cache(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/static/js/") or request.url.path.startswith("/static/css/"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

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


