import sqlite3
from pathlib import Path

db_path = Path("data/study_cycle.db")
if not db_path.exists():
    print("Banco de dados não encontrado em data/study_cycle.db")
    exit(1)

conn = sqlite3.connect(db_path)
cur = conn.cursor()

# 1. Colunas em topico_estudo_tec_de_para
cur.execute("PRAGMA table_info(topico_estudo_tec_de_para)")
colunas_de_para = [row[1] for row in cur.fetchall()]

novas_colunas_de_para = [
    ("caderno_id", "TEXT"),
    ("url_caderno_criado", "TEXT"),
    ("pasta_tec_nome", "TEXT"),
    ("data_geracao_caderno", "TIMESTAMP"),
]

for col_name, col_type in novas_colunas_de_para:
    if col_name not in colunas_de_para:
        cur.execute(f"ALTER TABLE topico_estudo_tec_de_para ADD COLUMN {col_name} {col_type}")
        print(f"Coluna {col_name} adicionada em topico_estudo_tec_de_para")

# 2. Colunas em configuracao_painel_prova
cur.execute("PRAGMA table_info(configuracao_painel_prova)")
colunas_cfg = [row[1] for row in cur.fetchall()]

novas_colunas_cfg = [
    ("tec_email", "TEXT DEFAULT 'fbasantos10@gmail.com'"),
    ("tec_senha", "TEXT"),
    ("tec_pasta_padrao", "TEXT DEFAULT 'Sefaz Alagoas Auditor TI'"),
]

for col_name, col_type in novas_colunas_cfg:
    if col_name not in colunas_cfg:
        cur.execute(f"ALTER TABLE configuracao_painel_prova ADD COLUMN {col_name} {col_type}")
        print(f"Coluna {col_name} adicionada em configuracao_painel_prova")

conn.commit()
conn.close()
print("Migração de colunas de cadernos concluída com sucesso!")
