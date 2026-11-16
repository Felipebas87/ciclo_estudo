import unittest
from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app.services.revisoes_service import diagnosticar_fila_revisoes_anki


class TestRevisoesAnki(unittest.TestCase):
    def setUp(self):
        self.db = SessionLocal()
        self.client = TestClient(app)

    def tearDown(self):
        self.db.close()

    def test_01_diagnostico_fila_revisoes_e_pior_rendimento(self):
        """Valida que a Central de Revisões mapeia revisões feitas, pior rendimento, curva de Ebbinghaus e técnicas."""
        dados = diagnosticar_fila_revisoes_anki(self.db)
        self.assertNotIn("erro", dados)
        self.assertIn("kpis", dados)
        self.assertIn("destaque_pior_rendimento", dados)
        self.assertIn("fila_sequencial_anki", dados)
        self.assertIn("ranking_pior_rendimento", dados)
        self.assertIn("historico_revisoes_feitas", dados)
        self.assertEqual(len(dados["tecnicas_memorizacao"]), 5)
        self.assertIn("curva_ebbinghaus", dados["graficos"])
        self.assertIn("constancia_14d", dados["graficos"])

        # Verifica que o ranking de pior rendimento ordena o menor percentual de acerto primeiro
        ranking_com_q = [x for x in dados["ranking_pior_rendimento"] if x["questoes_resolvidas"] > 0]
        if len(ranking_com_q) >= 2:
            self.assertLessEqual(ranking_com_q[0]["taxa_acerto_perc"], ranking_com_q[1]["taxa_acerto_perc"])

    def test_02_integracao_esteira_ciclo_blocos_revisao_anki(self):
        """Valida que os blocos REVISÃO ANKI do Ciclo Atual recebem a disciplina e o tópico recomendados."""
        resp_ciclo = self.client.get("/api/ciclos/ativo")
        self.assertEqual(resp_ciclo.status_code, 200)
        ciclo_json = resp_ciclo.json()
        if ciclo_json and ciclo_json.get("blocos"):
            blocos_anki = [
                b for b in ciclo_json["blocos"]
                if b.get("disciplina", {}).get("categoria") == "REVISAO_ANKI"
            ]
            self.assertGreater(len(blocos_anki), 0)
            for b_anki in blocos_anki:
                pt = b_anki.get("proximo_topico")
                self.assertIsNotNone(pt)
                self.assertTrue(pt.get("eh_revisao_anki"))
                self.assertTrue(bool(pt.get("disciplina_nome")))
                self.assertTrue(bool(pt.get("titulo")))
                self.assertIsNotNone(pt.get("taxa_acerto_perc"))
                self.assertIsNotNone(pt.get("retencao_estimada_perc"))
                self.assertTrue(bool(pt.get("tecnica_recomendada")))

    def test_03_endpoint_api_revisoes(self):
        """Valida o endpoint GET /api/revisoes."""
        resp = self.client.get("/api/revisoes")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("fila_sequencial_anki", body)
        self.assertIn("mapeamento_esteira_anki", body)


if __name__ == "__main__":
    unittest.main()
