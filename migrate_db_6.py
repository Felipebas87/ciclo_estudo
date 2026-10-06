import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'study_cycle.db')

def migrate():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        cursor.execute("ALTER TABLE ciclos_estudo ADD COLUMN voltas_completas INTEGER DEFAULT 0")
        print("Coluna 'voltas_completas' adicionada com sucesso.")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e):
            print("Coluna 'voltas_completas' já existe.")
        else:
            print("Erro:", e)
    
    conn.commit()
    conn.close()

if __name__ == '__main__':
    migrate()
