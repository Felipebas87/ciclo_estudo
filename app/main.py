from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.database import Base, engine
import app.models  # Garante registro dos modelos no SQLAlchemy
from app.routers import editais, ciclos, sessoes, dashboard

# Cria as tabelas do banco de dados automaticamente se não existirem
Base.metadata.create_all(bind=engine)

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

# Configuração dos Arquivos Estáticos e SPA Frontend
STATIC_DIR = Path(__file__).resolve().parent / "static"
STATIC_DIR.mkdir(exist_ok=True)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/", include_in_schema=False)
def serve_index():
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return {"mensagem": "API do Ciclo de Estudos online. Acesse /docs para documentação interativa."}
