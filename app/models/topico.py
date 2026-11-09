from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.database import Base

class Topico(Base):
    __tablename__ = "topicos"

    id = Column(Integer, primary_key=True, index=True)
    disciplina_id = Column(Integer, ForeignKey("disciplinas.id", ondelete="CASCADE"), nullable=False, index=True)
    titulo = Column(Text, nullable=False)
    ordem = Column(Integer, default=0)
    concluido = Column(Boolean, default=False)
    mais_cobrado = Column(Boolean, default=False)
    prioridade = Column(Integer, nullable=True)  # 1 (Alta/P1), 2 (Média/P2), 3 (Baixa/P3) ou None
    ordem_trilha = Column(Integer, nullable=True)
    motivo_ia = Column(Text, nullable=True)

    disciplina = relationship("Disciplina", back_populates="topicos")
    sessoes = relationship("SessaoEstudo", back_populates="topico")
    vinculo_tec = relationship(
        "TopicoEstudoTecDePara",
        back_populates="topico",
        uselist=False,
        cascade="all, delete-orphan"
    )

    @property
    def tec_vinculo(self):
        from app.services.tec_matching_service import montar_dados_vinculo_topico
        return montar_dados_vinculo_topico(self, self.vinculo_tec)
