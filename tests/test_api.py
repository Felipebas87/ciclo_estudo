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

def test_sessao_avanca_ciclo():
    res_edital = client.post("/api/editais", json={
        "nome": "Edital Ciclo Teste",
        "disciplinas": [
            {"nome": "Português", "categoria": "TEORICA_DIREITO", "peso_prova": 1.0, "relevancia_dificuldade": 3},
            {"nome": "RLM", "categoria": "EXATAS_LOGICA", "peso_prova": 2.0, "relevancia_dificuldade": 3}
        ]
    })
    edital = res_edital.json()
    edital_id = edital["id"]

    res_ciclo = client.post("/api/ciclos/gerar", json={
        "edital_id": edital_id,
        "carga_horaria_semanal": 10,
        "duracao_bloco_minutos": 60
    })
    ciclo = res_ciclo.json()
    assert ciclo["bloco_atual_index"] == 0
    bloco_0 = ciclo["blocos"][0]

    # Registra sessão passando o bloco_ciclo_id
    res_sessao = client.post("/api/sessoes", json={
        "disciplina_id": bloco_0["disciplina_id"],
        "bloco_ciclo_id": bloco_0["id"],
        "tempo_estudado_minutos": 60,
        "qtd_questoes_total": 5,
        "qtd_acertos": 4,
        "qtd_erros": 1,
        "avancar_ciclo": True
    })
    assert res_sessao.status_code == 200

    # Verifica se o ciclo avançou para o bloco 1
    res_ciclo_atual = client.get("/api/ciclos/ativo")
    assert res_ciclo_atual.status_code == 200
    assert res_ciclo_atual.json()["bloco_atual_index"] == 1

    # Registra outra sessão sem bloco_ciclo_id, apenas com avancar_ciclo = True
    bloco_1 = ciclo["blocos"][1]
    res_sessao2 = client.post("/api/sessoes", json={
        "disciplina_id": bloco_1["disciplina_id"],
        "tempo_estudado_minutos": 60,
        "qtd_questoes_total": 5,
        "qtd_acertos": 5,
        "qtd_erros": 0,
        "avancar_ciclo": True
    })
    assert res_sessao2.status_code == 200

    # Verifica se avançou para o bloco 2
    res_ciclo_atual2 = client.get("/api/ciclos/ativo")
    assert res_ciclo_atual2.status_code == 200
    assert res_ciclo_atual2.json()["bloco_atual_index"] == 2

def test_encerrar_ciclo_e_total_dias_estudados():
    from datetime import date, timedelta

    # 1. Cria edital
    res_edital = client.post("/api/editais", json={
        "nome": "Concurso Auditor Fiscal",
        "orgao": "SEFAZ",
        "cargo": "Auditor",
        "disciplinas": [
            {"nome": "Contabilidade", "categoria": "ESPECIFICAS", "peso_prova": 3.0, "relevancia_dificuldade": 4},
            {"nome": "Direito Tributário", "categoria": "TEORICA_DIREITO", "peso_prova": 2.0, "relevancia_dificuldade": 3}
        ]
    })
    assert res_edital.status_code == 200
    edital = res_edital.json()
    edital_id = edital["id"]
    disc1_id = edital["disciplinas"][0]["id"]
    disc2_id = edital["disciplinas"][1]["id"]

    # 2. Registra 3 sessões: 2 no mesmo dia (hoje) e 1 em outro dia (ontem)
    hoje = date.today().isoformat()
    ontem = (date.today() - timedelta(days=1)).isoformat()

    client.post("/api/sessoes", json={
        "disciplina_id": disc1_id,
        "data": hoje,
        "tempo_estudado_minutos": 60,
        "qtd_questoes_total": 10,
        "qtd_acertos": 8,
        "qtd_erros": 2
    })
    client.post("/api/sessoes", json={
        "disciplina_id": disc2_id,
        "data": hoje,
        "tempo_estudado_minutos": 45,
        "qtd_questoes_total": 5,
        "qtd_acertos": 4,
        "qtd_erros": 1
    })
    client.post("/api/sessoes", json={
        "disciplina_id": disc1_id,
        "data": ontem,
        "tempo_estudado_minutos": 90,
        "qtd_questoes_total": 15,
        "qtd_acertos": 12,
        "qtd_erros": 3
    })

    # 3. Verifica draft de resultado antes de encerrar
    res_draft = client.get(f"/api/resultados/{edital_id}")
    assert res_draft.status_code == 200
    assert res_draft.json()["total_dias_estudados"] == 2
    assert res_draft.json()["total_horas"] == 3.25

    # 4. Encerra o ciclo oficialmente
    payload_encerramento = {
        "nota_final": 82.5,
        "nota_corte": 78.0,
        "nota_minima_aprovados": 78.0,
        "nota_maxima_aprovados": 92.0,
        "posicao": 15,
        "total_vagas": 30,
        "resultado_final": "Aprovado",
        "acertos_basicos": 16,
        "erros_basicos": 4,
        "acertos_especificos": 20,
        "erros_especificos": 5,
        "disciplinas": [
            {"disciplina_id": disc1_id, "acertos": 20, "erros": 5},
            {"disciplina_id": disc2_id, "acertos": 16, "erros": 4}
        ]
    }
    res_encerrar = client.post(f"/api/resultados/{edital_id}/encerrar", json=payload_encerramento)
    assert res_encerrar.status_code == 200
    encerrado_data = res_encerrar.json()
    assert encerrado_data["total_dias_estudados"] == 2
    assert encerrado_data["resultado_final"] == "Aprovado"

    # 5. Verifica lista de encerrados
    res_lista = client.get("/api/resultados/encerrados")
    assert res_lista.status_code == 200
    lista = res_lista.json()
    assert len(lista) == 1
    assert lista[0]["total_dias_estudados"] == 2
    assert lista[0]["nome_edital"] == "Concurso Auditor Fiscal"

def test_configuracao_prova_sincronizacao():
    # 1. Obter configuração inicial (deve criar id=1 com valores padrão)
    res_get = client.get("/api/configuracao-prova")
    assert res_get.status_code == 200
    data = res_get.json()
    assert data["id"] == 1
    assert data["concurso"] == "SEFAZ ALAGOAS"

    # 2. Atualizar data da prova e concurso (simulando alteração feita no PC)
    novo_payload = {
        "concurso": "RECEITA FEDERAL",
        "cargo": "Auditor-Fiscal da Receita Federal",
        "especialidade": "Geral",
        "banca": "FGV",
        "estilo_banca": "Múltipla Escolha (5 alternativas)",
        "data_prova": "2026-12-15",
        "nota_corte": 85.0,
        "total_vagas": "230 vagas",
        "local_prova": "Brasília - DF",
        "formato_prova": "140 questões + 2 discursivas",
        "status_edital": "Edital Iminente"
    }
    res_put = client.put("/api/configuracao-prova", json=novo_payload)
    assert res_put.status_code == 200
    atualizado = res_put.json()
    assert atualizado["concurso"] == "RECEITA FEDERAL"
    assert atualizado["data_prova"] == "2026-12-15"
    assert atualizado["nota_corte"] == 85.0

    # 3. Dispositivo secundário (ex: celular) busca a configuração e recebe os dados atualizados
    res_celular = client.get("/api/configuracao-prova")
    assert res_celular.status_code == 200
    celular_data = res_celular.json()
    assert celular_data["concurso"] == "RECEITA FEDERAL"
    assert celular_data["data_prova"] == "2026-12-15"

    # 4. Marcar marco alertado de 60 dias (deve marcar 60 e retroativamente 90)
    res_marco = client.post("/api/configuracao-prova/marcar-alerta", json={
        "marco": 60,
        "data_prova": "2026-12-15"
    })
    assert res_marco.status_code == 200
    import json
    marcos = json.loads(res_marco.json()["marcos_alertados"])
    assert marcos["2026-12-15"]["60"] is True
    assert marcos["2026-12-15"]["90"] is True

    # 5. Resetar alertas
    res_reset = client.post("/api/configuracao-prova/resetar-alertas")
    assert res_reset.status_code == 200
    assert res_reset.json()["marcos_alertados"] == "{}"

def test_ia_insights():
    # 1. Gera insights a partir do banco de testes
    res = client.get("/api/ia/insights")
    assert res.status_code == 200
    data = res.json()
    assert data["titulo"] == "INSIGHTS DE IA"
    assert "resumo_executivo" in data
    assert len(data["pontos_analise"]) >= 3
    assert "timestamp" in data

    # 2. Força recarga
    res_rec = client.post("/api/ia/insights/recarregar")
    assert res_rec.status_code == 200
    data_rec = res_rec.json()
    assert data_rec["titulo"] == "INSIGHTS DE IA"
    assert len(data_rec["pontos_analise"]) >= 3

    # 3. Status de chave
    res_status = client.get("/api/ia/status-chave")
    assert res_status.status_code == 200
    assert "configurada" in res_status.json()

    # 4. Salvar chave Gemini e verificar retorno
    res_conf = client.post("/api/ia/config-chave", json={"api_key": "AIzaSy_fake_test_key_for_testing"})
    assert res_conf.status_code == 200
    assert res_conf.json()["configurada"] is True
    assert "insight" in res_conf.json()

    # 5. Limpar chave
    res_limpar = client.post("/api/ia/config-chave", json={"api_key": ""})
    assert res_limpar.status_code == 200
    assert res_limpar.json()["configurada"] is False




