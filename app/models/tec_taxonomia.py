from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey, Text, DateTime, Index
from sqlalchemy.orm import relationship, backref
from app.database import Base


def _utcnow():
    return datetime.now(timezone.utc)


class TecTaxonomia(Base):
    """
    Árvore de Taxonomia do TEC Concursos:
    - Nível 1: Disciplina / Matéria (is_materia=True)
    - Nível 2: Assunto Raiz
    - Nível 3+: Subassuntos / Nós-filhos
    """
    __tablename__ = "tec_taxonomia"

    id = Column(Integer, primary_key=True, index=True)
    tec_id = Column(Integer, nullable=False, index=True)
    is_materia = Column(Boolean, default=False, nullable=False, index=True)
    materia_tec_id = Column(Integer, nullable=True, index=True)
    nome = Column(String(350), nullable=False)
    parent_id = Column(Integer, ForeignKey("tec_taxonomia.id", ondelete="CASCADE"), nullable=True, index=True)
    nivel_profundidade = Column(Integer, default=1, nullable=False)
    hierarquia_tec = Column(String(60), nullable=True)
    caminho_completo = Column(Text, nullable=False, index=True)
    slug_url = Column(String(500), nullable=True)
    total_questoes = Column(Integer, default=0, nullable=False)
    url_params_payload = Column(Text, nullable=True)
    ativo = Column(Boolean, default=True, nullable=False)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow, nullable=False)

    filhos = relationship(
        "TecTaxonomia",
        backref=backref("pai", remote_side=[id]),
        cascade="all, delete-orphan"
    )
    vinculos_topicos = relationship(
        "TopicoEstudoTecDePara",
        back_populates="tec_taxonomia",
        cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_tec_taxonomia_tec_id_is_materia", "tec_id", "is_materia", unique=True),
    )


class TopicoEstudoTecDePara(Base):
    """
    Tabela associativa De-Para entre um Tópico do Edital Verticalizado (`topicos.id`)
    e um nó da árvore de taxonomia do TEC Concursos (`tec_taxonomia.id`).
    """
    __tablename__ = "topico_estudo_tec_de_para"

    id = Column(Integer, primary_key=True, index=True)
    topico_id = Column(Integer, ForeignKey("topicos.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    tec_taxonomia_id = Column(Integer, ForeignKey("tec_taxonomia.id", ondelete="CASCADE"), nullable=False, index=True)
    tipo_vinculo = Column(String(30), nullable=False, default="AUTOMATICO_FUZZY")  # AUTOMATICO_EXATO, AUTOMATICO_FUZZY, AUTOMATICO_IA, MANUAL
    confianca_score = Column(Float, nullable=False, default=0.0)
    validado = Column(Boolean, default=False, nullable=False)
    caderno_id = Column(String(50), nullable=True)  # ex: "107798461"
    url_caderno_criado = Column(String(300), nullable=True)  # ex: "https://www.tecconcursos.com.br/questoes/cadernos/107798461"
    pasta_tec_nome = Column(String(100), nullable=True)  # ex: "Sefaz Alagoas Auditor TI"
    data_geracao_caderno = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow, nullable=False)

    topico = relationship("Topico", back_populates="vinculo_tec")
    tec_taxonomia = relationship("TecTaxonomia", back_populates="vinculos_topicos", lazy="joined")
