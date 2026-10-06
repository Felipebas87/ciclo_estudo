import io
from typing import Tuple, List, Dict
import pandas as pd
from sqlalchemy.orm import Session
from app.models.edital import Edital
from app.models.disciplina import Disciplina
from app.models.topico import Topico
import re

def _normalizar_nome_coluna(col: str) -> str:
    c = str(col).strip().lower()
    c = c.replace("á", "a").replace("ã", "a").replace("â", "a")
    c = c.replace("é", "e").replace("ê", "e")
    c = c.replace("í", "i").replace("ó", "o").replace("ô", "o").replace("õ", "o")
    c = c.replace("ú", "u").replace("ç", "c")
    return c

def processar_arquivo_edital(
    db: Session,
    conteudo_bytes: bytes,
    nome_arquivo: str,
    nome_edital: str,
    orgao: str | None = None,
    cargo: str | None = None
) -> Tuple[Edital, int, int]:
    """
    Processa um arquivo CSV ou Excel contendo a estrutura verticalizada do edital.
    Retorna (edital, total_disciplinas, total_topicos).
    """
    ext = nome_arquivo.split(".")[-1].lower()
    
    if ext in ["xlsx", "xls"]:
        df = pd.read_excel(io.BytesIO(conteudo_bytes))
    else:
        # Tenta ler CSV com delimitador automático ou vírgula/ponto-e-vírgula
        try:
            df = pd.read_csv(io.BytesIO(conteudo_bytes), sep=None, engine="python", encoding="utf-8")
        except Exception:
            df = pd.read_csv(io.BytesIO(conteudo_bytes), sep=";", encoding="latin1")

    # Mapear colunas
    col_map = {}
    for col in df.columns:
        norm = _normalizar_nome_coluna(col)
        if "disciplina" in norm or "materia" in norm:
            col_map["disciplina"] = col
        elif "topico" in norm or "assunto" in norm or "conteudo" in norm:
            col_map["topico"] = col
        elif "categoria" in norm or "tipo" in norm:
            col_map["categoria"] = col
        elif "peso" in norm:
            col_map["peso"] = col
        elif "dificuldade" in norm or "relevancia" in norm:
            col_map["dificuldade"] = col

    if "disciplina" not in col_map:
        raise ValueError("A planilha precisa conter pelo menos uma coluna identificando a 'Disciplina' ou 'Matéria'.")

    # Cria o Edital
    edital = Edital(
        nome=nome_edital,
        orgao=orgao,
        cargo=cargo,
        ativo=True
    )
    db.add(edital)
    db.flush()

    disciplinas_cadastradas: Dict[str, Disciplina] = {}
    total_topicos = 0

    for _, row in df.iterrows():
        disc_nome = str(row[col_map["disciplina"]]).strip()
        if not disc_nome or disc_nome.lower() == "nan":
            continue

        if disc_nome not in disciplinas_cadastradas:
            # Extrair categoria
            cat_raw = str(row.get(col_map.get("categoria", ""), "")).upper()
            if any(term in cat_raw for term in ["EXATA", "TI", "LOGICA", "MATEMATICA", "ESTATISTICA", "INFORMATICA"]):
                categoria = "EXATAS_LOGICA"
            else:
                categoria = "TEORICA_DIREITO"

            # Extrair peso
            try:
                peso = float(str(row.get(col_map.get("peso", ""), 1.0)).replace(",", "."))
                if pd.isna(peso) or peso <= 0:
                    peso = 1.0
            except Exception:
                peso = 1.0

            # Extrair dificuldade
            try:
                dif = int(float(str(row.get(col_map.get("dificuldade", ""), 3)).replace(",", ".")))
                dif = max(1, min(5, dif))
            except Exception:
                dif = 3

            disciplina = Disciplina(
                edital_id=edital.id,
                nome=disc_nome,
                categoria=categoria,
                peso_prova=peso,
                relevancia_dificuldade=dif
            )
            db.add(disciplina)
            db.flush()
            disciplinas_cadastradas[disc_nome] = disciplina

        # Cadastrar tópico se presente
        if "topico" in col_map:
            topico_titulo = str(row.get(col_map["topico"], "")).strip()
            if topico_titulo and topico_titulo.lower() != "nan":
                topico = Topico(
                    disciplina_id=disciplinas_cadastradas[disc_nome].id,
                    titulo=topico_titulo,
                    ordem=len(disciplinas_cadastradas[disc_nome].topicos)
                )
                db.add(topico)
                total_topicos += 1

    db.commit()
    db.refresh(edital)
    return edital, len(disciplinas_cadastradas), total_topicos

def _criar_disciplina(nome, edital_id, grupo_conhecimento, db):
    cat_raw = nome.upper()
    if any(term in cat_raw for term in ["EXATA", "TI", "LOGICA", "MATEMATICA", "ESTATISTICA", "INFORMATICA", "RACIOCÍNIO"]):
        categoria = "EXATAS_LOGICA"
    else:
        categoria = "TEORICA_DIREITO"
    disc = Disciplina(
        edital_id=edital_id,
        nome=nome.upper()[:150],
        categoria=categoria,
        grupo_conhecimento=grupo_conhecimento,
        peso_prova=2.0 if grupo_conhecimento == "ESPECIFICOS" else 1.0,
        relevancia_dificuldade=3
    )
    db.add(disc)
    db.flush()
    return disc

def _extrair_disciplinas_topicos(texto: str, edital_id: int, grupo_conhecimento: str, db: Session) -> Tuple[int, int]:
    qtd_disciplinas = 0
    qtd_topicos = 0
    linhas = [ln.strip() for ln in texto.split('\n') if ln.strip()]
    
    regex_is_topic = re.compile(r'^(\d+(?:\.\d+)*)[\s\.\-\)]+(.*)')
    
    current_disciplina = None
    current_topico = None

    for linha in linhas:
        # Se tem dois pontos, tenta quebrar na mesma linha
        if not regex_is_topic.match(linha) and (": " in linha or " - 1" in linha):
            partes = re.split(r':\s+|\s+-\s+', linha, maxsplit=1)
            nome_disc = partes[0].strip()
            texto_topicos = partes[1].strip() if len(partes) > 1 else ""
            
            current_disciplina = _criar_disciplina(nome_disc, edital_id, grupo_conhecimento, db)
            qtd_disciplinas += 1
            
            matches = re.compile(r'(\d+(?:\.\d+)*\s+.*?)(?=\s+\d+(?:\.\d+)*\s+|$)').findall(texto_topicos)
            for m in matches:
                t_titulo = m.strip().rstrip('.;')
                current_topico = Topico(disciplina_id=current_disciplina.id, titulo=t_titulo, ordem=qtd_topicos)
                db.add(current_topico)
                qtd_topicos += 1
            continue

        match = regex_is_topic.match(linha)
        if match:
            # É um tópico!
            if not current_disciplina:
                current_disciplina = _criar_disciplina("Conhecimentos Gerais", edital_id, grupo_conhecimento, db)
                qtd_disciplinas += 1
                
            t_titulo = match.group(0).strip().rstrip('.;')
            current_topico = Topico(disciplina_id=current_disciplina.id, titulo=t_titulo, ordem=qtd_topicos)
            db.add(current_topico)
            qtd_topicos += 1
        else:
            # Não começa com número. É continuação ou nova disciplina?
            if linha.isupper() or not current_topico:
                # Se for tudo maiúsculo, ou não tivermos nenhum tópico ainda, é disciplina.
                current_disciplina = _criar_disciplina(linha, edital_id, grupo_conhecimento, db)
                current_topico = None
                qtd_disciplinas += 1
            else:
                # Se começa com minúscula, ou a linha anterior não terminou com ponto
                if linha[0].islower() or not current_topico.titulo.endswith('.'):
                    current_topico.titulo += " " + linha.rstrip('.;')
                else:
                    # É uma nova disciplina
                    current_disciplina = _criar_disciplina(linha, edital_id, grupo_conhecimento, db)
                    current_topico = None
                    qtd_disciplinas += 1

    return qtd_disciplinas, qtd_topicos

def processar_texto_puro_edital(
    db: Session,
    nome_edital: str,
    texto_basicos: str,
    texto_especificos: str
) -> Tuple[Edital, int, int]:
    
    edital = Edital(
        nome=nome_edital,
        ativo=True
    )
    db.add(edital)
    db.flush()

    d1, t1 = _extrair_disciplinas_topicos(texto_basicos, edital.id, "BASICOS", db)
    d2, t2 = _extrair_disciplinas_topicos(texto_especificos, edital.id, "ESPECIFICOS", db)

    db.commit()
    db.refresh(edital)

    return edital, d1 + d2, t1 + t2
