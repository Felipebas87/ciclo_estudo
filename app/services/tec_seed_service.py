import os
import json
import gzip
from datetime import datetime, timezone
from typing import Optional, Dict, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.tec_taxonomia import TecTaxonomia, TopicoEstudoTecDePara
from app.models.edital import Edital
from app.models.disciplina import Disciplina
from app.models.topico import Topico

SEED_TAXONOMIA_GZ = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "tec_taxonomia_seed.json.gz")
SEED_VINCULOS_JSON = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "tec_vinculos_seed.json")


def carregar_seed_tec_taxonomia(db: Session, forcar: bool = False) -> int:
    """
    Carrega a árvore completa de taxonomia do TEC Concursos (4.000+ nós) a partir
    do arquivo seed comprimido embutido na aplicação.
    Garante disponibilidade imediata mesmo em servidores de nuvem (Render)
    sem depender de scraping ao vivo.
    """
    total_existente = db.query(func.count(TecTaxonomia.id)).scalar() or 0
    if total_existente > 0 and not forcar:
        return total_existente

    if not os.path.exists(SEED_TAXONOMIA_GZ):
        print(f"[TEC SEED] Arquivo {SEED_TAXONOMIA_GZ} não encontrado.")
        return total_existente

    try:
        with gzip.open(SEED_TAXONOMIA_GZ, "rt", encoding="utf-8") as f:
            nos_data = json.load(f)

        now = datetime.now(timezone.utc)
        novos_objetos = []

        # Cache dos tec_id já existentes para evitar duplicidade
        existentes_chaves = {
            (r[0], bool(r[1]))
            for r in db.query(TecTaxonomia.tec_id, TecTaxonomia.is_materia).all()
        }

        for item in nos_data:
            chave = (int(item["tec_id"]), bool(item.get("is_materia", False)))
            if chave in existentes_chaves:
                continue

            novos_objetos.append(TecTaxonomia(
                tec_id=int(item["tec_id"]),
                is_materia=bool(item.get("is_materia", False)),
                materia_tec_id=item.get("materia_tec_id"),
                nome=str(item.get("nome", "")),
                nivel_profundidade=int(item.get("nivel_profundidade", 1)),
                hierarquia_tec=item.get("hierarquia_tec"),
                caminho_completo=str(item.get("caminho_completo", "")),
                slug_url=item.get("slug_url"),
                total_questoes=int(item.get("total_questoes", 0)),
                url_params_payload=item.get("url_params_payload"),
                ativo=bool(item.get("ativo", True)),
                updated_at=now
            ))

        if novos_objetos:
            db.bulk_save_objects(novos_objetos)
            db.commit()
            print(f"[TEC SEED] {len(novos_objetos)} nós da árvore TEC importados com sucesso a partir do seed!")
            return len(novos_objetos) + total_existente

        return total_existente
    except Exception as exc:
        print(f"[TEC SEED] Erro ao carregar seed de taxonomia: {exc}")
        try:
            db.rollback()
        except Exception:
            pass
        return total_existente


def carregar_seed_tec_vinculos(db: Session, forcar: bool = False) -> int:
    """
    Aplica os vínculos De-Para padrão pré-mapeados entre os tópicos do edital
    e os nós da taxonomia do TEC Concursos.
    """
    total_vinculos = db.query(func.count(TopicoEstudoTecDePara.id)).scalar() or 0
    if total_vinculos > 0 and not forcar:
        return total_vinculos

    if not os.path.exists(SEED_VINCULOS_JSON):
        return total_vinculos

    try:
        with open(SEED_VINCULOS_JSON, "r", encoding="utf-8") as f:
            v_data = json.load(f)

        # Mapa de nós TEC por (tec_id, is_materia) -> TecTaxonomia.id
        tec_nodes = {
            (n.tec_id, bool(n.is_materia)): n.id
            for n in db.query(TecTaxonomia.id, TecTaxonomia.tec_id, TecTaxonomia.is_materia).all()
        }
        if not tec_nodes:
            # Tenta carregar a taxonomia antes se estiver vazia
            carregar_seed_tec_taxonomia(db)
            tec_nodes = {
                (n.tec_id, bool(n.is_materia)): n.id
                for n in db.query(TecTaxonomia.id, TecTaxonomia.tec_id, TecTaxonomia.is_materia).all()
            }

        # Mapa de tópicos existentes no banco por (disciplina_nome_lower, titulo_lower) -> Topico.id
        topicos_db = (
            db.query(Topico.id, Topico.titulo, Disciplina.nome)
            .join(Disciplina, Topico.disciplina_id == Disciplina.id)
            .all()
        )
        topicos_map = {
            ((d_nome or "").strip().lower(), (t_titulo or "").strip().lower()): t_id
            for t_id, t_titulo, d_nome in topicos_db
        }

        # Também mapa secundário apenas por titulo_lower
        topicos_titulo_map = {
            (t_titulo or "").strip().lower(): t_id
            for t_id, t_titulo, _ in topicos_db
        }

        vinculos_existentes_topico_ids = {
            v.topico_id for v in db.query(TopicoEstudoTecDePara.topico_id).all()
        }

        now = datetime.now(timezone.utc)
        inseridos = 0

        for item in v_data:
            d_nome = (item.get("disciplina_nome") or "").strip().lower()
            t_titulo = (item.get("topico_titulo") or "").strip().lower()
            chave_tec = (int(item["tec_id"]), bool(item.get("is_materia", False)))

            tec_taxonomia_id = tec_nodes.get(chave_tec)
            if not tec_taxonomia_id:
                continue

            # Busca tópico pelo par (disciplina, título) ou só título
            topico_id = topicos_map.get((d_nome, t_titulo)) or topicos_titulo_map.get(t_titulo)
            if not topico_id or topico_id in vinculos_existentes_topico_ids:
                continue

            novo_v = TopicoEstudoTecDePara(
                topico_id=topico_id,
                tec_taxonomia_id=tec_taxonomia_id,
                tipo_vinculo=item.get("tipo_vinculo", "AUTOMATICO_FUZZY"),
                confianca_score=float(item.get("confianca_score", 0.85)),
                validado=bool(item.get("validado", False)),
                caderno_id=item.get("caderno_id"),
                url_caderno_criado=item.get("url_caderno_criado"),
                pasta_tec_nome=item.get("pasta_tec_nome"),
                updated_at=now
            )
            db.add(novo_v)
            vinculos_existentes_topico_ids.add(topico_id)
            inseridos += 1

        if inseridos > 0:
            db.commit()
            print(f"[TEC SEED] {inseridos} vínculos De-Para aplicados com sucesso!")

        return inseridos + total_vinculos
    except Exception as exc:
        print(f"[TEC SEED] Erro ao carregar seed de vínculos: {exc}")
        try:
            db.rollback()
        except Exception:
            pass
        return total_vinculos
