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
            self.assertGreater(m["duracao_minutos"], 0)
            if not m.get("is_revisao_anki"):
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
        self.assertEqual(len(gam["todos_ranks"]), 20)
        self.assertGreaterEqual(len(gam["medalhas"]), 56)

        tiers_encontrados = {m["tier"] for m in gam["medalhas"]}
        for t_esp in ("bronze", "prata", "ouro", "platina", "diamante", "lendario", "mitico"):
            self.assertIn(t_esp, tiers_encontrados)

    def test_05_alternancia_disciplinas_projetada_no_roteiro(self):
        """Valida que disciplinas configuradas em alternância no ciclo são ambas projetadas nas voltas pares/ímpares do roteiro até a prova."""
        import json
        from app.models.ciclo import CicloEstudos
        from app.models.disciplina import Disciplina

        ciclo = self.db.query(CicloEstudos).filter(CicloEstudos.ativo == True).first()
        if not ciclo or not ciclo.blocos:
            self.skipTest("Sem ciclo ativo no banco de teste")

        blocos_regulares = [
            b for b in sorted(ciclo.blocos, key=lambda x: x.ordem)
            if b.disciplina and b.disciplina.categoria != "REVISAO_ANKI"
        ]
        if not blocos_regulares:
            self.skipTest("Sem blocos regulares no ciclo ativo")

        disc_a_id = blocos_regulares[0].disciplina_id
        ids_no_ciclo = {b.disciplina_id for b in blocos_regulares}
        disc_b = (
            self.db.query(Disciplina)
            .filter(
                Disciplina.edital_id == ciclo.edital_id,
                Disciplina.categoria != "REVISAO_ANKI",
                ~Disciplina.id.in_(ids_no_ciclo),
            )
            .first()
        )
        if not disc_b:
            # Fallback: pega outra disciplina diferente de disc_a_id
            disc_b = (
                self.db.query(Disciplina)
                .filter(
                    Disciplina.edital_id == ciclo.edital_id,
                    Disciplina.categoria != "REVISAO_ANKI",
                    Disciplina.id != disc_a_id,
                )
                .first()
            )
        if not disc_b:
            self.skipTest("Sem segunda disciplina disponível para teste de alternância")

        cfg_original = ciclo.config_ciclo_json
        try:
            cfg = json.loads(cfg_original) if cfg_original else {}
            cfg["alternancias"] = [{"disc_a_id": disc_a_id, "disc_b_id": disc_b.id}]
            ciclo.config_ciclo_json = json.dumps(cfg, ensure_ascii=False)
            self.db.flush()

            rot = calcular_roteiro_estudo(
                db=self.db,
                horas_por_dia_override=3.0,
                dias_por_semana_override=6,
                data_prova_override=(self.hoje + timedelta(days=90)).isoformat(),
                hoje_ref=self.hoje,
            )

            por_disc = {d["disciplina_id"]: d for d in rot["roteiro_por_disciplina"]}
            self.assertIn(disc_a_id, por_disc)
            self.assertIn(disc_b.id, por_disc)

            aloc_a = por_disc[disc_a_id]["novos_ate_prova"] + por_disc[disc_a_id]["revisoes_apos_fechar"]
            aloc_b = por_disc[disc_b.id]["novos_ate_prova"] + por_disc[disc_b.id]["revisoes_apos_fechar"]
            self.assertGreater(aloc_a, 0, "Disciplina A da alternância deve receber missões nas voltas pares")
            self.assertGreater(aloc_b, 0, "Disciplina B da alternância deve receber missões nas voltas ímpares")
        finally:
            self.db.rollback()


if __name__ == "__main__":
    unittest.main()
