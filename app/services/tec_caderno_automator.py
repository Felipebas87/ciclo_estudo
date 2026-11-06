import os
import re
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
from sqlalchemy.orm import Session
try:
    from playwright.sync_api import sync_playwright, BrowserContext, Page, TimeoutError as PlaywrightTimeoutError
    PLAYWRIGHT_DISPONIVEL = True
except ImportError:
    PLAYWRIGHT_DISPONIVEL = False
    sync_playwright = None
    BrowserContext = None
    Page = None
    PlaywrightTimeoutError = Exception

from app.database import SessionLocal
from app.models.topico import Topico
from app.models.configuracao_prova import ConfiguracaoPainelProva
from app.models.tec_taxonomia import TecTaxonomia, TopicoEstudoTecDePara
from app.services.tec_scraper_service import TEC_BASE_URL
from app.services.tec_bancas_catalog import resolver_banca_tec
from app.services.tec_matching_service import montar_dados_vinculo_topico

SESSION_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "tec_session.json"
SCRATCH_DIR = Path(__file__).resolve().parent.parent.parent / "scratch"


def _utcnow():
    return datetime.now(timezone.utc)


def extrair_id_caderno(url_ou_id: str) -> Optional[str]:
    """Extrai apenas os dígitos do ID do caderno a partir de uma URL ou string numérica."""
    if not url_ou_id:
        return None
    s = str(url_ou_id).strip()
    match = re.search(r"/cadernos/(\d+)", s)
    if match:
        return match.group(1)
    match_digits = re.search(r"^\d+$", s)
    if match_digits:
        return match_digits.group(0)
    match_any = re.search(r"(\d{6,})", s)
    if match_any:
        return match_any.group(1)
    return None


def obter_status_sessao_tec() -> Dict[str, Any]:
    """Verifica se existe um arquivo de sessão/cookies salvo para o TEC Concursos."""
    if not SESSION_FILE.exists():
        return {
            "autenticado": False,
            "arquivo_sessao": False,
            "mensagem": "Nenhuma sessão salva no TEC Concursos. Faça login interativo ou informe suas credenciais."
        }

    try:
        with open(SESSION_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        cookies = data.get("cookies", [])
        tem_cookies = len(cookies) > 0
        return {
            "autenticado": tem_cookies,
            "arquivo_sessao": True,
            "total_cookies": len(cookies),
            "mensagem": "Sessão salva disponível." if tem_cookies else "Arquivo de sessão vazio."
        }
    except Exception as e:
        return {
            "autenticado": False,
            "arquivo_sessao": False,
            "erro": str(e),
            "mensagem": f"Erro ao ler sessão: {e}"
        }


def iniciar_login_interativo_tec(timeout_segundos: int = 150) -> Dict[str, Any]:
    """
    Abre uma janela de navegador (headed) do Playwright na página de login do TEC Concursos.
    O usuário faz login normalmente (com e-mail/senha ou Google).
    Assim que o usuário estiver comprovadamente logado no site, captura e salva a sessão em data/tec_session.json.
    """
    if not PLAYWRIGHT_DISPONIVEL:
        return {
            "sucesso": False,
            "mensagem": "Automação via navegador desativada neste ambiente. Utilize a inclusão manual de links de caderno."
        }
    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context_args = {}
        if SESSION_FILE.exists():
            try:
                context_args["storage_state"] = str(SESSION_FILE)
            except Exception:
                pass

        context = browser.new_context(**context_args)
        page = context.new_page()

        try:
            page.goto(f"{TEC_BASE_URL}/login")
            inicio = time.time()
            logado = False

            while time.time() - inicio < timeout_segundos:
                current_url = page.url
                # Verifica se há elementos que só aparecem para usuários logados
                tem_elemento_logado = False
                try:
                    tem_elemento_logado = page.locator(
                        "a:has-text('Sair'), a:has-text('sair'), a[href*='logout'], a[href*='sair'], .usuario-logado, #icone-usuario-header, span:has-text('Seja bem-vindo')"
                    ).count() > 0
                except Exception:
                    pass

                # Se saiu do /login e tem elemento de usuário logado
                if tem_elemento_logado or ("/login" not in current_url and any(sub in current_url for sub in ["/estudo", "/questoes", "/cadernos", "/materias", "/dashboard"])):
                    page.wait_for_timeout(2500)
                    logado = True
                    break

                page.wait_for_timeout(1000)

            if logado:
                context.storage_state(path=str(SESSION_FILE))
                browser.close()
                return {
                    "sucesso": True,
                    "mensagem": "Autenticação realizada e sessão salva com sucesso no TEC Concursos!"
                }
            else:
                browser.close()
                return {
                    "sucesso": False,
                    "mensagem": f"Tempo limite de {timeout_segundos} segundos esgotado para login no TEC Concursos."
                }
        except Exception as e:
            try:
                browser.close()
            except Exception:
                pass
            return {
                "sucesso": False,
                "erro": str(e),
                "mensagem": f"Erro durante login interativo: {e}"
            }


def autenticar_por_credenciais_tec(email: str, senha: str) -> Dict[str, Any]:
    """
    Realiza login headless com as credenciais informadas e salva a sessão em data/tec_session.json.
    """
    if not PLAYWRIGHT_DISPONIVEL:
        return {
            "sucesso": False,
            "mensagem": "Automação via navegador desativada neste ambiente. Utilize a inclusão manual de links de caderno."
        }
    if not email or not senha:
        return {"sucesso": False, "mensagem": "E-mail e senha são obrigatórios."}

    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        try:
            page.goto(f"{TEC_BASE_URL}/login", timeout=30000)
            page.fill("input[name='email'], input#email, input[type='email']", email)
            page.fill("input[name='senha'], input#senha, input[type='password']", senha)
            page.click("button#entrar-site, button[type='submit'], input[type='submit']")

            page.wait_for_timeout(3500)
            if "/login" not in page.url and "tecconcursos.com.br" in page.url:
                context.storage_state(path=str(SESSION_FILE))
                browser.close()
                return {
                    "sucesso": True,
                    "mensagem": "Login realizado com sucesso e sessão persistida!"
                }
            else:
                browser.close()
                return {
                    "sucesso": False,
                    "mensagem": "Não foi possível validar o login. Verifique as credenciais ou utilize a janela interativa."
                }
        except Exception as e:
            try:
                browser.close()
            except Exception:
                pass
            return {
                "sucesso": False,
                "erro": str(e),
                "mensagem": f"Erro ao tentar login automatizado: {e}"
            }


def associar_caderno_manualmente(
    topico_id: int,
    caderno_url_ou_id: str,
    pasta_nome: Optional[str] = None,
    db: Optional[Session] = None
) -> Dict[str, Any]:
    """
    Associa manualmente uma URL ou ID de caderno real já criado no TEC Concursos a um tópico.
    """
    caderno_id = extrair_id_caderno(caderno_url_ou_id)
    if not caderno_id:
        raise ValueError(f"Não foi possível extrair o ID do caderno a partir de: {caderno_url_ou_id}")

    url_caderno = f"{TEC_BASE_URL}/questoes/cadernos/{caderno_id}"

    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        topico = db.query(Topico).filter(Topico.id == topico_id).first()
        if not topico:
            raise ValueError(f"Tópico com ID {topico_id} não encontrado.")

        if not pasta_nome:
            cfg = db.query(ConfiguracaoPainelProva).first()
            pasta_nome = cfg.tec_pasta_padrao if cfg and cfg.tec_pasta_padrao else "Sefaz Alagoas Auditor TI"

        vinculo = db.query(TopicoEstudoTecDePara).filter(TopicoEstudoTecDePara.topico_id == topico_id).first()
        now = _utcnow()

        if not vinculo:
            tec_raiz = db.query(TecTaxonomia).first()
            tec_tax_id = tec_raiz.id if tec_raiz else 1
            vinculo = TopicoEstudoTecDePara(
                topico_id=topico_id,
                tec_taxonomia_id=tec_tax_id,
                tipo_vinculo="MANUAL",
                confianca_score=1.0,
                validado=True,
                caderno_id=caderno_id,
                url_caderno_criado=url_caderno,
                pasta_tec_nome=pasta_nome,
                data_geracao_caderno=now,
                updated_at=now,
            )
            db.add(vinculo)
        else:
            vinculo.caderno_id = caderno_id
            vinculo.url_caderno_criado = url_caderno
            vinculo.pasta_tec_nome = pasta_nome
            vinculo.data_geracao_caderno = now
            vinculo.updated_at = now

        db.commit()
        db.refresh(vinculo)

        dados_montados = montar_dados_vinculo_topico(topico, vinculo)
        return {
            "sucesso": True,
            "topico_id": topico_id,
            "caderno_id": caderno_id,
            "url_caderno_criado": url_caderno,
            "pasta_tec_nome": pasta_nome,
            "vinculo": dados_montados,
            "mensagem": f"Caderno #{caderno_id} associado com sucesso ao tópico!"
        }
    finally:
        if close_db:
            db.close()


def _selecionar_ou_criar_pasta_no_tec(page: Page, nome_pasta: str):
    """
    Verifica se a pasta de destino existe na lista de pastas e a seleciona.
    Se não encontrar a pasta exata, tenta encontrar por aproximação (ex: 'sefaz', 'alagoas').
    Caso não exista, mantém a pasta padrão/selecionada sem travar a execução.
    """
    try:
        select_pasta = page.locator("select[name='pasta_id'], select#pasta_id, select.select-pastas, select").first
        if select_pasta.count() > 0:
            options = select_pasta.locator("option").all_inner_texts()
            # 1. Match exato ou substring
            for opt in options:
                if nome_pasta.lower() in opt.lower() or opt.lower() in nome_pasta.lower():
                    select_pasta.select_option(label=opt.strip())
                    return True
            # 2. Match parcial ('sefaz' ou 'alagoas')
            for opt in options:
                if any(w in opt.lower() for w in ["sefaz", "alagoas"]):
                    select_pasta.select_option(label=opt.strip())
                    return True
    except Exception as e:
        print(f"[TEC AUTOMATOR] Aviso ao gerenciar pasta '{nome_pasta}': {e}")
    return False


def _descartar_banner_cookies(page: Page):
    """Descarta o banner de cookies/LGPD que cobre o rodapé da página."""
    try:
        page.evaluate("if (typeof tecCookieAceitar === 'function') { tecCookieAceitar(true, true); }")
    except Exception:
        pass
    try:
        for btn_sel in [
            "button:has-text('Aceitar todos')",
            "button:has-text('Somente essenciais')",
            "button:has-text('Aceitar')",
            "#tec-cookie-aceitar"
        ]:
            cookie_btn = page.locator(btn_sel).first
            if cookie_btn.count() > 0 and cookie_btn.is_visible():
                cookie_btn.click(force=True)
                page.wait_for_timeout(500)
                break
    except Exception:
        pass


def _aplicar_filtros_na_tela_tec(page: Page, nome_assunto: str, nome_banca: str):
    """
    Interage diretamente com a interface do filtro do TEC Concursos:
    1. Pesquisa o nome do assunto e marca o checkbox correspondente.
    2. Clica na aba 'Banca', pesquisa e marca o checkbox da banca (ex: Cebraspe).
    """
    try:
        # 1. Ativa 'Pesquisar por nome' se disponível
        btn_pesquisar_nome = page.locator(
            "a:has-text('Pesquisar por nome'), button:has-text('Pesquisar por nome'), span:has-text('Pesquisar por nome')"
        ).first
        if btn_pesquisar_nome.count() > 0 and btn_pesquisar_nome.is_visible():
            btn_pesquisar_nome.click()
            page.wait_for_timeout(800)

        # 2. Preenche termo de busca de assunto
        termo_limpo = re.sub(r"^(?:\d+[\.\-\s]+)+", "", nome_assunto).strip()
        palavras = [p for p in re.split(r"[,:;()\-/]", termo_limpo)[0].split() if len(p) > 2]
        termo_curto = " ".join(palavras[:3]) if palavras else termo_limpo[:25]

        input_busca = page.locator("input[placeholder*='Pesquisar'], input[type='search'], input.campo-pesquisa").first
        if input_busca.count() > 0:
            input_busca.fill(termo_curto)
            page.wait_for_timeout(1500)
            # Marca o checkbox do primeiro resultado encontrado
            chk_assunto = page.locator("input[type='checkbox']").first
            if chk_assunto.count() > 0 and not chk_assunto.is_checked():
                chk_assunto.check()
                page.wait_for_timeout(800)
    except Exception as e:
        print(f"[TEC AUTOMATOR] Aviso ao aplicar filtro de assunto: {e}")

    try:
        # 3. Clica na aba 'Banca' no menu lateral esquerdo
        tab_banca = page.locator("text='Banca'").first
        if tab_banca.count() > 0 and tab_banca.is_visible():
            tab_banca.click()
            page.wait_for_timeout(800)

            # Busca pela banca
            banca_busca = "Cebraspe" if "cebraspe" in nome_banca.lower() or "cespe" in nome_banca.lower() else nome_banca
            input_banca = page.locator("input[placeholder*='Pesquisar'], input[type='search']").first
            if input_banca.count() > 0:
                input_banca.fill(banca_busca)
                page.wait_for_timeout(1500)
                chks = page.locator("input[type='checkbox']").all()
                for c in chks[:3]:
                    if not c.is_checked():
                        c.check()
                        page.wait_for_timeout(600)
                        break
    except Exception as e:
        print(f"[TEC AUTOMATOR] Aviso ao aplicar filtro de banca: {e}")


def gerar_caderno_topico_playwright(
    topico_id: int,
    nome_pasta: Optional[str] = None,
    db: Optional[Session] = None,
    headless: bool = False
) -> Dict[str, Any]:
    """
    Abre o TEC Concursos (em modo visível para transparência total ao usuário),
    navega até a criação do caderno, preenche nome e pasta, submete e aguarda
    o redirecionamento para capturar o ID do caderno gerado (ex: 107798461).
    """
    if not PLAYWRIGHT_DISPONIVEL:
        return {
            "sucesso": False,
            "mensagem": "Criação automática de cadernos via robô está desativada. Cole o link ou ID do caderno diretamente para associá-lo ao tópico."
        }
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        topico = db.query(Topico).filter(Topico.id == topico_id).first()
        if not topico:
            raise ValueError(f"Tópico com ID {topico_id} não encontrado.")

        vinculo = db.query(TopicoEstudoTecDePara).filter(TopicoEstudoTecDePara.topico_id == topico_id).first()
        if not vinculo or not vinculo.tec_taxonomia:
            raise ValueError(f"Tópico {topico_id} não possui vínculo de taxonomia TEC.")

        if vinculo.caderno_id and vinculo.url_caderno_criado:
            return {
                "sucesso": True,
                "topico_id": topico_id,
                "caderno_id": vinculo.caderno_id,
                "url_caderno_criado": vinculo.url_caderno_criado,
                "pasta_tec_nome": vinculo.pasta_tec_nome,
                "reutilizado": True,
                "mensagem": f"Caderno #{vinculo.caderno_id} já existia no banco de dados."
            }

        cfg = db.query(ConfiguracaoPainelProva).first()
        pasta_alvo = nome_pasta or (cfg.tec_pasta_padrao if cfg and cfg.tec_pasta_padrao else "Sefaz Alagoas Auditor TI")
        banca_nome = cfg.banca if cfg and cfg.banca else "Cebraspe"
        banca_info = resolver_banca_tec(banca_nome)
        banca_tec_id = banca_info["id"] if banca_info else 4

        no = vinculo.tec_taxonomia
        param_filtro = f"materia_ids[]={no.tec_id}" if no.is_materia else f"assunto_ids[]={no.tec_id}"
        url_filtro = f"{TEC_BASE_URL}/questoes/cadernos/novo/?{param_filtro}&banca_ids[]={banca_tec_id}"

        if not SESSION_FILE.exists():
            return {
                "sucesso": False,
                "precisa_autenticar": True,
                "mensagem": "Nenhuma sessão ativa encontrada. Clique em 'Conectar Conta TEC' para autenticar uma vez."
            }

        SCRATCH_DIR.mkdir(parents=True, exist_ok=True)

        with sync_playwright() as p:
            # Headed para que o usuário veja a criação e possa interagir se houver qualquer alerta
            browser = p.chromium.launch(headless=headless)
            context = browser.new_context(storage_state=str(SESSION_FILE))
            page = context.new_page()

            # Aceita automaticamente diálogos do navegador
            page.on("dialog", lambda dialog: dialog.accept())

            try:
                page.goto(url_filtro, timeout=40000)
                page.wait_for_timeout(2500)

                # Se foi redirecionado para login, a sessão precisa ser renovada
                if "/login" in page.url:
                    browser.close()
                    return {
                        "sucesso": False,
                        "precisa_autenticar": True,
                        "mensagem": "Sessão expirada no TEC Concursos. Por favor, clique em 'Conectar Conta TEC' para renovar o acesso."
                    }

                # 1. Descarta o banner LGPD para liberar a tela e os botões
                _descartar_banner_cookies(page)

                # 2. Aplica os filtros na tela do TEC (Assunto e Banca)
                _aplicar_filtros_na_tela_tec(page, no.nome or topico.titulo, banca_nome)

                # 3. Garante que o banner de cookies não reapareceu
                _descartar_banner_cookies(page)

                # 4. Seleciona a pasta de destino
                _selecionar_ou_criar_pasta_no_tec(page, pasta_alvo)

                # 5. Preenche nome do caderno
                nome_caderno_tec = f"[Sefaz AL] {topico.titulo[:45]}"
                input_nome = page.locator("input[name='nome'], input#nome, input[placeholder*='Nome do caderno'], input.campo-nome-caderno").first
                if input_nome.count() > 0:
                    input_nome.fill(nome_caderno_tec)

                page.wait_for_timeout(1000)

                # 6. Clica em Gerar Caderno
                btn_gerar = page.locator("button:has-text('GERAR CADERNO'), input[value*='GERAR CADERNO'], .btn-gerar-caderno").first
                if btn_gerar.count() > 0:
                    btn_gerar.click()

                # Aguarda redirecionamento para o caderno gerado: URL com /cadernos/{id_numerico} (diferente de /novo)
                # Timeout generoso de 90 segundos para permitir cálculo de questões no TEC
                def is_caderno_criado_url(url_atual: str) -> bool:
                    return bool(
                        "/questoes/cadernos/" in url_atual
                        and "/novo" not in url_atual
                        and re.search(r"/cadernos/\d+", url_atual)
                    )

                page.wait_for_url(is_caderno_criado_url, timeout=90000)
                url_final = page.url
                caderno_id = extrair_id_caderno(url_final)

                if not caderno_id:
                    screenshot_err = SCRATCH_DIR / "erro_caderno_sem_id.png"
                    page.screenshot(path=str(screenshot_err))
                    browser.close()
                    return {
                        "sucesso": False,
                        "mensagem": f"Caderno gerado mas não foi possível capturar o ID numérico da URL: {url_final}"
                    }

                url_caderno_criado = f"{TEC_BASE_URL}/questoes/cadernos/{caderno_id}"
                now = _utcnow()
                vinculo.caderno_id = caderno_id
                vinculo.url_caderno_criado = url_caderno_criado
                vinculo.pasta_tec_nome = pasta_alvo
                vinculo.data_geracao_caderno = now
                vinculo.updated_at = now

                # Atualiza também o arquivo de sessão com os cookies mais recentes
                try:
                    context.storage_state(path=str(SESSION_FILE))
                except Exception:
                    pass

                db.commit()
                db.refresh(vinculo)
                browser.close()

                dados_montados = montar_dados_vinculo_topico(topico, vinculo)
                return {
                    "sucesso": True,
                    "topico_id": topico_id,
                    "caderno_id": caderno_id,
                    "url_caderno_criado": url_caderno_criado,
                    "pasta_tec_nome": pasta_alvo,
                    "reutilizado": False,
                    "vinculo": dados_montados,
                    "mensagem": f"Caderno #{caderno_id} criado com sucesso no TEC Concursos na pasta '{pasta_alvo}'!"
                }
            except PlaywrightTimeoutError:
                screenshot_timeout = SCRATCH_DIR / "erro_timeout_caderno.png"
                try:
                    page.screenshot(path=str(screenshot_timeout))
                except Exception:
                    pass
                browser.close()
                return {
                    "sucesso": False,
                    "mensagem": (
                        "Tempo limite esgotado aguardando geração do caderno no TEC Concursos. "
                        "Se o navegador abriu a tela de filtros, basta clicar em 'GERAR CADERNO' "
                        "e colar o ID ou link gerado no campo 'Cole o ID ou link do caderno'."
                    )
                }
            except Exception as e:
                try:
                    browser.close()
                except Exception:
                    pass
                return {
                    "sucesso": False,
                    "erro": str(e),
                    "mensagem": f"Erro durante a geração automática: {e}"
                }
    finally:
        if close_db:
            db.close()
