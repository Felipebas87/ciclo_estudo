import sqlite3
import os

DB_PATH = "C:\\Projetos\\app estudo\\data\\study_cycle.db"

def upgrade():
    if not os.path.exists(DB_PATH):
        print(f"DB not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        cursor.execute("ALTER TABLE sessoes_estudo ADD COLUMN volta_ciclo INTEGER DEFAULT 0")
        print("Column 'volta_ciclo' added to 'sessoes_estudo' table.")
    except sqlite3.OperationalError as e:
        print(f"Error (maybe column already exists): {e}")

    # For existing sessions in a cycle that is not on round 0, we could update them, but default 0 is fine.
    
    conn.commit()
    conn.close()

if __name__ == "__main__":
    upgrade()
