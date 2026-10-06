import pytest
from app.models.disciplina import Disciplina
from app.models.topico import Topico
from app.services.ciclo_service import (
    calcular_fatores_importancia,
    distribuir_blocos_disciplinas,
    intercalar_blocos_cognitivo
)

def test_calculo_fatores_importancia():
    d1 = Disciplina(id=1, nome="Português", categoria="TEORICA_DIREITO", peso_prova=2.0, relevancia_dificuldade=3)
    d1.topicos = [Topico(titulo=f"Tópico {i}") for i in range(5)]

    d2 = Disciplina(id=2, nome="TI", categoria="EXATAS_LOGICA", peso_prova=3.0, relevancia_dificuldade=4)
    d2.topicos = [Topico(titulo=f"Tópico {i}") for i in range(10)]

    disciplinas = [d1, d2]
    fatores = calcular_fatores_importancia(disciplinas)

    # TI tem peso maior (3.0 vs 2.0), maior dificuldade (4 vs 3) e mais tópicos (10 vs 5)
    assert fatores[2] > fatores[1]
    assert fatores[1] > 0
    assert fatores[2] > 0

def test_distribuicao_blocos_minimo_um_por_materia():
    d1 = Disciplina(id=1, nome="D1", peso_prova=1.0, relevancia_dificuldade=1)
    d1.topicos = []
    d2 = Disciplina(id=2, nome="D2", peso_prova=5.0, relevancia_dificuldade=5)
    d2.topicos = [Topico(titulo="T1")]

    total_blocos = 10
    alocacao = distribuir_blocos_disciplinas([d1, d2], total_blocos)

    assert sum(alocacao.values()) == total_blocos
    assert alocacao[1] >= 1  # Garante pelo menos 1 bloco
    assert alocacao[2] > alocacao[1]  # D2 tem peso muito maior

def test_intercalacao_cognitiva_evita_repeticoes_consecutivas():
    d1 = Disciplina(id=1, nome="Matemática", categoria="EXATAS_LOGICA")
    d2 = Disciplina(id=2, nome="Direito", categoria="TEORICA_DIREITO")

    alocacao = {1: 3, 2: 3}
    blocos = intercalar_blocos_cognitivo([d1, d2], alocacao)

    assert len(blocos) == 6
    # Verifica que não há blocos consecutivos da mesma matéria quando as contagens são iguais
    for i in range(len(blocos) - 1):
        assert blocos[i] != blocos[i+1]
