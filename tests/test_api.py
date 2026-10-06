import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.main import app
from app.database import Base, get_db

# Banco SQLite em memória com StaticPool para persistir entre conexões no teste
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

@pytest.fixture(autouse=True)
def setup_database():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

client = TestClient(app)

def test_criar_edital_e_gerar_ciclo():
    # 1. Cria edital com disciplinas
    payload_edital = {
        "nome": "Concurso Teste 2024",
        "orgao": "Orgao X",
        "cargo": "Analista",
        "disciplinas": [
            {
                "nome": "Português",
                "categoria": "TEORICA_DIREITO",
                "peso_prova": 1.5,
                "relevancia_dificuldade": 3,
                "topicos": [{"titulo": "Ortografia"}, {"titulo": "Sintaxe"}]
            },
            {
                "nome": "TI",
                "categoria": "EXATAS_LOGICA",
                "peso_prova": 3.0,
                "relevancia_dificuldade": 4,
                "topicos": [{"titulo": "Banco de Dados"}, {"titulo": "Redes"}]
            }
        ]
    }
    res_edital = client.post("/api/editais", json=payload_edital)
    assert res_edital.status_code == 200
    edital_data = res_edital.json()
    edital_id = edital_data["id"]
    assert len(edital_data["disciplinas"]) == 2

    # 2. Gera Ciclo
    payload_ciclo = {
        "edital_id": edital_id,
        "carga_horaria_semanal": 10,
        "duracao_bloco_minutos": 60
    }
    res_ciclo = client.post("/api/ciclos/gerar", json=payload_ciclo)
    assert res_ciclo.status_code == 200
    ciclo_data = res_ciclo.json()
    assert len(ciclo_data["blocos"]) >= 2
    assert ciclo_data["bloco_atual_index"] == 0

    # 3. Avançar bloco
    ciclo_id = ciclo_data["id"]
    res_avancar = client.post(f"/api/ciclos/{ciclo_id}/avancar")
    assert res_avancar.status_code == 200
    assert res_avancar.json()["bloco_atual_index"] == 1

def test_sessao_estudo_e_dashboard():
    # Cria edital rápido
    res_edital = client.post("/api/editais", json={
        "nome": "Edital Rápido",
        "disciplinas": [
            {"nome": "Direito Penal", "categoria": "TEORICA_DIREITO", "peso_prova": 2.0, "relevancia_dificuldade": 3}
        ]
    })
    edital = res_edital.json()
    disc_id = edital["disciplinas"][0]["id"]

    # Registra sessão com questões: 10 questões, 8 acertos, 2 erros
    payload_sessao = {
        "disciplina_id": disc_id,
        "tempo_estudado_minutos": 45,
        "qtd_questoes_total": 10,
        "qtd_acertos": 8,
        "qtd_erros": 2,
        "observacoes": "Bom rendimento"
    }
    res_sessao = client.post("/api/sessoes", json=payload_sessao)
    assert res_sessao.status_code == 200
    sessao_data = res_sessao.json()
    assert sessao_data["percentual_acerto"] == 80.0

    # Verifica Dashboard
    res_dash = client.get("/api/dashboard")
    assert res_dash.status_code == 200
    dash_data = res_dash.json()
    assert dash_data["metricas_gerais"]["total_questoes"] == 10
    assert dash_data["metricas_gerais"]["total_acertos"] == 8
    assert dash_data["metricas_gerais"]["percentual_acerto_geral"] == 80.0
    assert len(dash_data["rendimento_disciplinas"]) == 1
    assert dash_data["rendimento_disciplinas"][0]["disciplina_nome"] == "Direito Penal"
