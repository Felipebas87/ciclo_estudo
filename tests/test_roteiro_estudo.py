import unittest
from datetime import date, timedelta
from app.database import SessionLocal
from app.services.roteiro_estudo_service import calcular_roteiro_estudo


class TestRoteiroEstudo(unittest.TestCase):
    def setUp(self):
        self.db = SessionLocal()
        self.hoje = date(2026, 11, 16)
        self.data_prova_futura = (self.hoje + timedelta(days=45)).isoformat()

    def tearDown(self):
        self.db.close()

    def test_01_roteiro_padrao_2h_por_dia(self):
        """Valida que por padrão o roteiro usa 2h/dia (2 missões de 1h = disciplina + tópico)."""
        rot = calcular_roteiro_estudo(
            db=self.db,
            horas_por_dia_override=2.0,
            dias_por_semana_override=6,
            data_prova_override=self.data_prova_futura,
            hoje_ref=self.hoje,
        )
        self.assertNotIn("erro", rot)
        self.assertEqual(rot["parametros_roteiro"]["horas_por_dia"], 2.0)
        self.assertEqual(rot["parametros_roteiro"]["missoes_por_dia"], 2)
        self.assertEqual(len(rot["agenda_hoje"]["missoes_hoje"]), 2)
        for m in rot["agenda_hoje"]["missoes_hoje"]:
            self.assertEqual(m["duracao_minutos"], 60)
            self.assertTrue(bool(m["disciplina_nome"]))
            self.assertTrue(bool(m["topico_titulo"]))

    def test_02_ajuste_horas_recalcula_cobertura_probabilidades_e_questoes(self):
        """Valida que aumentar de 2h/dia para 4h/dia recalcula o roteiro e eleva % edital, P1/MC e questões."""
        rot_2h = calcular_roteiro_estudo(
            db=self.db,
            horas_por_dia_override=2.0,
            dias_por_semana_override=6,
            data_prova_override=self.data_prova_futura,
            hoje_ref=self.hoje,
        )
        rot_4h = calcular_roteiro_estudo(
            db=self.db,
            horas_por_dia_override=4.0,
            dias_por_semana_override=6,
            data_prova_override=self.data_prova_futura,
            hoje_ref=self.hoje,
        )

        p2 = rot_2h["projecao_ate_prova"]
        p4 = rot_4h["projecao_ate_prova"]

        self.assertGreater(p4["perc_edital_ate_prova"], p2["perc_edital_ate_prova"])
        self.assertGreaterEqual(p4["probabilidade_ver_p1_perc"], p2["probabilidade_ver_p1_perc"])
        self.assertGreaterEqual(
            p4["probabilidade_ver_mais_cobrados_perc"],
            p2["probabilidade_ver_mais_cobrados_perc"],
        )
        self.assertGreater(p4["questoes_acumuladas_ate_prova"], p2["questoes_acumuladas_ate_prova"])
        self.assertEqual(len(rot_4h["agenda_hoje"]["missoes_hoje"]), 4)

    def test_03_estrutura_semana_mes_calendario_e_ate_prova(self):
        """Valida a presença das visões de Semana, Mês, Calendário Mensal e Até a Prova."""
        rot = calcular_roteiro_estudo(
            db=self.db,
            horas_por_dia_override=2.0,
            dias_por_semana_override=6,
            data_prova_override=self.data_prova_futura,
            hoje_ref=self.hoje,
        )
        self.assertEqual(len(rot["roteiro_semana"]), 7)
        self.assertEqual(len(rot["roteiro_mes"]), 30)
        self.assertGreaterEqual(len(rot["calendario_mensal"]), 1)
        self.assertGreaterEqual(len(rot["semanas_ate_prova"]), 6)
        self.assertGreater(len(rot["roteiro_por_disciplina"]), 0)

    def test_04_gamificacao_medalhas_tiers_e_ranks(self):
        """Valida o sistema de gamificação, medalhas por dificuldade (Bronze a Lendário), Ranks e XP."""
        rot = calcular_roteiro_estudo(
            db=self.db,
            horas_por_dia_override=2.0,
            dias_por_semana_override=6,
            data_prova_override=self.data_prova_futura,
            hoje_ref=self.hoje,
        )
        self.assertIn("gamificacao", rot)
        gam = rot["gamificacao"]
        self.assertGreaterEqual(gam["xp_total"], 0)
        self.assertIn("rank_atual", gam)
        self.assertEqual(len(gam["todos_ranks"]), 10)
        self.assertGreaterEqual(len(gam["medalhas"]), 40)

        tiers_encontrados = {m["tier"] for m in gam["medalhas"]}
        for t_esp in ("bronze", "prata", "ouro", "platina", "diamante", "lendario"):
            self.assertIn(t_esp, tiers_encontrados)


if __name__ == "__main__":
    unittest.main()
