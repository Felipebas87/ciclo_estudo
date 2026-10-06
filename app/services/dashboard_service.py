from typing import List, Dict, Any
from datetime import date, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.edital import Edital
from app.models.disciplina import Disciplina
from app.models.sessao import SessaoEstudo
from app.models.ciclo import CicloEstudos

def get_matriz_semanal(db: Session, edital_id: int) -> Dict[str, Any]:
    """
    Retorna os dados agrupados por disciplina e por semana (Matriz Semanal).
    """
    edital = db.query(Edital).filter(Edital.id == edital_id).first()
    if not edital:
        return {}

    # Todas as sessões do edital
    sessoes = (
        db.query(SessaoEstudo)
        .join(Disciplina)
        .filter(Disciplina.edital_id == edital_id)
        .all()
    )

    # Identificar semanas
    semanas = {}
    for s in sessoes:
        # Pega a segunda-feira da semana
        segunda = s.data - timedelta(days=s.data.weekday())
        if segunda not in semanas:
            semanas[segunda] = True
    
    lista_semanas = sorted(list(semanas.keys()))
    
    # Limitar a no máximo as últimas 8 semanas para não quebrar o layout/poluir a tela
    if len(lista_semanas) > 8:
        lista_semanas = lista_semanas[-8:]
        
    semanas_labels = [f"Sem {seg.strftime('%d/%m')}" for seg in lista_semanas]

    # Estrutura de retorno
    # { "BASICOS": [ { disciplina: str, semanas: [ { certas, resolvidas, perc } ] } ], "ESPECIFICOS": [] }
    resultado = {"BASICOS": [], "ESPECIFICOS": []}
    
    for disc in edital.disciplinas:
        if disc.categoria == 'REVISAO_ANKI':
            continue
        # sessoes da disciplina
        s_disc = [s for s in sessoes if s.disciplina_id == disc.id]
        
        linha_semanas = []
        totais = {"certas": 0, "resolvidas": 0}
        
        for seg in lista_semanas:
            domingo = seg + timedelta(days=6)
            s_semana = [s for s in s_disc if seg <= s.data <= domingo]
            
            c = sum(s.qtd_acertos for s in s_semana)
            r = sum(s.qtd_questoes_total for s in s_semana)
            p = round((c / r * 100), 1) if r > 0 else 0
            
            linha_semanas.append({
                "certas": c,
                "resolvidas": r,
                "percentual": p
            })
            totais["certas"] += c
            totais["resolvidas"] += r
            
        p_total = round((totais["certas"] / totais["resolvidas"] * 100), 1) if totais["resolvidas"] > 0 else 0
        
        item = {
            "disciplina": disc.nome,
            "semanas": linha_semanas,
            "total_certas": totais["certas"],
            "total_resolvidas": totais["resolvidas"],
            "percentual_total": p_total
        }
        
        if disc.grupo_conhecimento == "BASICOS":
            resultado["BASICOS"].append(item)
        else:
            resultado["ESPECIFICOS"].append(item)
            
    return {
        "labels": semanas_labels,
        "dados": resultado
    }

def get_calendario_estudos(db: Session, edital_id: int, dias: int = 30) -> Dict[str, Any]:
    hoje = date.today()
    # Usaremos 30 dias para trás e 15 dias para frente
    data_inicio = hoje - timedelta(days=30)
    data_fim = hoje + timedelta(days=15)
    total_dias = (data_fim - data_inicio).days + 1
    
    from app.models.edital import Edital
    from app.models.sessao import SessaoEstudo
    from app.models.disciplina import Disciplina

    edital = db.query(Edital).filter(Edital.id == edital_id).first()
    if not edital:
        return {}

    sessoes_todas = (
        db.query(SessaoEstudo)
        .join(Disciplina)
        .filter(Disciplina.edital_id == edital_id)
        .order_by(SessaoEstudo.data.asc())
        .all()
    )

    sessoes_periodo = [s for s in sessoes_todas if s.data >= data_inicio and s.data <= data_fim]

    lista_dias = [data_inicio + timedelta(days=i) for i in range(total_dias)]
    
    dias_semana_curto = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom']
    
    dias_labels = []
    for d in lista_dias:
        dias_labels.append({
            "data_str": d.strftime('%Y-%m-%d'),
            "label": d.strftime('%d/%m'),
            "dia_semana": dias_semana_curto[d.weekday()],
            "is_hoje": d == hoje,
            "is_fim_semana": d.weekday() >= 5
        })
    
    PALETTE = ["#3b82f6", "#10b981", "#8b5cf6", "#f59e0b", "#ec4899", "#14b8a6", "#f43f5e"]
    
    from app.models.ciclo import CicloEstudos
    ciclo_ativo = db.query(CicloEstudos).filter(CicloEstudos.edital_id == edital_id, CicloEstudos.ativo == True).first()
    
    disc_ordem = {}
    if ciclo_ativo and ciclo_ativo.blocos:
        for b in ciclo_ativo.blocos:
            if b.disciplina_id not in disc_ordem:
                disc_ordem[b.disciplina_id] = b.ordem
                
    def get_disc_order(disc):
        if disc.id in disc_ordem:
            return (0, disc_ordem[disc.id])
        return (1, disc.nome)
        
    disciplinas_ordenadas = sorted(edital.disciplinas, key=get_disc_order)

    linhas = []
    for disc in disciplinas_ordenadas:
        if disc.categoria == 'REVISAO_ANKI':
            continue
        celulas = []
        for d in lista_dias:
            s_dia = [s for s in sessoes_periodo if s.disciplina_id == disc.id and s.data == d]
            if s_dia:
                horas = 0
                volta_dia = 0
                for s in s_dia:
                    horas += s.tempo_estudado_minutos
                    if getattr(s, 'volta_ciclo', 0) > volta_dia:
                        volta_dia = getattr(s, 'volta_ciclo', 0)
                
                cor = PALETTE[volta_dia % len(PALETTE)]
                celulas.append({
                    "estudou": True,
                    "cor_hex": cor,
                    "minutos": horas,
                    "is_fim_semana": d.weekday() >= 5,
                    "is_hoje": d == hoje
                })
            else:
                celulas.append({
                    "estudou": False,
                    "cor_hex": "",
                    "minutos": 0,
                    "is_fim_semana": d.weekday() >= 5,
                    "is_hoje": d == hoje
                })
        linhas.append({
            "disciplina": disc.nome,
            "dias": celulas
        })
        
    max_volta = 0
    for s in sessoes_periodo:
        v = getattr(s, 'volta_ciclo', 0)
        if v > max_volta:
            max_volta = v
            
    legenda = []
    for i in range(max_volta + 1):
        legenda.append({
            "nome": f"Ciclo {i+1} (Volta {i+1})",
            "cor_hex": PALETTE[i % len(PALETTE)]
        })

    horas_por_dia = {}
    for s in sessoes_todas:
        if s.data not in horas_por_dia:
            horas_por_dia[s.data] = 0
        horas_por_dia[s.data] += s.tempo_estudado_minutos / 60.0

    dias_unicos_estudados = sorted(horas_por_dia.keys())
    
    current_streak = 0
    max_streak = 0
    temp_streak = 0
    taxa_aderencia = 0
    
    soma_horas_dsemana = {i: 0.0 for i in range(7)}
    count_dias_dsemana = {i: 0 for i in range(7)}
    evolucao_diaria = []

    if dias_unicos_estudados:
        data_minima = dias_unicos_estudados[0]
        # Calculate max period from first study day to today
        total_dias_analise = (hoje - data_minima).days + 1
        
        for i in range(total_dias_analise):
            d = data_minima + timedelta(days=i)
            hr_dia = horas_por_dia.get(d, 0.0)
            
            wd = d.weekday()
            count_dias_dsemana[wd] += 1
            if hr_dia > 0:
                soma_horas_dsemana[wd] += hr_dia
                temp_streak += 1
                max_streak = max(max_streak, temp_streak)
            else:
                temp_streak = 0
                
        # ALWAYS build evolucao_diaria for the last 60 days for moving averages
        data_min_grafico = hoje - timedelta(days=59)
        for i in range(60):
            d = data_min_grafico + timedelta(days=i)
            evolucao_diaria.append({
                "data": d.strftime("%Y-%m-%d"),
                "horas": horas_por_dia.get(d, 0.0)
            })
                
        d_curr = hoje
        while d_curr in horas_por_dia and horas_por_dia[d_curr] > 0:
            current_streak += 1
            d_curr -= timedelta(days=1)
            
        taxa_aderencia = round((len(dias_unicos_estudados) / total_dias_analise) * 100, 1) if total_dias_analise > 0 else 0

    media_horas_dsemana = {
        wd: round((soma_horas_dsemana[wd] / count_dias_dsemana[wd]), 2) if count_dias_dsemana[wd] > 0 else 0
        for wd in range(7)
    }

    distribuicao_horas = [round(h, 2) for h in horas_por_dia.values()]

    return {
        "dias_labels": dias_labels,
        "disciplinas": linhas,
        "legenda": legenda,
        "analytics": {
            "current_streak": current_streak,
            "max_streak": max_streak,
            "taxa_aderencia": taxa_aderencia,
            "media_horas_dia": round(sum(horas_por_dia.values()) / len(dias_unicos_estudados), 1) if dias_unicos_estudados else 0.0,
            "media_horas_dia_fmt": f"{int(sum(horas_por_dia.values()) / len(dias_unicos_estudados))}h{int(( (sum(horas_por_dia.values()) / len(dias_unicos_estudados)) % 1) * 60):02d}m" if dias_unicos_estudados else "0h00m",
            "media_horas_dsemana": media_horas_dsemana,
            "distribuicao_horas": distribuicao_horas,
            "evolucao_diaria": evolucao_diaria
        }
    }

def get_edital_verticalizado(db: Session, edital_id: int) -> Dict[str, Any]:
    """
    Retorna os dados para visualização de Edital Verticalizado Granular.
    """
    edital = db.query(Edital).filter(Edital.id == edital_id).first()
    if not edital:
        return {}

    resultado = {"BASICOS": [], "ESPECIFICOS": [], "resumo_basicos": {}, "resumo_especificos": {}}

    for grupo in ["BASICOS", "ESPECIFICOS"]:
        total_topicos = 0
        topicos_vistos = 0
        certas = 0
        resolvidas = 0
        
        disciplinas_grupo = [d for d in edital.disciplinas if d.grupo_conhecimento == grupo and d.categoria != 'REVISAO_ANKI']
        
        for disc in disciplinas_grupo:
            sessoes_disc = db.query(SessaoEstudo).filter(SessaoEstudo.disciplina_id == disc.id).all()
            t_certas = sum(s.qtd_acertos for s in sessoes_disc)
            t_resolvidas = sum(s.qtd_questoes_total for s in sessoes_disc)
            t_revisoes_anki = sum(1 for s in sessoes_disc if s.is_revisao_anki)
            perc = round((t_certas / t_resolvidas * 100), 1) if t_resolvidas > 0 else 0
            
            topicos_data = []
            disc_topicos_vistos = 0
            for t in disc.topicos:
                s_top = [s for s in sessoes_disc if s.topico_id == t.id]
                c = sum(s.qtd_acertos for s in s_top)
                r = sum(s.qtd_questoes_total for s in s_top)
                revs_anki = sum(1 for s in s_top if s.is_revisao_anki)
                p = round((c / r * 100), 1) if r > 0 else 0
                ultima_data = max([s.data for s in s_top]) if s_top else None
                
                visto = len(s_top) > 0
                if visto:
                    disc_topicos_vistos += 1
                
                topicos_data.append({
                    "id": t.id,
                    "titulo": t.titulo,
                    "certas": c,
                    "resolvidas": r,
                    "percentual": p,
                    "revisoes_anki": revs_anki,
                    "ultima_data": ultima_data.isoformat() if ultima_data else None,
                    "concluido": t.concluido,
                    "visto": visto
                })
                
            total_topicos += len(disc.topicos)
            topicos_vistos += disc_topicos_vistos
            certas += t_certas
            resolvidas += t_resolvidas
            
            cobertura_perc = round((disc_topicos_vistos / len(disc.topicos) * 100), 1) if len(disc.topicos) > 0 else 0
            
            resultado[grupo].append({
                "id": disc.id,
                "nome": disc.nome,
                "certas": t_certas,
                "resolvidas": t_resolvidas,
                "percentual": perc,
                "revisoes_anki": t_revisoes_anki,
                "topicos_vistos": disc_topicos_vistos,
                "total_topicos": len(disc.topicos),
                "cobertura_percentual": cobertura_perc,
                "topicos": topicos_data
            })
            
        cobertura_grupo = round((topicos_vistos / total_topicos * 100), 1) if total_topicos > 0 else 0
        perc_grupo = round((certas / resolvidas * 100), 1) if resolvidas > 0 else 0
        key = "resumo_basicos" if grupo == "BASICOS" else "resumo_especificos"
        resultado[key] = {
            "topicos_vistos": topicos_vistos,
            "total_topicos": total_topicos,
            "cobertura_percentual": cobertura_grupo,
            "certas": certas,
            "resolvidas": resolvidas,
            "percentual": perc_grupo
        }

    return resultado
