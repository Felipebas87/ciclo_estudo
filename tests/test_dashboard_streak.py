from datetime import date, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.edital import Edital
from app.models.disciplina import Disciplina
from app.models.sessao import SessaoEstudo
from app.services.dashboard_service import get_calendario_estudos


def _make_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return SessionLocal()


def _seed_edital_e_dias(db, dias_offsets):
    edital = Edital(nome="Edital Teste", orgao="Orgao", cargo="Cargo")
    db.add(edital)
    db.flush()

    disc = Disciplina(
        edital_id=edital.id,
        nome="Português",
        categoria="TEORICA_DIREITO",
    )
    db.add(disc)
    db.flush()

    hoje = date.today()
    for offset in dias_offsets:
        db.add(
            SessaoEstudo(
                disciplina_id=disc.id,
                data=hoje - timedelta(days=offset),
                tempo_estudado_minutos=60,
            )
        )
    db.commit()
    return edital.id


def test_streak_mantem_sequencia_ao_virar_o_dia_sem_estudo_hoje():
    db = _make_db()
    try:
        edital_id = _seed_edital_e_dias(db, [1, 2, 3])
        res = get_calendario_estudos(db, edital_id)
        assert res["analytics"]["current_streak"] == 3
        assert res["analytics"]["max_streak"] == 3
    finally:
        db.close()


def test_streak_incrementa_ao_estudar_hoje():
    db = _make_db()
    try:
        edital_id = _seed_edital_e_dias(db, [0, 1, 2, 3])
        res = get_calendario_estudos(db, edital_id)
        assert res["analytics"]["current_streak"] == 4
        assert res["analytics"]["max_streak"] == 4
    finally:
        db.close()


def test_streak_zera_apos_um_dia_inteiro_sem_estudo():
    db = _make_db()
    try:
        # Estudou há 2, 3 e 4 dias; ontem (offset=1) e hoje (offset=0) sem estudo
        edital_id = _seed_edital_e_dias(db, [2, 3, 4])
        res = get_calendario_estudos(db, edital_id)
        assert res["analytics"]["current_streak"] == 0
        assert res["analytics"]["max_streak"] == 3
    finally:
        db.close()


def test_streak_reinicia_em_1_se_falhou_ontem_mas_estudou_hoje():
    db = _make_db()
    try:
        edital_id = _seed_edital_e_dias(db, [0, 2, 3, 4])
        res = get_calendario_estudos(db, edital_id)
        assert res["analytics"]["current_streak"] == 1
        assert res["analytics"]["max_streak"] == 3
    finally:
        db.close()
