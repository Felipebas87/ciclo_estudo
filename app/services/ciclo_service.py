import math
from typing import List, Dict, Tuple
from sqlalchemy.orm import Session
from app.models.edital import Edital
from app.models.disciplina import Disciplina
from app.models.ciclo import CicloEstudos, BlocoCiclo

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
    disciplinas_ativas = [d for d in edital.disciplinas if d.incluir_no_ciclo]
    
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
    # Ordenar por relevância (maior alocação primeiro)
    disciplinas_ordenadas = sorted(disciplinas_ativas, key=lambda d: alocacao.get(d.id, 0), reverse=True)
    
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
