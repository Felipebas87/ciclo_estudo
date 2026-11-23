import json
from datetime import date, datetime, timedelta
from collections import defaultdict
from typing import Dict, Any, List, Optional, Set

from sqlalchemy.orm import Session, selectinload

from app.models.configuracao_prova import ConfiguracaoPainelProva
from app.models.edital import Edital
from app.models.disciplina import Disciplina
from app.models.topico import Topico
from app.models.ciclo import CicloEstudos
from app.models.sessao import SessaoEstudo


RANKS_SISTEMA = [
    {"nivel": 1, "titulo": "Iniciante da Trilha", "xp_min": 0, "cor": "bronze", "icone": "star", "avatar_url": "/static/img/avatars/rank_01.png?v=3", "personagem": "Viajante Mochileiro"},
    {"nivel": 2, "titulo": "Estudante Focado", "xp_min": 250, "cor": "bronze", "icone": "flame", "avatar_url": "/static/img/avatars/rank_02.png?v=3", "personagem": "Estudante de Fones"},
    {"nivel": 3, "titulo": "Estrategista de Ciclo", "xp_min": 600, "cor": "prata", "icone": "compass", "avatar_url": "/static/img/avatars/rank_03.png?v=3", "personagem": "Navegador Tático"},
    {"nivel": 4, "titulo": "Desbravador de Edital", "xp_min": 1100, "cor": "prata", "icone": "shield", "avatar_url": "/static/img/avatars/rank_04.png?v=3", "personagem": "Explorador de Escudo"},
    {"nivel": 5, "titulo": "Caçador de Questões", "xp_min": 1800, "cor": "ouro", "icone": "target", "avatar_url": "/static/img/avatars/rank_05.png?v=3", "personagem": "Arqueiro de Questões"},
    {"nivel": 6, "titulo": "Especialista Pareto 80/20", "xp_min": 2700, "cor": "ouro", "icone": "bolt", "avatar_url": "/static/img/avatars/rank_06.png?v=3", "personagem": "Analista Relâmpago"},
    {"nivel": 7, "titulo": "Veterano da Banca", "xp_min": 3800, "cor": "platina", "icone": "award", "avatar_url": "/static/img/avatars/rank_07.png?v=3", "personagem": "Mestre de Karatê"},
    {"nivel": 8, "titulo": "Mestre da Constância", "xp_min": 5200, "cor": "platina", "icone": "gem", "avatar_url": "/static/img/avatars/rank_08.png?v=3", "personagem": "Guardião da Chama"},
    {"nivel": 9, "titulo": "Elite da Aprovação", "xp_min": 7000, "cor": "diamante", "icone": "crown", "avatar_url": "/static/img/avatars/rank_09.png?v=3", "personagem": "Campeão da Elite"},
    {"nivel": 10, "titulo": "Auditor Imortal ORBiS", "xp_min": 9500, "cor": "lendario", "icone": "trophy", "avatar_url": "/static/img/avatars/rank_10.png?v=3", "personagem": "Paladino Auditor"},
    {"nivel": 11, "titulo": "Auditor Supremo", "xp_min": 13000, "cor": "lendario", "icone": "crown", "avatar_url": "/static/img/avatars/rank_11.png?v=3", "personagem": "Monarca Fiscal"},
    {"nivel": 12, "titulo": "Grão-Mestre Fiscal", "xp_min": 17000, "cor": "lendario", "icone": "shield", "avatar_url": "/static/img/avatars/rank_12.png?v=3", "personagem": "Cavaleiro Imperial"},
    {"nivel": 13, "titulo": "Oráculo do Edital", "xp_min": 21500, "cor": "lendario", "icone": "compass", "avatar_url": "/static/img/avatars/rank_13.png?v=3", "personagem": "Sábio Oráculo"},
    {"nivel": 14, "titulo": "Arquiteto da Aprovação", "xp_min": 26500, "cor": "mitico", "icone": "gem", "avatar_url": "/static/img/avatars/rank_14.png?v=3", "personagem": "Arquiteto Mestre"},
    {"nivel": 15, "titulo": "Lenda dos Concursos", "xp_min": 32500, "cor": "mitico", "icone": "flame", "avatar_url": "/static/img/avatars/rank_15.png?v=3", "personagem": "Guerreiro Lendário"},
    {"nivel": 16, "titulo": "Titã da Banca", "xp_min": 39000, "cor": "mitico", "icone": "bolt", "avatar_url": "/static/img/avatars/rank_16.png?v=3", "personagem": "Colosso Titânico"},
    {"nivel": 17, "titulo": "Soberano do Gabarito", "xp_min": 46500, "cor": "mitico", "icone": "target", "avatar_url": "/static/img/avatars/rank_17.png?v=4", "personagem": "Soberano Laureado"},
    {"nivel": 18, "titulo": "Guardião da Vaga", "xp_min": 55000, "cor": "mitico", "icone": "award", "avatar_url": "/static/img/avatars/rank_18.png?v=4", "personagem": "Sentinela Guardião"},
    {"nivel": 19, "titulo": "Entidade da Nomeação", "xp_min": 64500, "cor": "mitico", "icone": "star", "avatar_url": "/static/img/avatars/rank_19.png?v=4", "personagem": "Arquimago Cósmico"},
    {"nivel": 20, "titulo": "Divindade ORBiS", "xp_min": 75000, "cor": "mitico", "icone": "trophy", "avatar_url": "/static/img/avatars/rank_20.png?v=3", "personagem": "Zeus — Divindade ORBiS"},
]


def _garantir_config(db: Session) -> ConfiguracaoPainelProva:
    config = db.query(ConfiguracaoPainelProva).first()
    if not config:
        config = ConfiguracaoPainelProva(id=1)
        db.add(config)
        db.commit()
        db.refresh(config)
    return config


def _resolver_edital_ativo_id(db: Session, edital_id: Optional[int] = None) -> Optional[int]:
    if edital_id:
        return int(edital_id)
    ciclo = db.query(CicloEstudos).filter(CicloEstudos.ativo == True).first()
    if ciclo:
        return int(ciclo.edital_id)
    ed = db.query(Edital).filter(Edital.encerrado == False).order_by(Edital.id.desc()).first()
    if not ed:
        ed = db.query(Edital).order_by(Edital.id.desc()).first()
    return int(ed.id) if ed else None


def _carregar_estado_gamificacao(config: ConfiguracaoPainelProva, edital_id: Optional[int] = None) -> Dict[str, Any]:
    """
    Carrega o estado de gamificação isolado por preparação (`edital_id`), garantindo que
    ao iniciar uma nova preparação o progresso de XP bônus e medalhas vistas comece do zero.
    """
    padrao = {"medalhas_vistas": [], "desafio_diario_resgatado_data": None, "xp_bonus_desafios": 0}
    try:
        dados = json.loads(config.marcos_alertados or "{}")
        if not isinstance(dados, dict):
            return dict(padrao)
        por_edital = dados.get("gamificacao_por_edital")
        chave = str(edital_id) if edital_id is not None else "default"
        if isinstance(por_edital, dict) and isinstance(por_edital.get(chave), dict):
            return por_edital[chave]
        # Migração suave: se ainda não existe registro por edital e só havia o legado global
        if not isinstance(por_edital, dict) and isinstance(dados.get("gamificacao"), dict):
            return dados["gamificacao"]
    except Exception:
        pass
    return dict(padrao)


def _salvar_estado_gamificacao(
    db: Session,
    config: ConfiguracaoPainelProva,
    estado_gam: Dict[str, Any],
    edital_id: Optional[int] = None,
) -> None:
    try:
        dados = json.loads(config.marcos_alertados or "{}")
        if not isinstance(dados, dict):
            dados = {}
    except Exception:
        dados = {}
    if not isinstance(dados.get("gamificacao_por_edital"), dict):
        dados["gamificacao_por_edital"] = {}
    chave = str(edital_id) if edital_id is not None else "default"
    dados["gamificacao_por_edital"][chave] = estado_gam
    config.marcos_alertados = json.dumps(dados, ensure_ascii=False)
    db.commit()


def marcar_medalhas_como_vistas(
    db: Session,
    medalha_ids: List[str],
    edital_id: Optional[int] = None,
) -> Dict[str, Any]:
    ed_id = _resolver_edital_ativo_id(db, edital_id)
    config = _garantir_config(db)
    estado = _carregar_estado_gamificacao(config, ed_id)
    vistas = set(estado.get("medalhas_vistas") or [])
    for mid in medalha_ids:
        if mid:
            vistas.add(str(mid))
    estado["medalhas_vistas"] = sorted(list(vistas))
    _salvar_estado_gamificacao(db, config, estado, ed_id)
    return {"sucesso": True, "medalhas_vistas": estado["medalhas_vistas"], "edital_id": ed_id}


def resgatar_desafio_diario_xp(
    db: Session,
    hoje_ref: Optional[date] = None,
    edital_id: Optional[int] = None,
) -> Dict[str, Any]:
    ed_id = _resolver_edital_ativo_id(db, edital_id)
    hoje_str = (hoje_ref or date.today()).isoformat()
    config = _garantir_config(db)
    estado = _carregar_estado_gamificacao(config, ed_id)
    if estado.get("desafio_diario_resgatado_data") != hoje_str:
        estado["desafio_diario_resgatado_data"] = hoje_str
        estado["xp_bonus_desafios"] = int(estado.get("xp_bonus_desafios") or 0) + 150
        _salvar_estado_gamificacao(db, config, estado, ed_id)
    return calcular_gamificacao_aluno(db, edital_id=ed_id, hoje_ref=hoje_ref)


def calcular_gamificacao_aluno(
    db: Session,
    edital_id: Optional[int] = None,
    hoje_ref: Optional[date] = None,
) -> Dict[str, Any]:
    """
    Calcula todas as medalhas, patentes (ranks), XP, sequência de dias, desafio diário
    e identifica medalhas recém-conquistadas para abrir o modal de celebração com fogos e confetes.
    """
    hoje = hoje_ref or date.today()
    config = _garantir_config(db)

    # Preferência de horas/missões por dia do Roteiro
    horas_meta_dia = 2
    dias_meta_semana = int(config.dias_disponiveis_semana or 6)
    try:
        dados_m = json.loads(config.marcos_alertados or "{}")
        if isinstance(dados_m, dict) and isinstance(dados_m.get("roteiro_estudo_config"), dict):
            rc = dados_m["roteiro_estudo_config"]
            horas_meta_dia = max(1, int(round(float(rc.get("horas_por_dia", 2.0)))))
            dias_meta_semana = max(1, int(rc.get("dias_por_semana", dias_meta_semana)))
    except Exception:
        pass

    # Localiza Ciclo e Edital ativo
    ciclo_q = db.query(CicloEstudos)
    if edital_id:
        ciclo = ciclo_q.filter(CicloEstudos.edital_id == edital_id, CicloEstudos.ativo == True).first()
    else:
        ciclo = ciclo_q.filter(CicloEstudos.ativo == True).first()

    edital_q = db.query(Edital).options(selectinload(Edital.disciplinas).selectinload(Disciplina.topicos))
    if ciclo:
        edital = edital_q.filter(Edital.id == ciclo.edital_id).first()
    elif edital_id:
        edital = edital_q.filter(Edital.id == edital_id).first()
    else:
        edital = edital_q.filter(Edital.encerrado == False).order_by(Edital.id.desc()).first()
        if not edital:
            edital = edital_q.order_by(Edital.id.desc()).first()

    estado_gam = _carregar_estado_gamificacao(config, edital.id if edital else edital_id)

    todas_sessoes: List[SessaoEstudo] = []
    if edital:
        todas_sessoes = (
            db.query(SessaoEstudo)
            .join(Disciplina, SessaoEstudo.disciplina_id == Disciplina.id)
            .filter(Disciplina.edital_id == edital.id)
            .order_by(SessaoEstudo.data.asc(), SessaoEstudo.id.asc())
            .all()
        )

    # Métricas reais do aluno
    total_sessoes = len(todas_sessoes)
    total_questoes = sum(int(s.qtd_questoes_total or 0) for s in todas_sessoes)
    total_acertos = sum(int(s.qtd_acertos or 0) for s in todas_sessoes)
    taxa_acerto_global = round((total_acertos / total_questoes) * 100.0, 1) if total_questoes > 0 else 0.0
    total_minutos = sum(int(s.tempo_estudado_minutos or 0) for s in todas_sessoes)
    total_horas = round(total_minutos / 60.0, 1)
    voltas_ciclo = int(ciclo.voltas_completas or 0) if ciclo else 0

    # Agrupamento por data
    sessoes_por_data: Dict[date, List[SessaoEstudo]] = defaultdict(list)
    for s in todas_sessoes:
        if s.data:
            sessoes_por_data[s.data].append(s)

    dias_estudados_total = len(sessoes_por_data)
    missoes_hoje_concluidas = len(sessoes_por_data.get(hoje, []))
    minutos_hoje = sum(int(s.tempo_estudado_minutos or 0) for s in sessoes_por_data.get(hoje, []))
    max_missoes_num_unico_dia = max((len(lista) for lista in sessoes_por_data.values()), default=0)
    dias_com_meta_cumprida = sum(1 for lista in sessoes_por_data.values() if len(lista) >= horas_meta_dia)
    total_missoes_atendidas = sum(min(len(lista), horas_meta_dia) for lista in sessoes_por_data.values())

    # Maior sequência consecutiva de dias cumprindo 100% das missões diárias
    datas_meta_cumprida = sorted(dt_m for dt_m, lista in sessoes_por_data.items() if len(lista) >= horas_meta_dia)
    maior_sequencia_meta_cumprida = 0
    seq_meta_temp = 0
    dt_meta_ant: Optional[date] = None
    for dt_m in datas_meta_cumprida:
        if dt_meta_ant is None or (dt_m - dt_meta_ant).days == 1:
            seq_meta_temp += 1
        elif (dt_m - dt_meta_ant).days > 1:
            seq_meta_temp = 1
        maior_sequencia_meta_cumprida = max(maior_sequencia_meta_cumprida, seq_meta_temp)
        dt_meta_ant = dt_m

    # Missões nos últimos 7 dias (semana atual)
    inicio_janela_7d = hoje - timedelta(days=6)
    missoes_ultimos_7d = sum(
        len(lista) for dt_s, lista in sessoes_por_data.items() if inicio_janela_7d <= dt_s <= hoje
    )
    meta_missoes_semana = horas_meta_dia * dias_meta_semana

    # Sequência atual de dias (streak) e maior sequência histórica
    datas_ordenadas = sorted(sessoes_por_data.keys())
    maior_sequencia_dias = 0
    seq_temp = 0
    dt_ant: Optional[date] = None
    for dt_cur in datas_ordenadas:
        if dt_ant is None or (dt_cur - dt_ant).days == 1:
            seq_temp += 1
        elif (dt_cur - dt_ant).days > 1:
            seq_temp = 1
        maior_sequencia_dias = max(maior_sequencia_dias, seq_temp)
        dt_ant = dt_cur

    sequencia_atual = 0
    cursor_streak = hoje if hoje in sessoes_por_data else (hoje - timedelta(days=1))
    while cursor_streak in sessoes_por_data:
        sequencia_atual += 1
        cursor_streak -= timedelta(days=1)

    # Cobertura do Edital e Tópicos P1 / Mais Cobrados
    todos_topicos: List[Topico] = []
    if edital:
        for d in edital.disciplinas:
            if d.categoria != "REVISAO_ANKI" and d.nome != "REVISÃO ANKI":
                todos_topicos.extend(d.topicos or [])

    topicos_vistos_ids = {s.topico_id for s in todas_sessoes if s.topico_id is not None}
    topicos_concluidos = [t for t in todos_topicos if bool(t.concluido) or (t.id in topicos_vistos_ids)]
    perc_edital = round((len(topicos_concluidos) / len(todos_topicos)) * 100.0, 1) if todos_topicos else 0.0

    topicos_elite = [t for t in todos_topicos if t.prioridade == 1 or bool(t.mais_cobrado)]
    elite_concluidos = [t for t in topicos_elite if bool(t.concluido) or (t.id in topicos_vistos_ids)]
    qtd_elite_vistos = len(elite_concluidos)
    perc_elite = round((qtd_elite_vistos / len(topicos_elite)) * 100.0, 1) if topicos_elite else 0.0

    # Sessão de alta precisão (>= 15 questões e >= 80% / 90% de acerto)
    melhor_perc_sessao_15q = max(
        (float(s.percentual_acerto or 0.0) for s in todas_sessoes if int(s.qtd_questoes_total or 0) >= 15),
        default=0.0,
    )
    sessoes_90_porcento_20q = sum(
        1 for s in todas_sessoes
        if int(s.qtd_questoes_total or 0) >= 20 and float(s.percentual_acerto or 0.0) >= 90.0
    )
    revisoes_anki_concluidas = sum(1 for s in todas_sessoes if bool(s.is_revisao_anki))
    disciplinas_fechadas_100 = 0
    if edital:
        for d in edital.disciplinas:
            if d.categoria == "REVISAO_ANKI" or d.nome == "REVISÃO ANKI":
                continue
            tops_d = list(d.topicos or [])
            if tops_d and all(bool(t.concluido) or (t.id in topicos_vistos_ids) for t in tops_d):
                disciplinas_fechadas_100 += 1

    # Catálogo de Medalhas (46 conquistas com estilos distintos por dificuldade: bronze, prata, ouro, platina, diamante, lendario)
    catalogo_medalhas = [
        # 1. MISSÕES & CONSTÂNCIA
        {
            "id": "missao_primeira_sessao",
            "titulo": "Primeiro Passo",
            "categoria": "Missões & Roteiro",
            "tier": "bronze",
            "tier_label": "Bronze",
            "icone": "star",
            "xp": 50,
            "descricao": "Registrou sua primeira sessão de estudo no ORBiS.",
            "progresso_atual": total_sessoes,
            "meta": 1,
            "unidade": "sessão",
        },
        {
            "id": "missao_primeiro_dia",
            "titulo": "Missão Cumprida",
            "categoria": "Missões & Roteiro",
            "tier": "bronze",
            "tier_label": "Bronze",
            "icone": "target",
            "xp": 100,
            "descricao": f"Cumpriu todas as {horas_meta_dia} missões planejadas do dia.",
            "progresso_atual": dias_com_meta_cumprida,
            "meta": 1,
            "unidade": "dia completo",
        },
        {
            "id": "missao_3_dias_seguidos",
            "titulo": "Trinca de Foco — 3 Dias",
            "categoria": "Missões & Roteiro",
            "tier": "bronze",
            "tier_label": "Bronze",
            "icone": "flame",
            "xp": 120,
            "descricao": "Manteve uma sequência de 3 dias consecutivos estudando.",
            "progresso_atual": maior_sequencia_dias,
            "meta": 3,
            "unidade": "dias seguidos",
        },
        {
            "id": "missao_alem_do_dever",
            "titulo": "Além do Dever (Hora Extra)",
            "categoria": "Missões & Roteiro",
            "tier": "prata",
            "tier_label": "Prata",
            "icone": "bolt",
            "xp": 180,
            "descricao": f"Superou a meta diária fazendo {horas_meta_dia + 1} ou mais missões em um único dia.",
            "progresso_atual": max_missoes_num_unico_dia,
            "meta": horas_meta_dia + 1,
            "unidade": "missões/dia",
        },
        {
            "id": "missao_5_dias_meta",
            "titulo": "Consistência Real — 5 Dias",
            "categoria": "Missões & Roteiro",
            "tier": "prata",
            "tier_label": "Prata",
            "icone": "check",
            "xp": 220,
            "descricao": f"Bateu a meta completa de {horas_meta_dia} missões diárias em 5 dias.",
            "progresso_atual": dias_com_meta_cumprida,
            "meta": 5,
            "unidade": "dias com meta",
        },
        {
            "id": "missao_regularidade_3_dias",
            "titulo": "Regularidade nas Missões (3 Dias 100%)",
            "categoria": "Missões & Roteiro",
            "tier": "prata",
            "tier_label": "Prata",
            "icone": "calendar",
            "xp": 250,
            "descricao": f"Cumpriu 100% das {horas_meta_dia} missões diárias por 3 dias seguidos.",
            "progresso_atual": maior_sequencia_meta_cumprida,
            "meta": 3,
            "unidade": "dias seguidos 100%",
        },
        {
            "id": "missao_regularidade_7_dias",
            "titulo": "Semana Perfeita de Missões (7 Dias)",
            "categoria": "Missões & Roteiro",
            "tier": "ouro",
            "tier_label": "Ouro",
            "icone": "calendar",
            "xp": 450,
            "descricao": f"Manteve regularidade total cumprindo todas as {horas_meta_dia} missões diárias por 7 dias seguidos.",
            "progresso_atual": maior_sequencia_meta_cumprida,
            "meta": 7,
            "unidade": "dias seguidos 100%",
        },
        {
            "id": "missao_qtd_50_atendidas",
            "titulo": "50 Missões Diárias Atendidas",
            "categoria": "Missões & Roteiro",
            "tier": "ouro",
            "tier_label": "Ouro",
            "icone": "target",
            "xp": 400,
            "descricao": "Concluiu 50 missões diárias planejadas dentro da sua preparação.",
            "progresso_atual": total_missoes_atendidas,
            "meta": 50,
            "unidade": "missões",
        },
        {
            "id": "missao_meta_20_dias",
            "titulo": "20 Dias de Meta 100% Batida",
            "categoria": "Missões & Roteiro",
            "tier": "platina",
            "tier_label": "Platina",
            "icone": "check",
            "xp": 750,
            "descricao": f"Atendeu integralmente todas as {horas_meta_dia} missões do dia em 20 dias diferentes.",
            "progresso_atual": dias_com_meta_cumprida,
            "meta": 20,
            "unidade": "dias com meta",
        },
        {
            "id": "missao_regularidade_14_dias",
            "titulo": "Constância de Ferro (14 Dias 100%)",
            "categoria": "Missões & Roteiro",
            "tier": "platina",
            "tier_label": "Platina",
            "icone": "flame",
            "xp": 800,
            "descricao": "Bateu 100% da meta diária de missões durante 14 dias consecutivos.",
            "progresso_atual": maior_sequencia_meta_cumprida,
            "meta": 14,
            "unidade": "dias seguidos 100%",
        },
        {
            "id": "missao_qtd_150_atendidas",
            "titulo": "150 Missões Diárias Atendidas",
            "categoria": "Missões & Roteiro",
            "tier": "diamante",
            "tier_label": "Diamante",
            "icone": "gem",
            "xp": 1000,
            "descricao": "Atingiu a marca expressiva de 150 missões diárias cumpridas na preparação.",
            "progresso_atual": total_missoes_atendidas,
            "meta": 150,
            "unidade": "missões",
        },
        {
            "id": "missao_regularidade_30_dias",
            "titulo": "Mestre da Disciplina (30 Dias 100%)",
            "categoria": "Missões & Roteiro",
            "tier": "diamante",
            "tier_label": "Diamante",
            "icone": "crown",
            "xp": 1400,
            "descricao": "Completou 30 dias seguidos cumprindo 100% das missões diárias sem falhar.",
            "progresso_atual": maior_sequencia_meta_cumprida,
            "meta": 30,
            "unidade": "dias seguidos 100%",
        },
        {
            "id": "missao_qtd_300_atendidas",
            "titulo": "300 Missões Diárias Atendidas",
            "categoria": "Missões & Roteiro",
            "tier": "lendario",
            "tier_label": "Lendário",
            "icone": "trophy",
            "xp": 1800,
            "descricao": "Cumpriu 300 missões diárias do roteiro com regularidade de alto nível.",
            "progresso_atual": total_missoes_atendidas,
            "meta": 300,
            "unidade": "missões",
        },
        {
            "id": "missao_7_dias_seguidos",
            "titulo": "Semana Ininterrupta — 7 Dias",
            "categoria": "Missões & Roteiro",
            "tier": "ouro",
            "tier_label": "Ouro",
            "icone": "flame",
            "xp": 380,
            "descricao": "Manteve uma sequência de 7 dias seguidos sem quebrar o ritmo.",
            "progresso_atual": maior_sequencia_dias,
            "meta": 7,
            "unidade": "dias seguidos",
        },
        {
            "id": "missao_semana_completa",
            "titulo": "Semana Impecável",
            "categoria": "Missões & Roteiro",
            "tier": "ouro",
            "tier_label": "Ouro",
            "icone": "calendar",
            "xp": 350,
            "descricao": f"Realizou todas as {meta_missoes_semana} missões planejadas na semana.",
            "progresso_atual": missoes_ultimos_7d,
            "meta": meta_missoes_semana,
            "unidade": "missões na semana",
        },
        {
            "id": "missao_10_dias",
            "titulo": "Blindagem de 10 Dias",
            "categoria": "Missões & Roteiro",
            "tier": "platina",
            "tier_label": "Platina",
            "icone": "flame",
            "xp": 450,
            "descricao": "Completou 10 dias de estudos e missões registradas no sistema.",
            "progresso_atual": dias_estudados_total,
            "meta": 10,
            "unidade": "dias estudados",
        },
        {
            "id": "missao_15_dias_seguidos",
            "titulo": "Foco Inabalável — 15 Dias Seguidos",
            "categoria": "Missões & Roteiro",
            "tier": "diamante",
            "tier_label": "Diamante",
            "icone": "gem",
            "xp": 780,
            "descricao": "Manteve uma sequência invicta de 15 dias consecutivos de estudo.",
            "progresso_atual": maior_sequencia_dias,
            "meta": 15,
            "unidade": "dias seguidos",
        },
        {
            "id": "missao_21_dias",
            "titulo": "Hábito de Aço — 21 Dias",
            "categoria": "Missões & Roteiro",
            "tier": "diamante",
            "tier_label": "Diamante",
            "icone": "gem",
            "xp": 750,
            "descricao": "Alcançou 21 dias ativos cumprindo o roteiro de estudos.",
            "progresso_atual": dias_estudados_total,
            "meta": 21,
            "unidade": "dias estudados",
        },
        {
            "id": "missao_45_dias",
            "titulo": "Guardião da Constância — 45 Dias",
            "categoria": "Missões & Roteiro",
            "tier": "lendario",
            "tier_label": "Lendário",
            "icone": "crown",
            "xp": 1200,
            "descricao": "Alcançou a marca histórica de 45 dias de estudos cumpridos.",
            "progresso_atual": dias_estudados_total,
            "meta": 45,
            "unidade": "dias estudados",
        },

        # 2. VOLTAS & SESSÕES DO CICLO DE ESTUDOS
        {
            "id": "ciclo_10_sessoes",
            "titulo": "Motor Ligado — 10 Sessões",
            "categoria": "Ciclo de Estudos",
            "tier": "bronze",
            "tier_label": "Bronze",
            "icone": "cycle",
            "xp": 110,
            "descricao": "Completou 10 sessões de estudo na esteira do Ciclo.",
            "progresso_atual": total_sessoes,
            "meta": 10,
            "unidade": "sessões",
        },
        {
            "id": "ciclo_1_volta",
            "titulo": "1ª Volta no Ciclo",
            "categoria": "Ciclo de Estudos",
            "tier": "bronze",
            "tier_label": "Bronze",
            "icone": "cycle",
            "xp": 150,
            "descricao": "Completou o primeiro giro completo por todas as disciplinas do Ciclo.",
            "progresso_atual": voltas_ciclo,
            "meta": 1,
            "unidade": "volta",
        },
        {
            "id": "ciclo_2_voltas",
            "titulo": "Dupla Rotação — 2 Voltas",
            "categoria": "Ciclo de Estudos",
            "tier": "prata",
            "tier_label": "Prata",
            "icone": "cycle",
            "xp": 210,
            "descricao": "Completou 2 voltas inteiras no Ciclo de Estudos.",
            "progresso_atual": voltas_ciclo,
            "meta": 2,
            "unidade": "voltas",
        },
        {
            "id": "ciclo_30_sessoes",
            "titulo": "Engrenagem Afiada — 30 Sessões",
            "categoria": "Ciclo de Estudos",
            "tier": "prata",
            "tier_label": "Prata",
            "icone": "compass",
            "xp": 240,
            "descricao": "Completou 30 sessões de estudo registradas no Ciclo.",
            "progresso_atual": total_sessoes,
            "meta": 30,
            "unidade": "sessões",
        },
        {
            "id": "ciclo_3_voltas",
            "titulo": "Ritmo de Cruzeiro — 3 Voltas",
            "categoria": "Ciclo de Estudos",
            "tier": "prata",
            "tier_label": "Prata",
            "icone": "cycle",
            "xp": 300,
            "descricao": "Atingiu 3 voltas completas no Ciclo de Estudos.",
            "progresso_atual": voltas_ciclo,
            "meta": 3,
            "unidade": "voltas",
        },
        {
            "id": "ciclo_60_sessoes",
            "titulo": "Máquina de Aprovação — 60 Sessões",
            "categoria": "Ciclo de Estudos",
            "tier": "ouro",
            "tier_label": "Ouro",
            "icone": "bolt",
            "xp": 450,
            "descricao": "Atingiu 60 sessões de estudo concluídas no Ciclo.",
            "progresso_atual": total_sessoes,
            "meta": 60,
            "unidade": "sessões",
        },
        {
            "id": "ciclo_5_voltas",
            "titulo": "Veterano do Ciclo — 5 Voltas",
            "categoria": "Ciclo de Estudos",
            "tier": "ouro",
            "tier_label": "Ouro",
            "icone": "trophy",
            "xp": 500,
            "descricao": "Atingiu 5 voltas completas na esteira do Ciclo de Estudos.",
            "progresso_atual": voltas_ciclo,
            "meta": 5,
            "unidade": "voltas",
        },
        {
            "id": "ciclo_10_voltas",
            "titulo": "Mestre da Esteira — 10 Voltas",
            "categoria": "Ciclo de Estudos",
            "tier": "diamante",
            "tier_label": "Diamante",
            "icone": "crown",
            "xp": 950,
            "descricao": "Atingiu a marca de 10 voltas completas no Ciclo de Estudos.",
            "progresso_atual": voltas_ciclo,
            "meta": 10,
            "unidade": "voltas",
        },

        # 3. QUESTÕES RESOLVIDAS
        {
            "id": "questoes_50",
            "titulo": "Aquecimento de Banca — 50 Questões",
            "categoria": "Resolução de Questões",
            "tier": "bronze",
            "tier_label": "Bronze",
            "icone": "check",
            "xp": 80,
            "descricao": "Resolveu suas primeiras 50 questões no sistema.",
            "progresso_atual": total_questoes,
            "meta": 50,
            "unidade": "questões",
        },
        {
            "id": "questoes_100",
            "titulo": "Primeiras 100 Questões",
            "categoria": "Resolução de Questões",
            "tier": "bronze",
            "tier_label": "Bronze",
            "icone": "check",
            "xp": 120,
            "descricao": "Resolveu 100 questões de concurso registradas no sistema.",
            "progresso_atual": total_questoes,
            "meta": 100,
            "unidade": "questões",
        },
        {
            "id": "questoes_200",
            "titulo": "Bateria de 200 Questões",
            "categoria": "Resolução de Questões",
            "tier": "bronze",
            "tier_label": "Bronze",
            "icone": "shield",
            "xp": 180,
            "descricao": "Atingiu 200 questões resolvidas na preparação.",
            "progresso_atual": total_questoes,
            "meta": 200,
            "unidade": "questões",
        },
        {
            "id": "questoes_300",
            "titulo": "Trator de Prova — 300 Questões",
            "categoria": "Resolução de Questões",
            "tier": "prata",
            "tier_label": "Prata",
            "icone": "bolt",
            "xp": 260,
            "descricao": "Atingiu 300 questões resolvidas com foco na banca.",
            "progresso_atual": total_questoes,
            "meta": 300,
            "unidade": "questões",
        },
        {
            "id": "questoes_500",
            "titulo": "Meio Milhar — 500 Questões",
            "categoria": "Resolução de Questões",
            "tier": "ouro",
            "tier_label": "Ouro",
            "icone": "star",
            "xp": 400,
            "descricao": "Superou a marca de 500 questões resolvidas.",
            "progresso_atual": total_questoes,
            "meta": 500,
            "unidade": "questões",
        },
        {
            "id": "questoes_750",
            "titulo": "Ritmo de Elite — 750 Questões",
            "categoria": "Resolução de Questões",
            "tier": "ouro",
            "tier_label": "Ouro",
            "icone": "target",
            "xp": 480,
            "descricao": "Alcançou 750 questões resolvidas com foco total na banca.",
            "progresso_atual": total_questoes,
            "meta": 750,
            "unidade": "questões",
        },
        {
            "id": "questoes_1000",
            "titulo": "Clube das 1.000 Questões",
            "categoria": "Resolução de Questões",
            "tier": "platina",
            "tier_label": "Platina",
            "icone": "award",
            "xp": 650,
            "descricao": "Alcançou 1.000 questões resolvidas na preparação.",
            "progresso_atual": total_questoes,
            "meta": 1000,
            "unidade": "questões",
        },
        {
            "id": "questoes_1500",
            "titulo": "Arsenal Completo — 1.500 Questões",
            "categoria": "Resolução de Questões",
            "tier": "platina",
            "tier_label": "Platina",
            "icone": "shield",
            "xp": 780,
            "descricao": "Ultrapassou 1.500 questões resolvidas no edital.",
            "progresso_atual": total_questoes,
            "meta": 1500,
            "unidade": "questões",
        },
        {
            "id": "questoes_2500",
            "titulo": "Especialista de Banca — 2.500 Questões",
            "categoria": "Resolução de Questões",
            "tier": "diamante",
            "tier_label": "Diamante",
            "icone": "gem",
            "xp": 1100,
            "descricao": "Alcançou 2.500 questões resolvidas na preparação.",
            "progresso_atual": total_questoes,
            "meta": 2500,
            "unidade": "questões",
        },
        {
            "id": "questoes_5000",
            "titulo": "Lenda das Questões — 5.000 Questões",
            "categoria": "Resolução de Questões",
            "tier": "lendario",
            "tier_label": "Lendário",
            "icone": "crown",
            "xp": 1800,
            "descricao": "Alcançou a marca lendária de 5.000 questões resolvidas.",
            "progresso_atual": total_questoes,
            "meta": 5000,
            "unidade": "questões",
        },

        # 4. EDITAL VERTICALIZADO & PRIORIDADES (PARETO)
        {
            "id": "pareto_5_p1_mc",
            "titulo": "Olho Clínico — 5 Tópicos P1/🔥",
            "categoria": "Edital & Pareto",
            "tier": "bronze",
            "tier_label": "Bronze",
            "icone": "flame",
            "xp": 110,
            "descricao": "Concluiu seus primeiros 5 tópicos P1 ⚡ ou Mais Cobrados (🔥).",
            "progresso_atual": qtd_elite_vistos,
            "meta": 5,
            "unidade": "tópicos P1/🔥",
        },
        {
            "id": "edital_10_perc",
            "titulo": "Desbravador — 10% do Edital",
            "categoria": "Edital & Pareto",
            "tier": "bronze",
            "tier_label": "Bronze",
            "icone": "compass",
            "xp": 130,
            "descricao": "Cobriu os primeiros 10% de tópicos do Edital Verticalizado.",
            "progresso_atual": perc_edital,
            "meta": 10,
            "unidade": "% do edital",
        },
        {
            "id": "edital_25_perc",
            "titulo": "Base Sólida — 25% do Edital",
            "categoria": "Edital & Pareto",
            "tier": "prata",
            "tier_label": "Prata",
            "icone": "shield",
            "xp": 280,
            "descricao": "Atingiu 25% de cobertura dos tópicos do Edital Verticalizado.",
            "progresso_atual": perc_edital,
            "meta": 25,
            "unidade": "% do edital",
        },
        {
            "id": "pareto_15_p1_mc",
            "titulo": "Caçador de P1 & Mais Cobrados",
            "categoria": "Edital & Pareto",
            "tier": "ouro",
            "tier_label": "Ouro",
            "icone": "flame",
            "xp": 420,
            "descricao": "Concluiu 15 tópicos classificados como Prioridade Alta (P1 ⚡) ou Mais Cobrados (🔥).",
            "progresso_atual": qtd_elite_vistos,
            "meta": 15,
            "unidade": "tópicos P1/🔥",
        },
        {
            "id": "edital_disciplina_100",
            "titulo": "Matéria Zerada — 100% Concluída",
            "categoria": "Edital & Pareto",
            "tier": "ouro",
            "tier_label": "Ouro",
            "icone": "check",
            "xp": 420,
            "descricao": "Concluiu 100% dos tópicos de pelo menos 1 disciplina do edital.",
            "progresso_atual": disciplinas_fechadas_100,
            "meta": 1,
            "unidade": "disciplina 100%",
        },
        {
            "id": "edital_50_perc",
            "titulo": "Metade da Montanha — 50% do Edital",
            "categoria": "Edital & Pareto",
            "tier": "platina",
            "tier_label": "Platina",
            "icone": "award",
            "xp": 600,
            "descricao": "Venceu 50% de todos os tópicos do Edital Verticalizado.",
            "progresso_atual": perc_edital,
            "meta": 50,
            "unidade": "% do edital",
        },
        {
            "id": "pareto_30_p1_mc",
            "titulo": "Cirurgião do Edital — 30 P1/🔥",
            "categoria": "Edital & Pareto",
            "tier": "platina",
            "tier_label": "Platina",
            "icone": "bolt",
            "xp": 620,
            "descricao": "Concluiu 30 tópicos classificados como Prioridade Alta (P1 ⚡) ou Mais Cobrados (🔥).",
            "progresso_atual": qtd_elite_vistos,
            "meta": 30,
            "unidade": "tópicos P1/🔥",
        },
        {
            "id": "edital_70_perc",
            "titulo": "Reta de Chegada — 70% do Edital",
            "categoria": "Edital & Pareto",
            "tier": "diamante",
            "tier_label": "Diamante",
            "icone": "gem",
            "xp": 900,
            "descricao": "Alcançou 70% de cobertura completa do Edital Verticalizado.",
            "progresso_atual": perc_edital,
            "meta": 70,
            "unidade": "% do edital",
        },
        {
            "id": "edital_85_perc",
            "titulo": "Dominador do Edital — 85%+",
            "categoria": "Edital & Pareto",
            "tier": "lendario",
            "tier_label": "Lendário",
            "icone": "trophy",
            "xp": 1400,
            "descricao": "Atingiu a meta de excelência de 85% de cobertura do edital.",
            "progresso_atual": perc_edital,
            "meta": 85,
            "unidade": "% do edital",
        },

        # 5. PRECISÃO & CARGA HORÁRIA
        {
            "id": "horas_5h",
            "titulo": "Primeiras 5 Horas Líquidas",
            "categoria": "Performance & Horas",
            "tier": "bronze",
            "tier_label": "Bronze",
            "icone": "star",
            "xp": 90,
            "descricao": "Acumulou 5 horas líquidas de estudo cronometrado.",
            "progresso_atual": total_horas,
            "meta": 5,
            "unidade": "horas",
        },
        {
            "id": "horas_10h",
            "titulo": "Dezena de Foco — 10 Horas",
            "categoria": "Performance & Horas",
            "tier": "prata",
            "tier_label": "Prata",
            "icone": "compass",
            "xp": 170,
            "descricao": "Acumulou 10 horas líquidas de estudo focado.",
            "progresso_atual": total_horas,
            "meta": 10,
            "unidade": "horas",
        },
        {
            "id": "revisao_anki_10",
            "titulo": "Memória Blindada — 10 Revisões",
            "categoria": "Performance & Horas",
            "tier": "prata",
            "tier_label": "Prata",
            "icone": "shield",
            "xp": 210,
            "descricao": "Concluiu 10 sessões de revisão espaçada / Anki.",
            "progresso_atual": revisoes_anki_concluidas,
            "meta": 10,
            "unidade": "revisões",
        },
        {
            "id": "precisao_sessao_80",
            "titulo": "Mira Calibrada (80%+ de Acerto)",
            "categoria": "Performance & Horas",
            "tier": "prata",
            "tier_label": "Prata",
            "icone": "target",
            "xp": 200,
            "descricao": "Alcançou 80% ou mais de acerto em uma bateria de pelo menos 15 questões.",
            "progresso_atual": round(melhor_perc_sessao_15q, 1),
            "meta": 80,
            "unidade": "% na bateria",
        },
        {
            "id": "precisao_sessao_90",
            "titulo": "Sniper da Banca (90%+ de Acerto)",
            "categoria": "Performance & Horas",
            "tier": "ouro",
            "tier_label": "Ouro",
            "icone": "bolt",
            "xp": 360,
            "descricao": "Alcançou 90% ou mais de acerto em uma bateria de pelo menos 15 questões.",
            "progresso_atual": round(melhor_perc_sessao_15q, 1),
            "meta": 90,
            "unidade": "% na bateria",
        },
        {
            "id": "horas_20h",
            "titulo": "20 Horas Líquidas de Foco",
            "categoria": "Performance & Horas",
            "tier": "ouro",
            "tier_label": "Ouro",
            "icone": "star",
            "xp": 320,
            "descricao": "Acumulou 20 horas líquidas de estudo cronometrado.",
            "progresso_atual": total_horas,
            "meta": 20,
            "unidade": "horas",
        },
        {
            "id": "horas_60h",
            "titulo": "Maratonista — 60 Horas Líquidas",
            "categoria": "Performance & Horas",
            "tier": "diamante",
            "tier_label": "Diamante",
            "icone": "gem",
            "xp": 800,
            "descricao": "Acumulou 60 horas líquidas de estudo focado.",
            "progresso_atual": total_horas,
            "meta": 60,
            "unidade": "horas",
        },
        {
            "id": "horas_100h",
            "titulo": "Centurião — 100 Horas Líquidas",
            "categoria": "Performance & Horas",
            "tier": "lendario",
            "tier_label": "Lendário",
            "icone": "trophy",
            "xp": 1600,
            "descricao": "Alcançou a marca histórica de 100 horas líquidas de estudo focado.",
            "progresso_atual": total_horas,
            "meta": 100,
            "unidade": "horas",
        },
        # 6. TROFÉUS MÍTICOS (NÍVEL MUITO DIFÍCIL)
        {
            "id": "mitico_sequencia_100_dias",
            "titulo": "Inquebrável — 100 Dias Seguidos",
            "categoria": "Missões & Roteiro",
            "tier": "mitico",
            "tier_label": "Mítico",
            "icone": "flame",
            "xp": 2000,
            "descricao": "Manteve uma sequência ininterrupta de 100 dias consecutivos estudando.",
            "progresso_atual": maior_sequencia_dias,
            "meta": 100,
            "unidade": "dias seguidos",
        },
        {
            "id": "mitico_180_dias_estudados",
            "titulo": "Maratonista Semestral (180 Dias)",
            "categoria": "Missões & Roteiro",
            "tier": "mitico",
            "tier_label": "Mítico",
            "icone": "calendar",
            "xp": 2200,
            "descricao": "Registrou estudos em 180 dias diferentes ao longo da preparação.",
            "progresso_atual": dias_estudados_total,
            "meta": 180,
            "unidade": "dias",
        },
        {
            "id": "mitico_25_voltas_ciclo",
            "titulo": "Senhor dos Ciclos (25 Voltas)",
            "categoria": "Ciclo de Estudos",
            "tier": "mitico",
            "tier_label": "Mítico",
            "icone": "cycle",
            "xp": 2000,
            "descricao": "Completou impressionantes 25 voltas inteiras no ciclo de estudos.",
            "progresso_atual": voltas_ciclo,
            "meta": 25,
            "unidade": "voltas",
        },
        {
            "id": "mitico_300_sessoes",
            "titulo": "Veterano de 300 Batalhas",
            "categoria": "Ciclo de Estudos",
            "tier": "mitico",
            "tier_label": "Mítico",
            "icone": "shield",
            "xp": 2000,
            "descricao": "Concluiu 300 sessões completas de estudo registradas no ciclo.",
            "progresso_atual": total_sessoes,
            "meta": 300,
            "unidade": "sessões",
        },
        {
            "id": "mitico_10000_questoes",
            "titulo": "Máquina de 10.000 Questões",
            "categoria": "Resolução de Questões",
            "tier": "mitico",
            "tier_label": "Mítico",
            "icone": "target",
            "xp": 2500,
            "descricao": "Superou a marca épica de 10.000 questões resolvidas na plataforma.",
            "progresso_atual": total_questoes,
            "meta": 10000,
            "unidade": "questões",
        },
        {
            "id": "mitico_7500_acertos",
            "titulo": "Sniper Supremo (7.500 Acertos)",
            "categoria": "Resolução de Questões",
            "tier": "mitico",
            "tier_label": "Mítico",
            "icone": "check",
            "xp": 2500,
            "descricao": "Cravou 7.500 questões corretas com consistência de alto nível.",
            "progresso_atual": total_acertos,
            "meta": 7500,
            "unidade": "acertos",
        },
        {
            "id": "mitico_edital_100_perc",
            "titulo": "Edital 100% Zerado",
            "categoria": "Edital & Pareto",
            "tier": "mitico",
            "tier_label": "Mítico",
            "icone": "crown",
            "xp": 3000,
            "descricao": "Concluiu todos os tópicos do edital completo (100% de cobertura).",
            "progresso_atual": perc_edital,
            "meta": 100,
            "unidade": "%",
        },
        {
            "id": "mitico_5_disciplinas_100",
            "titulo": "Domínio Multidisciplinar (5x 100%)",
            "categoria": "Edital & Pareto",
            "tier": "mitico",
            "tier_label": "Mítico",
            "icone": "award",
            "xp": 2200,
            "descricao": "Fechou 100% dos tópicos de pelo menos 5 disciplinas do edital.",
            "progresso_atual": disciplinas_fechadas_100,
            "meta": 5,
            "unidade": "disciplinas",
        },
        {
            "id": "mitico_500_horas",
            "titulo": "Titã das 500 Horas Líquidas",
            "categoria": "Performance & Horas",
            "tier": "mitico",
            "tier_label": "Mítico",
            "icone": "trophy",
            "xp": 2800,
            "descricao": "Acumulou 500 horas líquidas de estudo focado de alto rendimento.",
            "progresso_atual": total_horas,
            "meta": 500,
            "unidade": "horas",
        },
        {
            "id": "mitico_10_sessoes_90_20q",
            "titulo": "Precisão Cirúrgica (10x 90%+)",
            "categoria": "Performance & Horas",
            "tier": "mitico",
            "tier_label": "Mítico",
            "icone": "gem",
            "xp": 2000,
            "descricao": "Alcançou 90% ou mais de acerto em 10 sessões com pelo menos 20 questões cada.",
            "progresso_atual": sessoes_90_porcento_20q,
            "meta": 10,
            "unidade": "sessões",
        },
    ]

    vistas_set: Set[str] = set(estado_gam.get("medalhas_vistas") or [])
    medalhas_processadas: List[Dict[str, Any]] = []
    medalhas_recem_conquistadas: List[Dict[str, Any]] = []
    xp_medalhas = 0

    for m in catalogo_medalhas:
        prog = float(m["progresso_atual"] or 0.0)
        meta_val = float(m["meta"] or 1.0)
        conquistada = prog >= meta_val
        perc_prog = round(min(100.0, max(0.0, (prog / meta_val) * 100.0)), 1)
        faltam = round(max(0.0, meta_val - prog), 1)
        if faltam.is_integer():
            faltam = int(faltam)
        if prog.is_integer():
            prog_fmt = int(prog)
        else:
            prog_fmt = round(prog, 1)

        eh_nova = conquistada and (m["id"] not in vistas_set)
        if conquistada:
            xp_medalhas += int(m["xp"])

        item_m = {
            **m,
            "progresso_atual": prog_fmt,
            "percentual_progresso": perc_prog,
            "faltam_para_conquistar": faltam,
            "conquistada": conquistada,
            "eh_nova": eh_nova,
        }
        medalhas_processadas.append(item_m)
        if eh_nova:
            medalhas_recem_conquistadas.append(item_m)

    # XP Total = XP de medalhas + XP por sessões/questões + bônus de desafios
    xp_atividade = (total_sessoes * 15) + (total_questoes * 2) + int(estado_gam.get("xp_bonus_desafios") or 0)
    xp_total = xp_medalhas + xp_atividade

    # Determina Rank atual e próximo Rank
    rank_atual = RANKS_SISTEMA[0]
    proximo_rank = None
    for idx_r, r_item in enumerate(RANKS_SISTEMA):
        if xp_total >= r_item["xp_min"]:
            rank_atual = r_item
            proximo_rank = RANKS_SISTEMA[idx_r + 1] if idx_r + 1 < len(RANKS_SISTEMA) else None
        else:
            break

    if proximo_rank:
        faixa_nivel = max(1, proximo_rank["xp_min"] - rank_atual["xp_min"])
        xp_no_nivel = max(0, xp_total - rank_atual["xp_min"])
        perc_nivel = round(min(100.0, (xp_no_nivel / faixa_nivel) * 100.0), 1)
        faltam_xp_proximo = max(0, proximo_rank["xp_min"] - xp_total)
    else:
        xp_no_nivel = xp_total
        faixa_nivel = xp_total
        perc_nivel = 100.0
        faltam_xp_proximo = 0

    # Próxima medalha mais próxima de ser conquistada
    nao_conquistadas = [m for m in medalhas_processadas if not m["conquistada"]]
    nao_conquistadas.sort(key=lambda x: (-x["percentual_progresso"], x["xp"]))
    proxima_medalha = nao_conquistadas[0] if nao_conquistadas else None

    # Desafio Diário (cumprir as missões do dia ou estudar pelo menos 60 min hoje)
    meta_min_desafio = horas_meta_dia * 60
    perc_desafio_hoje = round(min(100.0, (minutos_hoje / max(1, meta_min_desafio)) * 100.0), 1)
    desafio_concluido = minutos_hoje >= meta_min_desafio or missoes_hoje_concluidas >= horas_meta_dia
    desafio_resgatado = estado_gam.get("desafio_diario_resgatado_data") == hoje.isoformat()

    # Todos os ranks com status de desbloqueio
    todos_ranks = [
        {
            **r,
            "desbloqueado": xp_total >= r["xp_min"],
            "atual": r["nivel"] == rank_atual["nivel"],
        }
        for r in RANKS_SISTEMA
    ]

    qtd_conquistadas = sum(1 for m in medalhas_processadas if m["conquistada"])

    return {
        "xp_total": xp_total,
        "xp_no_nivel": xp_no_nivel,
        "xp_meta_nivel": faixa_nivel,
        "percentual_nivel": perc_nivel,
        "rank_atual": rank_atual,
        "proximo_rank": proximo_rank,
        "faltam_xp_proximo_rank": faltam_xp_proximo,
        "sequencia_atual_dias": sequencia_atual,
        "maior_sequencia_dias": maior_sequencia_dias,
        "desafio_diario": {
            "titulo": f"Cumprir {horas_meta_dia} missão(ões) de estudo hoje ({meta_min_desafio} min).",
            "minutos_estudados_hoje": minutos_hoje,
            "meta_minutos_hoje": meta_min_desafio,
            "missoes_concluidas_hoje": missoes_hoje_concluidas,
            "meta_missoes_hoje": horas_meta_dia,
            "percentual": perc_desafio_hoje,
            "concluido": desafio_concluido,
            "resgatado": desafio_resgatado,
            "xp_recompensa": 150,
        },
        "resumo_conquistas": {
            "conquistadas": qtd_conquistadas,
            "total": len(medalhas_processadas),
            "novas_nao_vistas": len(medalhas_recem_conquistadas),
        },
        "proxima_medalha": proxima_medalha,
        "medalhas": medalhas_processadas,
        "medalhas_recem_conquistadas": medalhas_recem_conquistadas,
        "todos_ranks": todos_ranks,
    }
