"""
Migration SQL / DDL para suporte à Árvore de Taxonomia do TEC Concursos
e Mapeamento De-Para com os Tópicos do Edital Verticalizado.
"""
from sqlalchemy import text
from app.database import engine, Base
import app.models  # Garante registro de TecTaxonomia e TopicoEstudoTecDePara

DDL_SQL = """
-- 1. Tabela da Árvore de Taxonomia do TEC Concursos
CREATE TABLE IF NOT EXISTS tec_taxonomia (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tec_id INTEGER NOT NULL,
    is_materia BOOLEAN NOT NULL DEFAULT 0,
    materia_tec_id INTEGER,
    nome VARCHAR(350) NOT NULL,
    parent_id INTEGER REFERENCES tec_taxonomia(id) ON DELETE CASCADE,
    nivel_profundidade INTEGER NOT NULL DEFAULT 1,
    hierarquia_tec VARCHAR(60),
    caminho_completo TEXT NOT NULL,
    slug_url VARCHAR(500),
    total_questoes INTEGER NOT NULL DEFAULT 0,
    url_params_payload TEXT,
    ativo BOOLEAN NOT NULL DEFAULT 1,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_tec_taxonomia_tec_id_is_materia
    ON tec_taxonomia (tec_id, is_materia);
CREATE INDEX IF NOT EXISTS ix_tec_taxonomia_tec_id
    ON tec_taxonomia (tec_id);
CREATE INDEX IF NOT EXISTS ix_tec_taxonomia_parent_id
    ON tec_taxonomia (parent_id);
CREATE INDEX IF NOT EXISTS ix_tec_taxonomia_caminho_completo
    ON tec_taxonomia (caminho_completo);

-- 2. Tabela Associativa De-Para (Tópico do Edital <-> Nó Taxonômico do TEC)
CREATE TABLE IF NOT EXISTS topico_estudo_tec_de_para (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topico_id INTEGER NOT NULL UNIQUE REFERENCES topicos(id) ON DELETE CASCADE,
    tec_taxonomia_id INTEGER NOT NULL REFERENCES tec_taxonomia(id) ON DELETE CASCADE,
    tipo_vinculo VARCHAR(30) NOT NULL DEFAULT 'AUTOMATICO_FUZZY',
    confianca_score FLOAT NOT NULL DEFAULT 0.0,
    validado BOOLEAN NOT NULL DEFAULT 0,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_topico_estudo_tec_de_para_topico_id
    ON topico_estudo_tec_de_para (topico_id);
CREATE INDEX IF NOT EXISTS ix_topico_estudo_tec_de_para_tec_taxonomia_id
    ON topico_estudo_tec_de_para (tec_taxonomia_id);
"""


def run_migration():
    Base.metadata.create_all(bind=engine)
    print("Tabelas 'tec_taxonomia' e 'topico_estudo_tec_de_para' criadas/verificadas com sucesso!")


if __name__ == "__main__":
    run_migration()
