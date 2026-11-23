import json
import math
from typing import List, Dict, Tuple, Optional, Any
from sqlalchemy.orm import Session, selectinload
from app.models.edital import Edital
from app.models.disciplina import Disciplina
from app.models.ciclo import CicloEstudos, BlocoCiclo
from app.models.sessao import SessaoEstudo

def calcular_fatores_importancia(disciplinas: List[Disciplina]) -> Dict[int, float]:
    """
    Calcula o Fator de Importância de cada disciplina:
    F_i = peso_prova * relevancia_dificuldade * (1 + ln(1 + qtd_topicos)) * (1 + ln(1 + qtd_questoes))
    Garante que matérias com mais peso, mais dificuldade, mais tópicos e mais questões tenham maior representação.
    """
    fatores = {}
    for d in disciplinas:
        qtd_topicos = len(d.topicos) if d.topicos else 1
        peso = max(d.peso_prova or 1.0, 0.5)
        dificuldade = max(d.relevancia_dificuldade or 3, 1)
        questoes = d.qtd_questoes_prova or 0
        
        fator_topicos = 1.0 + math.log1p(qtd_topicos)
        fator_questoes = 1.0 + math.log1p(questoes) if questoes > 0 else 1.0
        
        fator_total = peso * (dificuldade / 3.0) * fator_topicos * fator_questoes
        fatores[d.id] = round(fator_total, 3)
    return fatores

def distribuir_blocos_disciplinas(disciplinas: List[Disciplina], total_blocos: int) -> Dict[int, int]:
    """
    Distribui os blocos de estudo entre as disciplinas com base no fator de importância.
    Garante que toda disciplina receba pelo menos 1 bloco.
    """
    if not disciplinas:
        return {}
    
    fatores = calcular_fatores_importancia(disciplinas)
    soma_fatores = sum(fatores.values())
    if soma_fatores == 0:
        soma_fatores = len(disciplinas)
        fatores = {d.id: 1.0 for d in disciplinas}

    # Garantir no mínimo 1 bloco para cada disciplina
    alocacao = {d.id: 1 for d in disciplinas}
    blocos_restantes = max(0, total_blocos - len(disciplinas))

    if blocos_restantes > 0:
        fracoes = []
        for d in disciplinas:
            proporcao = fatores[d.id] / soma_fatores
            ideal = proporcao * blocos_restantes
            inteiro = int(ideal)
            alocacao[d.id] += inteiro
            fracoes.append((ideal - inteiro, d.id))
        
        # Distribuir os blocos que sobraram por maior resto (Método Hamilton/Largest Remainder)
        sobra = total_blocos - sum(alocacao.values())
        fracoes.sort(key=lambda x: x[0], reverse=True)
        for i in range(min(sobra, len(fracoes))):
            alocacao[fracoes[i][1]] += 1

    return alocacao

def intercalar_blocos_cognitivo(disciplinas: List[Disciplina], alocacao: Dict[int, int]) -> List[int]:
    """
    Intercala blocos de estudo alternando entre matérias de categorias distintas
    (Exatas/Lógica/TI vs Teórica/Direito) e evitando repetições consecutivas da mesma disciplina.
    """
    disciplina_map = {d.id: d for d in disciplinas}
    
    # Pool de blocos por disciplina
    pool_exatas = []
    pool_teoricas = []
    
    for disc_id, count in alocacao.items():
        disc = disciplina_map[disc_id]
        itens = [disc_id] * count
        if disc.categoria == "EXATAS_LOGICA":
            pool_exatas.extend(itens)
        else:
            pool_teoricas.extend(itens)
            
    # Se uma das pools estiver vazia, ordena por rodízio simples entre disciplinas
    if not pool_exatas or not pool_teoricas:
        return _intercalar_simples(alocacao)
        
    resultado = []
    # Alterna entre as listas garantindo intercalação cognitiva
    usar_exatas = len(pool_exatas) >= len(pool_teoricas)
    
    while pool_exatas or pool_teoricas:
        escolhido = None
        if usar_exatas and pool_exatas:
            # Pega uma disciplina diferente da última se possível
            escolhido = _selecionar_diferente(pool_exatas, resultado[-1] if resultado else None)
            if escolhido is not None:
                pool_exatas.remove(escolhido)
                resultado.append(escolhido)
        elif not usar_exatas and pool_teoricas:
            escolhido = _selecionar_diferente(pool_teoricas, resultado[-1] if resultado else None)
            if escolhido is not None:
                pool_teoricas.remove(escolhido)
                resultado.append(escolhido)
        elif pool_exatas:
            escolhido = _selecionar_diferente(pool_exatas, resultado[-1] if resultado else None)
            if escolhido is not None:
                pool_exatas.remove(escolhido)
                resultado.append(escolhido)
        elif pool_teoricas:
            escolhido = _selecionar_diferente(pool_teoricas, resultado[-1] if resultado else None)
            if escolhido is not None:
                pool_teoricas.remove(escolhido)
                resultado.append(escolhido)
                
        # Alterna para o próximo turno
        if pool_exatas and pool_teoricas:
            usar_exatas = not usar_exatas
        elif pool_exatas:
            usar_exatas = True
        else:
            usar_exatas = False
            
    return resultado

def _selecionar_diferente(pool: List[int], ultimo_id: int | None) -> int:
    if not pool:
        return None
    if ultimo_id is None:
        return pool[0]
    for item in pool:
        if item != ultimo_id:
            return item
    return pool[0]

def _intercalar_simples(alocacao: Dict[int, int]) -> List[int]:
    """Intercala em round-robin respeitando a contagem"""
    pool = {k: v for k, v in alocacao.items() if v > 0}
    resultado = []
    while pool:
        chaves = sorted(pool.keys(), key=lambda k: pool[k], reverse=True)
        for k in chaves:
            if pool[k] > 0:
                # Evita se igual ao último se houver alternativa
                resultado.append(k)
                pool[k] -= 1
                if pool[k] == 0:
                    del pool[k]
    return resultado

def gerar_ciclo_para_edital(
    db: Session,
    edital_id: int,
    nome_ciclo: str | None = None,
    carga_horaria_semanal: float = 20.0,
    duracao_bloco_minutos: int = 60
) -> CicloEstudos:
    """
    Gera o ciclo completo persistindo os blocos calculados e intercalados no banco de dados.
    """
    edital = db.query(Edital).filter(Edital.id == edital_id).first()
    if not edital:
        raise ValueError(f"Edital com ID {edital_id} não encontrado.")
    if not edital.disciplinas:
        raise ValueError("O edital não possui disciplinas cadastradas.")

    # Pega o numero do ultimo ciclo
    ultimo_numero = db.query(CicloEstudos).filter(CicloEstudos.edital_id == edital_id).count()
    novo_numero = ultimo_numero + 1
    
    cores = ['#10b981', '#3b82f6', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#14b8a6']
    cor = cores[(novo_numero - 1) % len(cores)]

    # Desativa ciclos anteriores do mesmo edital se houver
    db.query(CicloEstudos).filter(CicloEstudos.edital_id == edital_id).update({"ativo": False})

    # Filtra as disciplinas que devem ir para o ciclo
    disciplinas_ativas = [d for d in edital.disciplinas if d.incluir_no_ciclo and d.nome != "REVISÃO ANKI"]
    
    if not disciplinas_ativas:
        # Usuário não marcou nenhuma. Vamos rankear as top 8 automaticamente
        scored = []
        for disc in edital.disciplinas:
            p = disc.peso_prova or 1.0
            d = disc.relevancia_dificuldade or 3
            q = disc.qtd_questoes_prova or 0
            
            # peso e quantidade de questões têm mais importância que dificuldade
            # Fórmula: (Peso * 10) + (Questões * 2) + Dificuldade
            score = (p * 10.0) + (q * 2.0) + d
            scored.append((disc, score))
            
        scored.sort(key=lambda x: x[1], reverse=True)
        top_8 = [x[0] for x in scored[:8]]
        
        # Marca elas no banco e usa para o ciclo
        for disc in top_8:
            disc.incluir_no_ciclo = True
        db.commit()
        
        disciplinas_ativas = top_8

    # Calcula a quantidade total de blocos do ciclo
    minutos_totais = carga_horaria_semanal * 60
    total_blocos = max(len(disciplinas_ativas), int(round(minutos_totais / duracao_bloco_minutos)))

    # Distribui e Intercala
    alocacao = distribuir_blocos_disciplinas(disciplinas_ativas, total_blocos)
    ordem_disciplinas = intercalar_blocos_cognitivo(disciplinas_ativas, alocacao)

    # Cria o registro do ciclo
    nome = nome_ciclo or f"Ciclo {edital.nome} ({int(carga_horaria_semanal)}h/sem)"
    ciclo = CicloEstudos(
        edital_id=edital.id,
        nome=nome,
        carga_horaria_semanal=carga_horaria_semanal,
        duracao_bloco_minutos=duracao_bloco_minutos,
        bloco_atual_index=0,
        ativo=True,
        numero_ciclo=novo_numero,
        cor_hex=cor
    )
    db.add(ciclo)
    db.flush()

    # Cria 1 bloco por disciplina, com o tempo total daquela disciplina
    # Ordenar pela ordem da Trilha de Aprendizado IA (se definida) e depois por alocação Pareto
    disciplinas_ordenadas = sorted(
        disciplinas_ativas,
        key=lambda d: (
            d.ordem_trilha if getattr(d, "ordem_trilha", None) is not None else 999,
            -alocacao.get(d.id, 0),
            d.id
        )
    )
    
    # Criar ou buscar a disciplina especial "REVISÃO ANKI"
    revisao_disc = db.query(Disciplina).filter(Disciplina.edital_id == edital.id, Disciplina.nome == "REVISÃO ANKI").first()
    if not revisao_disc:
        revisao_disc = Disciplina(
            edital_id=edital.id,
            nome="REVISÃO ANKI",
            categoria="REVISAO_ANKI",
            grupo_conhecimento="BASICOS",
            peso_prova=1.0,
            incluir_no_ciclo=True
        )
        db.add(revisao_disc)
        db.flush()

    meio_index = len(disciplinas_ordenadas) // 2
    
    # Inserir REVISÃO ANKI no meio
    disciplinas_com_revisao = disciplinas_ordenadas[:meio_index] + [revisao_disc] + disciplinas_ordenadas[meio_index:]

    for idx, disc in enumerate(disciplinas_com_revisao):
        if disc.nome == "REVISÃO ANKI":
            tempo_total_disciplina = 30 # Default 30 minutos para revisão
        else:
            qtd_blocos = alocacao.get(disc.id, 0)
            if qtd_blocos == 0:
                qtd_blocos = 1 # Garantir pelo menos 1
            tempo_total_disciplina = qtd_blocos * duracao_bloco_minutos
            
        bloco = BlocoCiclo(
            ciclo_id=ciclo.id,
            disciplina_id=disc.id,
            ordem=idx,
            duracao_minutos=tempo_total_disciplina,
            concluido=False
        )
        db.add(bloco)

    db.commit()
    db.refresh(ciclo)
    return ciclo


def _obter_ou_criar_disciplina_anki(db: Session, edital_id: int) -> Disciplina:
    revisao_disc = (
        db.query(Disciplina)
        .filter(Disciplina.edital_id == edital_id, Disciplina.nome == "REVISÃO ANKI")
        .first()
    )
    if not revisao_disc:
        revisao_disc = Disciplina(
            edital_id=edital_id,
            nome="REVISÃO ANKI",
            categoria="REVISAO_ANKI",
            grupo_conhecimento="BASICOS",
            peso_prova=1.0,
            incluir_no_ciclo=True,
        )
        db.add(revisao_disc)
        db.flush()
    return revisao_disc


def aplicar_alternancia_volta_ciclo(db: Session, ciclo: CicloEstudos) -> bool:
    """
    Aplica as regras de alternância de 2 disciplinas conforme a paridade de `ciclo.voltas_completas`.
    Voltas pares (0, 2, 4...): usa `disc_a_id`.
    Voltas ímpares (1, 3, 5...): usa `disc_b_id`.
    """
    if not ciclo or not getattr(ciclo, "config_ciclo_json", None):
        return False
    try:
        cfg = json.loads(ciclo.config_ciclo_json)
    except Exception:
        return False

    alternancias = cfg.get("alternancias") or []
    if not alternancias:
        return False

    volta_impar = ((ciclo.voltas_completas or 0) % 2) == 1
    alterou = False
    for regra in alternancias:
        try:
            disc_a_id = int(regra.get("disc_a_id"))
            disc_b_id = int(regra.get("disc_b_id"))
        except (TypeError, ValueError):
            continue
        if not disc_a_id or not disc_b_id or disc_a_id == disc_b_id:
            continue

        alvo_id = disc_b_id if volta_impar else disc_a_id
        outro_id = disc_a_id if volta_impar else disc_b_id
        for bloco in ciclo.blocos:
            if bloco.disciplina_id == outro_id:
                bloco.disciplina_id = alvo_id
                alterou = True

    if alterou:
        db.flush()
    return alterou


def avancar_bloco_ciclo(
    db: Session,
    ciclo: CicloEstudos,
    marcar_atual_concluido: bool = True,
) -> Tuple[int, int]:
    """
    Avança a esteira do ciclo de forma inteligente:
    - Marca o bloco atual como concluído (se solicitado).
    - Pula blocos que já estejam com `concluido=True` nesta volta (evita repetir matéria já feita após reordenar).
    - Quando todos os blocos da volta estiverem concluídos, incrementa `voltas_completas`,
      reseta `concluido=False` para a nova volta, aplica alternâncias de volta e volta ao índice 0.
    """
    blocos_ord = sorted(list(ciclo.blocos), key=lambda b: b.ordem)
    total_blocos = len(blocos_ord)
    if total_blocos == 0:
        return (0, 0)

    antigo_index = max(0, min(ciclo.bloco_atual_index or 0, total_blocos - 1))
    if marcar_atual_concluido:
        blocos_ord[antigo_index].concluido = True

    # 1. Procura o próximo bloco pendente à frente na ordem da esteira
    novo_index: Optional[int] = None
    for idx in range(antigo_index + 1, total_blocos):
        if not blocos_ord[idx].concluido:
            novo_index = idx
            break

    # 2. Se não houver pendente à frente, verifica se restou algum pendente antes (caso de reordenação no meio da volta)
    if novo_index is None:
        for idx in range(0, antigo_index + 1):
            if not blocos_ord[idx].concluido:
                novo_index = idx
                break

    # 3. Se todos os blocos da volta estão concluídos, conclui a volta e inicia a próxima sequencialmente do 0
    if novo_index is None:
        ciclo.voltas_completas = (ciclo.voltas_completas or 0) + 1
        for b in blocos_ord:
            b.concluido = False
        aplicar_alternancia_volta_ciclo(db, ciclo)
        novo_index = 0

    ciclo.bloco_atual_index = novo_index
    db.flush()
    return (antigo_index, novo_index)


def configurar_ciclo_personalizado(
    db: Session,
    ciclo_id: int,
    itens: List[Dict[str, Any]],
    qtd_revisoes_anki: int = 1,
    duracao_revisao_anki: int = 30,
    alternancias: Optional[List[Dict[str, Any]]] = None,
) -> CicloEstudos:
    """
    Reorganiza a esteira do ciclo com ordem personalizada das disciplinas,
    quantidade de blocos de Revisão Anki distribuídos uniformemente e regras de alternância por volta.
    """
    ciclo = (
        db.query(CicloEstudos)
        .options(selectinload(CicloEstudos.blocos).joinedload(BlocoCiclo.disciplina))
        .filter(CicloEstudos.id == ciclo_id)
        .first()
    )
    if not ciclo:
        raise ValueError("Ciclo não encontrado.")

    disciplinas_edital = db.query(Disciplina).filter(Disciplina.edital_id == ciclo.edital_id).all()
    disc_map = {d.id: d for d in disciplinas_edital}

    regras_limpas: List[Dict[str, int]] = []
    usados_alt = set()
    for reg in (alternancias or []):
        try:
            a_id = int(reg.get("disc_a_id"))
            b_id = int(reg.get("disc_b_id"))
        except (TypeError, ValueError):
            continue
        if (
            a_id in disc_map
            and b_id in disc_map
            and a_id != b_id
            and disc_map[a_id].categoria != "REVISAO_ANKI"
            and disc_map[b_id].categoria != "REVISAO_ANKI"
            and a_id not in usados_alt
            and b_id not in usados_alt
        ):
            regras_limpas.append({"disc_a_id": a_id, "disc_b_id": b_id})
            usados_alt.add(a_id)
            usados_alt.add(b_id)

    volta_impar = ((ciclo.voltas_completas or 0) % 2) == 1
    alt_substituicao: Dict[int, int] = {}
    for reg in regras_limpas:
        ativo_id = reg["disc_b_id"] if volta_impar else reg["disc_a_id"]
        inativo_id = reg["disc_a_id"] if volta_impar else reg["disc_b_id"]
        alt_substituicao[inativo_id] = ativo_id
        alt_substituicao[ativo_id] = ativo_id

    regulares: List[Tuple[int, int]] = []
    alt_ja_incluido = set()
    for item in itens:
        try:
            d_id = int(item.get("disciplina_id"))
            dur = max(15, min(360, int(item.get("duracao_minutos") or 60)))
        except (TypeError, ValueError):
            continue
        disc = disc_map.get(d_id)
        if not disc or disc.categoria == "REVISAO_ANKI":
            continue
        if d_id in alt_substituicao:
            ativo_id = alt_substituicao[d_id]
            if ativo_id in alt_ja_incluido:
                continue
            alt_ja_incluido.add(ativo_id)
            regulares.append((ativo_id, dur))
        else:
            regulares.append((d_id, dur))

    if not regulares:
        raise ValueError("Selecione pelo menos uma disciplina para compor a esteira do ciclo.")

    qtd_anki = max(0, min(10, int(qtd_revisoes_anki)))
    dur_anki = max(10, min(180, int(duracao_revisao_anki or 30)))

    sequencia_final: List[Tuple[int, int]] = []
    if qtd_anki == 0:
        sequencia_final = list(regulares)
    else:
        revisao_disc = _obter_ou_criar_disciplina_anki(db, ciclo.edital_id)
        n = len(regulares)
        if qtd_anki == 1:
            meio = n // 2
            sequencia_final = regulares[:meio] + [(revisao_disc.id, dur_anki)] + regulares[meio:]
        else:
            pontos_insercao = set()
            for i in range(qtd_anki):
                pos = max(1, min(n, round((i + 1) * n / qtd_anki)))
                # Evita colisão quando qtd_anki <= n
                while pos in pontos_insercao and pos < n:
                    pos += 1
                pontos_insercao.add(pos)

            extras = max(0, qtd_anki - len(pontos_insercao))
            for idx, reg_item in enumerate(regulares, start=1):
                sequencia_final.append(reg_item)
                if idx in pontos_insercao:
                    sequencia_final.append((revisao_disc.id, dur_anki))
            for _ in range(extras):
                sequencia_final.append((revisao_disc.id, dur_anki))

    blocos_atuais = sorted(list(ciclo.blocos), key=lambda b: b.ordem)
    idx_atual_antigo = ciclo.bloco_atual_index or 0
    bloco_atual_antigo = (
        blocos_atuais[idx_atual_antigo]
        if 0 <= idx_atual_antigo < len(blocos_atuais)
        else None
    )

    # Mapeia parceiro de alternância para reaproveitar o bloco existente sem quebrar sessões nem progresso
    parceiro_alt: Dict[int, int] = {}
    for reg in regras_limpas:
        parceiro_alt[reg["disc_a_id"]] = reg["disc_b_id"]
        parceiro_alt[reg["disc_b_id"]] = reg["disc_a_id"]

    # Pool de blocos existentes por disciplina_id (preserva IDs, status concluido e vínculos de SessaoEstudo)
    pools_existentes: Dict[int, List[BlocoCiclo]] = {}
    for b in blocos_atuais:
        pools_existentes.setdefault(b.disciplina_id, []).append(b)

    blocos_finais: List[BlocoCiclo] = []
    ids_reutilizados = set()
    for ordem, (d_id, dur) in enumerate(sequencia_final):
        reutilizado: Optional[BlocoCiclo] = None
        if pools_existentes.get(d_id):
            reutilizado = pools_existentes[d_id].pop(0)
        elif d_id in parceiro_alt and pools_existentes.get(parceiro_alt[d_id]):
            reutilizado = pools_existentes[parceiro_alt[d_id]].pop(0)

        if reutilizado is not None:
            reutilizado.disciplina_id = d_id
            reutilizado.ordem = ordem
            reutilizado.duracao_minutos = dur
            blocos_finais.append(reutilizado)
            ids_reutilizados.add(reutilizado.id)
        else:
            novo_bloco = BlocoCiclo(
                ciclo_id=ciclo.id,
                disciplina_id=d_id,
                ordem=ordem,
                duracao_minutos=dur,
                concluido=False,
            )
            db.add(novo_bloco)
            blocos_finais.append(novo_bloco)

    # Remove apenas blocos que realmente deixaram de existir, preservando 100% do histórico de SessaoEstudo
    blocos_obsoletos = [b for b in blocos_atuais if b.id not in ids_reutilizados]
    if blocos_obsoletos:
        obsoletos_ids = [b.id for b in blocos_obsoletos]
        db.query(SessaoEstudo).filter(SessaoEstudo.bloco_ciclo_id.in_(obsoletos_ids)).update(
            {"bloco_ciclo_id": None}, synchronize_session=False
        )
        for b_obs in blocos_obsoletos:
            db.delete(b_obs)
        db.flush()

    # Define o bloco atual como o primeiro bloco ainda não concluído na nova ordem,
    # garantindo que disciplinas colocadas no início sem conclusão não sejam puladas/burladas.
    primeiro_pendente = next((i for i, b in enumerate(blocos_finais) if not b.concluido), None)
    if primeiro_pendente is not None:
        ciclo.bloco_atual_index = primeiro_pendente
    else:
        ciclo.bloco_atual_index = 0

    ciclo.carga_horaria_semanal = round(sum(dur for _, dur in sequencia_final) / 60.0, 1)
    ciclo.config_ciclo_json = json.dumps(
        {
            "qtd_revisoes_anki": qtd_anki,
            "duracao_revisao_anki": dur_anki,
            "alternancias": regras_limpas,
        },
        ensure_ascii=False,
    )

    # Sincroniza incluir_no_ciclo nas disciplinas da preparação
    ids_no_ciclo = {d_id for d_id, _ in regulares}
    for reg in regras_limpas:
        ids_no_ciclo.add(reg["disc_a_id"])
        ids_no_ciclo.add(reg["disc_b_id"])
    for d in disciplinas_edital:
        if d.categoria != "REVISAO_ANKI" and d.nome != "REVISÃO ANKI":
            d.incluir_no_ciclo = d.id in ids_no_ciclo

    db.commit()
    db.refresh(ciclo)
    return ciclo
