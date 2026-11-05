import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture(autouse=True)
def restaurar_db():
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


client = TestClient(app)


def test_estatisticas_e_materias_tec():
    resp = client.get("/api/tec/estatisticas?edital_id=1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_materias"] >= 20
    assert data["total_assuntos"] >= 3000
    assert data["total_vinculos"] >= 300

    resp_mat = client.get("/api/tec/materias")
    assert resp_mat.status_code == 200
    materias = resp_mat.json()
    assert len(materias) >= 20
    assert any("Segurança da Informação" in m["nome"] for m in materias)


def test_busca_arvore_tec_firewall():
    resp = client.get("/api/tec/arvore", params={"q": "Firewall", "apenas_assuntos": True})
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) > 0
    assert any("Firewall" in it["nome"] for it in items)


def test_obter_link_topico_e_vinculo_manual():
    # Tópico 302 = "5.1 Firewall e web application firewall (WAF)"
    resp = client.get("/api/tec/topico/302/link")
    assert resp.status_code == 200
    body = resp.json()
    vinculo = body["vinculo"]
    assert vinculo["vinculado"] is True
    assert "tecconcursos.com.br/materias/" in vinculo["url_assunto"]
    assert vinculo["banca_tec_id"] == 4
    assert len(body["sugestoes"]) > 0

    # Testar associação do caderno real 107798461
    resp_assoc = client.post(
        "/api/tec/topico/302/associar-caderno",
        json={
            "caderno_url_ou_id": "https://www.tecconcursos.com.br/questoes/cadernos/107798461",
            "pasta_nome": "Sefaz Alagoas Auditor TI"
        }
    )
    assert resp_assoc.status_code == 200
    assoc_data = resp_assoc.json()
    assert assoc_data["caderno_id"] == "107798461"
    assert assoc_data["url_caderno_criado"] == "https://www.tecconcursos.com.br/questoes/cadernos/107798461"
    assert assoc_data["vinculo"]["url_tec"] == "https://www.tecconcursos.com.br/questoes/cadernos/107798461"
    assert assoc_data["vinculo"]["tem_caderno_gerado"] is True

    # Fixar manualmente nó TEC e validar persistência
    tec_taxonomia_id_original = vinculo["tec_taxonomia_id"]
    resp_post = client.post(
        "/api/tec/topico/302/vincular",
        json={"tec_taxonomia_id": tec_taxonomia_id_original}
    )
    assert resp_post.status_code == 200
    v_manual = resp_post.json()
    assert v_manual["tipo_vinculo"] == "MANUAL"
    assert v_manual["confianca_score"] == 1.0
    assert v_manual["validado"] is True


def test_status_sessao_tec():
    resp = client.get("/api/tec/status-sessao")
    assert resp.status_code == 200
    data = resp.json()
    assert "autenticado" in data
    assert data["pasta_padrao"] == "Sefaz Alagoas Auditor TI"
    assert "email_configurado" in data


def test_ciclo_ativo_e_edital_verticalizado_expoem_tec_vinculo():
    resp_ciclo = client.get("/api/ciclos/ativo")
    assert resp_ciclo.status_code == 200
    ciclo = resp_ciclo.json()
    if ciclo and ciclo.get("blocos"):
        blocos_com_topico = [b for b in ciclo["blocos"] if b.get("proximo_topico")]
        assert len(blocos_com_topico) > 0
        for b in blocos_com_topico:
            tv = b["proximo_topico"].get("tec_vinculo")
            assert tv is not None
            assert tv.get("url_tec", "").startswith("https://www.tecconcursos.com.br/")

    resp_vert = client.get("/api/dashboard/edital-verticalizado?edital_id=1")
    assert resp_vert.status_code == 200
    vert = resp_vert.json()
    assert len(vert.get("TRILHA_COMPLETA", [])) > 0
    primeiro_topico = vert["TRILHA_COMPLETA"][0]["topicos"][0]
    assert "tec_vinculo" in primeiro_topico
    assert primeiro_topico["tec_vinculo"]["vinculado"] is True


def test_dois_comportamentos_link_tec():
    # Comportamento 1: Sem caderno vinculado manualmente -> abre direto a matéria com exercícios e banca
    resp_del = client.delete("/api/tec/topico/302/caderno")
    assert resp_del.status_code == 200
    del_data = resp_del.json()
    assert del_data["sucesso"] is True
    vinculo_sem_caderno = del_data["vinculo"]
    assert vinculo_sem_caderno["caderno_id"] is None
    assert vinculo_sem_caderno["tem_caderno_gerado"] is False
    assert "/aulas/materias/" in vinculo_sem_caderno["url_tec"]
    assert "exercicio=1" in vinculo_sem_caderno["url_tec"]
    assert "filtroBanca=4" in vinculo_sem_caderno["url_tec"]

    # Comportamento 2: Com caderno inserido manualmente -> abre o link oficial do caderno
    resp_assoc = client.post(
        "/api/tec/topico/302/associar-caderno",
        json={"caderno_url_ou_id": "107798461", "pasta_nome": "Sefaz Alagoas Auditor TI"}
    )
    assert resp_assoc.status_code == 200
    vinculo_com_caderno = resp_assoc.json()["vinculo"]
    assert vinculo_com_caderno["caderno_id"] == "107798461"
    assert vinculo_com_caderno["tem_caderno_gerado"] is True
    assert vinculo_com_caderno["url_tec"] == "https://www.tecconcursos.com.br/questoes/cadernos/107798461"
