import unittest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.edital import Edital
from app.models.disciplina import Disciplina
from app.models.sessao import SessaoEstudo
from app.services.ciclo_service import (
    gerar_ciclo_para_edital,
    configurar_ciclo_personalizado,
    aplicar_alternancia_volta_ciclo,
    avancar_bloco_ciclo,
)


class TestConfigCiclo(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=self.engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        self.db = SessionLocal()

        self.edital = Edital(nome="SEFAZ Teste", orgao="SEFAZ")
        self.db.add(self.edital)
        self.db.flush()

        self.d_port = Disciplina(edital_id=self.edital.id, nome="Português", categoria="TEORICA_DIREITO", incluir_no_ciclo=True)
        self.d_dir = Disciplina(edital_id=self.edital.id, nome="Direito Tributário", categoria="TEORICA_DIREITO", incluir_no_ciclo=True)
        self.d_est = Disciplina(edital_id=self.edital.id, nome="Estatística", categoria="EXATAS_LOGICA", incluir_no_ciclo=True)
        self.d_mat = Disciplina(edital_id=self.edital.id, nome="Matemática", categoria="EXATAS_LOGICA", incluir_no_ciclo=True)
        self.db.add_all([self.d_port, self.d_dir, self.d_est, self.d_mat])
        self.db.commit()

        self.ciclo = gerar_ciclo_para_edital(self.db, self.edital.id, carga_horaria_semanal=8.0)

    def tearDown(self):
        self.db.close()

    def test_ordem_revisoes_anki_e_alternancia_por_volta(self):
        # Configura ordem: Direito Tributário -> Português -> (Estatística <-> Matemática), com 2 Revisões Anki
        atualizado = configurar_ciclo_personalizado(
            db=self.db,
            ciclo_id=self.ciclo.id,
            itens=[
                {"disciplina_id": self.d_dir.id, "duracao_minutos": 60},
                {"disciplina_id": self.d_port.id, "duracao_minutos": 60},
                {"disciplina_id": self.d_est.id, "duracao_minutos": 60},
                {"disciplina_id": self.d_mat.id, "duracao_minutos": 60},  # deve consolidar em 1 slot alternado
            ],
            qtd_revisoes_anki=2,
            duracao_revisao_anki=30,
            alternancias=[{"disc_a_id": self.d_est.id, "disc_b_id": self.d_mat.id}],
        )

        nomes_volta_0 = [b.disciplina.nome for b in atualizado.blocos]
        self.assertEqual(nomes_volta_0.count("REVISÃO ANKI"), 2)
        self.assertIn("Estatística", nomes_volta_0)
        self.assertNotIn("Matemática", nomes_volta_0)
        self.assertLess(nomes_volta_0.index("Direito Tributário"), nomes_volta_0.index("Português"))

        # Simula completar volta 0 -> volta 1 (ímpar): Estatística deve virar Matemática
        atualizado.voltas_completas = 1
        alterou = aplicar_alternancia_volta_ciclo(self.db, atualizado)
        self.assertTrue(alterou)
        self.db.commit()
        self.db.refresh(atualizado)
        nomes_volta_1 = [b.disciplina.nome for b in atualizado.blocos]
        self.assertIn("Matemática", nomes_volta_1)
        self.assertNotIn("Estatística", nomes_volta_1)

        # Simula completar volta 1 -> volta 2 (par): Matemática volta a ser Estatística
        atualizado.voltas_completas = 2
        alterou2 = aplicar_alternancia_volta_ciclo(self.db, atualizado)
        self.assertTrue(alterou2)
        self.db.commit()
        self.db.refresh(atualizado)
        nomes_volta_2 = [b.disciplina.nome for b in atualizado.blocos]
        self.assertIn("Estatística", nomes_volta_2)
        self.assertNotIn("Matemática", nomes_volta_2)

    def test_resiliencia_sessoes_e_progresso_da_volta(self):
        # Marca o bloco de Português como concluído e registra uma sessão vinculada a ele
        bloco_port = next(b for b in self.ciclo.blocos if b.disciplina_id == self.d_port.id)
        bloco_port.concluido = True
        sessao = SessaoEstudo(
            ciclo_id=self.ciclo.id,
            bloco_ciclo_id=bloco_port.id,
            disciplina_id=self.d_port.id,
            tempo_estudado_minutos=55,
            qtd_questoes_total=20,
            qtd_acertos=17,
            qtd_erros=3,
            percentual_acerto=85.0,
            volta_ciclo=2,
        )
        self.db.add(sessao)
        # Define bloco atual como o de Direito Tributário e voltas_completas = 2
        idx_dir = next(i for i, b in enumerate(self.ciclo.blocos) if b.disciplina_id == self.d_dir.id)
        self.ciclo.bloco_atual_index = idx_dir
        self.ciclo.voltas_completas = 2
        self.db.commit()

        # Reconfigura movendo Direito Tributário para a última posição e removendo Revisão Anki (qtd=0)
        atualizado = configurar_ciclo_personalizado(
            db=self.db,
            ciclo_id=self.ciclo.id,
            itens=[
                {"disciplina_id": self.d_est.id, "duracao_minutos": 60},
                {"disciplina_id": self.d_port.id, "duracao_minutos": 90},
                {"disciplina_id": self.d_dir.id, "duracao_minutos": 60},
            ],
            qtd_revisoes_anki=0,
            duracao_revisao_anki=30,
            alternancias=[{"disc_a_id": self.d_est.id, "disc_b_id": self.d_mat.id}],
        )

        # Sessão e histórico permanecem intactos e ainda vinculados ao mesmo BlocoCiclo de Português
        sessao_pos = self.db.query(SessaoEstudo).filter(SessaoEstudo.id == sessao.id).first()
        self.assertIsNotNone(sessao_pos)
        self.assertEqual(sessao_pos.bloco_ciclo_id, bloco_port.id)
        self.assertEqual(sessao_pos.tempo_estudado_minutos, 55)
        self.assertEqual(sessao_pos.qtd_acertos, 17)

        # Status concluido do bloco de Português e voltas_completas foram preservados
        bloco_port_pos = next(b for b in atualizado.blocos if b.disciplina_id == self.d_port.id)
        self.assertEqual(bloco_port_pos.id, bloco_port.id)
        self.assertTrue(bloco_port_pos.concluido)
        self.assertEqual(atualizado.voltas_completas, 2)

        # bloco_atual_index aponta para o primeiro bloco pendente (Estatística, índice 0) e não burla progresso
        self.assertEqual(atualizado.blocos[atualizado.bloco_atual_index].disciplina_id, self.d_est.id)

    def test_reordenar_colocando_pendente_em_primeiro_e_pular_ja_concluida(self):
        # Cenário real: usuário conclui apenas Estatística e depois coloca Direito Tributário (pendente) em 1º lugar
        bloco_est = next(b for b in self.ciclo.blocos if b.disciplina_id == self.d_est.id)
        bloco_est.concluido = True
        self.db.commit()

        # Nova ordem: #1 Direito Tributário (pendente) -> #2 Estatística (já concluída) -> #3 Português (pendente)
        atualizado = configurar_ciclo_personalizado(
            db=self.db,
            ciclo_id=self.ciclo.id,
            itens=[
                {"disciplina_id": self.d_dir.id, "duracao_minutos": 60},
                {"disciplina_id": self.d_est.id, "duracao_minutos": 60},
                {"disciplina_id": self.d_port.id, "duracao_minutos": 60},
            ],
            qtd_revisoes_anki=0,
            duracao_revisao_anki=30,
            alternancias=[],
        )

        # 1) Primeiro a estudar deve ser #1 Direito Tributário (NÃO pode aparecer como concluído)
        self.assertEqual(atualizado.bloco_atual_index, 0)
        self.assertEqual(atualizado.blocos[0].disciplina_id, self.d_dir.id)
        self.assertFalse(atualizado.blocos[0].concluido)
        self.assertTrue(atualizado.blocos[1].concluido)  # Estatística continua concluída

        # 2) Ao concluir #1 Direito Tributário, o ciclo deve PULAR #2 Estatística e ir direto para #3 Português (idx=2)
        antigo, novo = avancar_bloco_ciclo(self.db, atualizado, marcar_atual_concluido=True)
        self.db.commit()
        self.db.refresh(atualizado)
        self.assertEqual(antigo, 0)
        self.assertEqual(novo, 2)
        self.assertEqual(atualizado.bloco_atual_index, 2)
        self.assertEqual(atualizado.blocos[2].disciplina_id, self.d_port.id)

        # 3) Ao concluir #3 Português, encerra a volta, reseta concluido=False e próxima volta segue sequencial 0 -> 1 -> 2
        _, novo2 = avancar_bloco_ciclo(self.db, atualizado, marcar_atual_concluido=True)
        self.db.commit()
        self.db.refresh(atualizado)
        self.assertEqual(novo2, 0)
        self.assertEqual(atualizado.voltas_completas, 1)
        self.assertTrue(all(not b.concluido for b in atualizado.blocos))

        # Próxima volta segue sequencialmente normal: 0 -> 1
        _, novo3 = avancar_bloco_ciclo(self.db, atualizado, marcar_atual_concluido=True)
        self.assertEqual(novo3, 1)


if __name__ == "__main__":
    unittest.main()
