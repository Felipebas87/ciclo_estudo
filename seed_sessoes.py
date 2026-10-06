import sqlite3
import random
from datetime import datetime, timedelta

DB_PATH = "C:\\Projetos\\app estudo\\data\\study_cycle.db"

def seed():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Get a cycle
    cursor.execute("SELECT id, edital_id, voltas_completas FROM ciclos_estudo WHERE ativo=1 LIMIT 1")
    ciclo = cursor.fetchone()
    if not ciclo:
        print("Nenhum ciclo ativo encontrado.")
        return
    ciclo_id, edital_id, voltas = ciclo

    # Get blocks for this cycle
    cursor.execute("SELECT id, disciplina_id FROM blocos_ciclo WHERE ciclo_id = ?", (ciclo_id,))
    blocos = cursor.fetchall()
    if not blocos:
        print("Nenhum bloco encontrado no ciclo ativo.")
        return

    today = datetime.now()
    dates_to_add = [
        today - timedelta(days=5),
        today - timedelta(days=1),
        today + timedelta(days=1)
    ]

    for d in dates_to_add:
        # Create 2 sessions for each day
        for _ in range(2):
            bloco_id, disciplina_id = random.choice(blocos)
            
            data_str = d.strftime('%Y-%m-%d')
            data_criacao_str = d.strftime('%Y-%m-%d %H:%M:%S')
            
            tempo = random.randint(30, 120)
            total_q = random.randint(10, 30)
            acertos = random.randint(5, total_q)
            erros = total_q - acertos
            perc = round((acertos / total_q) * 100, 2)

            cursor.execute("""
                INSERT INTO sessoes_estudo 
                (ciclo_id, bloco_ciclo_id, disciplina_id, data, data_criacao, tempo_estudado_minutos, 
                qtd_questoes_total, qtd_acertos, qtd_erros, percentual_acerto, observacoes, is_revisao_anki, volta_ciclo)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (ciclo_id, bloco_id, disciplina_id, data_str, data_criacao_str, tempo, total_q, acertos, erros, perc, 'Mock para testes visuais', 0, voltas))
            
    conn.commit()
    print("Sessões de teste inseridas com sucesso!")
    conn.close()

if __name__ == "__main__":
    seed()
