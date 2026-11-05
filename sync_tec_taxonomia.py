"""
Job/Worker de Sincronização e Reconciliação da Árvore de Taxonomia do TEC Concursos.
Pode ser executado via CLI:
    python sync_tec_taxonomia.py
Ou agendado via Cron / Task Scheduler para detectar IDs novos, renomeados ou descontinuados.
"""
import sys
import asyncio
import argparse

from app.database import SessionLocal, Base, engine
import app.models
from app.models.edital import Edital
from app.services.tec_scraper_service import sincronizar_taxonomia_tec
from app.services.tec_matching_service import executar_matching_edital


async def main_async(edital_id: int | None = None, delay: float = 0.2, usar_ia: bool = True):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        print("=== [1/2] Iniciando Scraping Idempotente da Árvore do TEC Concursos ===")
        resumo_sync = await sincronizar_taxonomia_tec(db, delay_entre_requisicoes=delay)
        print(
            f"Concluído em {resumo_sync['tempo_segundos']}s | "
            f"Matérias: {resumo_sync['materias_processadas']} | "
            f"Total Nós: {resumo_sync['total_nos_processados']} "
            f"(+{resumo_sync['nos_inseridos']} novos, ~{resumo_sync['nos_atualizados']} atualizados, "
            f"-{resumo_sync['nos_descontinuados']} descontinuados)"
        )

        print("\n=== [2/2] Executando Mecanismo de Matching De-Para (Edital <-> TEC) ===")
        if edital_id is not None:
            editais = db.query(Edital).filter(Edital.id == edital_id).all()
        else:
            editais = db.query(Edital).filter(Edital.encerrado == False).all()

        for ed in editais:
            resumo_match = await executar_matching_edital(
                db=db,
                edital_id=ed.id,
                sobrescrever_manuais=False,
                usar_ia_se_necessario=usar_ia
            )
            print(
                f"Edital #{ed.id} ({ed.nome}): {resumo_match['total_topicos']} tópicos | "
                f"Exatos: {resumo_match['vinculados_exatos']} | "
                f"Fuzzy: {resumo_match['vinculados_fuzzy']} | "
                f"IA: {resumo_match['vinculados_ia']} | "
                f"Manuais: {resumo_match['preservados_manuais']} | "
                f"Alta Confiança (>=85%): {resumo_match['alta_confianca_85']}"
            )
    finally:
        db.close()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Sincroniza árvore do TEC Concursos e executa Matching De-Para.")
    parser.add_argument("--edital-id", type=int, default=None, help="ID do edital específico para reconciliar")
    parser.add_argument("--delay", type=float, default=0.2, help="Delay em segundos entre requisições ao TEC (rate limiting)")
    parser.add_argument("--sem-ia", action="store_true", help="Desativa reconciliação complementar via IA Gemini")
    args = parser.parse_args()

    asyncio.run(main_async(edital_id=args.edital_id, delay=args.delay, usar_ia=not args.sem_ia))
