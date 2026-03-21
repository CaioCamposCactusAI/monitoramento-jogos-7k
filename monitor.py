"""
Robô de Monitoramento de Jogos - 7K Bet
Realiza scraping para verificar se os jogos estão operacionais,
capturando screenshots dos iframes dos jogos.
"""

import json
import os
import sys
import asyncio
import logging
import random
import subprocess
import urllib.request
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright, Page, BrowserContext, TimeoutError as PlaywrightTimeout
from supabase_client import send_results

# ─── Configuração de logging ───────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("monitor-7k")

# ─── Constantes ────────────────────────────────────────────────────────────────
BASE_URL = "https://7k.bet.br/"
LOGIN_URL = "https://7k.bet.br/login"
TENANT_URL = "7k.bet.br"
CLOUDFLARE_BYPASS = "TffkXflOjcnDj391"
INPUT_FILE = "input2.json"
BRAND = "7k"
GAMES_BASE_URL = "https://7k.bet.br/games/"
ENV_FILE = ".env"
EVIDENCE_DIR = "game_evidence"
PROFILE_DIR = "chrome_cdp_profile"
CDP_PORT = 9222
CONCURRENT_TABS = 3
GAME_LOAD_TIMEOUT = 15_000  # 15 segundos em ms
LOGIN_TIMEOUT = 10_000
CF_MAX_WAIT = 30  # segundos máximos para aguardar challenge do Cloudflare

# ─── Detecção de ambiente ──────────────────────────────────────────────────────
# environment: "staging" = Windows | "prod" = Ubuntu
ENVIRONMENT = os.environ.get("environment", "prod").lower()
IS_PROD = ENVIRONMENT == "prod"

if IS_PROD:
    # Em prod (Ubuntu/ARM64), usar Chromium bundled do Playwright
    # Instalar via: python -m playwright install chromium
    import glob as _glob
    _pw_candidates = sorted(
        _glob.glob(os.path.expanduser("~/.cache/ms-playwright/chromium-*/chrome-linux/chrome")),
        reverse=True,
    )
    if _pw_candidates:
        CHROME_PATH = _pw_candidates[0]
    else:
        CHROME_PATH = "/usr/bin/chromium-browser"  # fallback
    CONCURRENT_TABS = 5  # 4 GB RAM — teste com 5 abas simultâneas
else:
    CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

# ─── Utilitários ───────────────────────────────────────────────────────────────
async def human_delay(a: float = 0.15, b: float = 0.7):
    """Pausa com duração aleatória para simular comportamento humano."""
    await asyncio.sleep(random.uniform(a, b))


def load_env(filepath: str) -> dict[str, str]:
    """Carrega variáveis do arquivo .env de forma simples."""
    env_vars: dict[str, str] = {}
    path = Path(filepath)
    if not path.exists():
        return env_vars
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, value = line.split("=", 1)
                env_vars[key.strip()] = value.strip().strip('"').strip("'")
    return env_vars


def load_games(filepath: str) -> list[dict]:
    """Carrega a lista de jogos do arquivo JSON."""
    with open(filepath, encoding="utf-8") as f:
        return json.load(f)


def sanitize_filename(name: str) -> str:
    """Remove caracteres inválidos para nome de arquivo."""
    return "".join(c if c.isalnum() or c in (" ", "-", "_") else "_" for c in name).strip()


# ─── Cloudflare ────────────────────────────────────────────────────────────────
async def check_cloudflare(page: Page) -> bool:
    """
    Verifica se a página está mostrando o challenge do Cloudflare.
    Detecta:
    - Página intersticial clássica (título 'Just a moment')
    - Challenge via iframe /api/challenge (usado pelo 7k após login)
    - Overlay fullscreen com z-index alto (classe _8-ude)
    """
    try:
        title = (await page.title()).lower().strip()

        # 1. Título da página intersticial clássica do CF
        if title in ("just a moment...", "just a moment", "attention required! | cloudflare"):
            logger.info("Cloudflare detectado via título: '%s'", title)
            return True

        # 2. Iframe /api/challenge em tela cheia (como o 7k usa)
        has_challenge = await page.evaluate("""() => {
            // Iframe do /api/challenge (Cloudflare embutido no site)
            const challengeIframe = document.querySelector('iframe[src*="/api/challenge"]');
            if (challengeIframe) {
                const rect = challengeIframe.getBoundingClientRect();
                if (rect.width > 300 && rect.height > 300) return true;
            }

            // Overlay fullscreen com z-index alto (classe _8-ude do 7k)
            const allDivs = document.querySelectorAll('div');
            for (const el of allDivs) {
                const style = window.getComputedStyle(el);
                const z = parseInt(style.zIndex);
                if (style.position === 'fixed' && z >= 9999) {
                    const rect = el.getBoundingClientRect();
                    const vw = window.innerWidth;
                    const vh = window.innerHeight;
                    if (rect.width >= vw * 0.9 && rect.height >= vh * 0.9) {
                        // Verificar se contém texto do CF ou iframe challenge
                        const text = el.innerText || '';
                        if (text.includes('demorando') || text.includes('Atualizar')
                            || text.includes('Fechar') || el.querySelector('iframe[src*="challenge"]')
                            || el.querySelector('iframe[src*="/api/challenge"]')) {
                            return true;
                        }
                    }
                }
            }

            // Challenge intersticial clássico
            if (document.getElementById('challenge-running')
                || document.getElementById('cf-challenge-running')) {
                return true;
            }

            return false;
        }""")

        if has_challenge:
            logger.info("Cloudflare challenge detectado (iframe /api/challenge ou overlay).")
            return True

        return False
    except Exception:
        return False


async def wait_for_cloudflare(page: Page, timeout: int = CF_MAX_WAIT) -> bool:
    """
    Aguarda até o Cloudflare liberar a página (caso resolva sozinho).
    NÃO tenta clicar em nada — se o CF persistir, retorna False.
    """
    for i in range(timeout // 2):
        if not await check_cloudflare(page):
            return True
        logger.info("Cloudflare challenge ativo. Aguardando resolução automática... (%ds/%ds)", (i + 1) * 2, timeout)
        await page.wait_for_timeout(2_000)
    # Salvar screenshot do bloqueio para debug
    try:
        await page.screenshot(path="cloudflare_block.png")
        logger.info("Screenshot do bloqueio Cloudflare salvo em cloudflare_block.png")
    except Exception:
        pass
    return False


# ─── Login ─────────────────────────────────────────────────────────────────────
async def perform_login(page: Page, email: str, senha: str) -> bool:
    """
    Realiza o login na plataforma 7K.
    Segue o padrão do projeto funcional: vai direto na /login com delays humanos.
    Retorna True se o login foi bem-sucedido.
    """
    try:
        logger.info("Acessando página de login: %s", LOGIN_URL)
        await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60_000)

        # Aguardar a página carregar
        await page.wait_for_timeout(5_000)

        # Verificar Cloudflare
        if await check_cloudflare(page):
            logger.warning("Cloudflare bloqueou o acesso na página de login.")
            if not await wait_for_cloudflare(page):
                logger.error(
                    "CLOUDFLARE BLOQUEOU O ACESSO. O captcha não foi resolvido após %ds. "
                    "Encerrando o programa.", CF_MAX_WAIT
                )
                return False
            logger.info("Cloudflare liberou o acesso.")

        # Na /login os campos já estão visíveis
        # Preencher campo de login (email/CPF) com typing humano
        logger.info("Digitando campo de login...")
        email_input = page.locator("#login")
        await email_input.wait_for(state="attached", timeout=30_000)
        await human_delay(1.0, 2.0)
        # Limpar campo antes de digitar (pode ter valor residual)
        await email_input.click()
        await email_input.fill("")
        await email_input.press_sequentially(email, delay=50)
        await human_delay(0.5, 1.0)

        # Verificar o que foi realmente digitado
        typed_email = await email_input.input_value()
        logger.info("Valor no campo email: '%s' (esperado: '%s') match=%s",
                     typed_email, email, typed_email == email)

        await human_delay(1.5, 2.0)

        # Preencher campo de senha com typing humano
        logger.info("Digitando campo de senha...")
        senha_input = page.locator("#password")
        await senha_input.click()
        await senha_input.fill("")
        await senha_input.press_sequentially(senha, delay=50)
        await human_delay(0.5, 1.0)

        # Verificar o que foi realmente digitado
        typed_senha = await senha_input.input_value()
        logger.info("Valor no campo senha: [%d chars] (esperado: [%d chars]) match=%s",
                     len(typed_senha), len(senha), typed_senha == senha)

        await human_delay(1.5, 2.0)

        # Clicar no botão submit ENTRAR
        logger.info("Clicando no botão de login (submit)...")
        login_btn = page.locator("button[type='submit']")
        btn_count = await login_btn.count()
        logger.info("Botões button[type='submit'] encontrados: %d", btn_count)

        if btn_count == 0:
            # Fallback: tentar outros seletores
            for sel in ["button:has-text('Entrar')", "button:has-text('ENTRAR')", "form button"]:
                fallback = page.locator(sel)
                if await fallback.count() > 0:
                    logger.info("Botão encontrado via fallback: %s (count=%d)", sel, await fallback.count())
                    login_btn = fallback.first
                    btn_count = 1
                    break
            if btn_count == 0:
                logger.error("Nenhum botão de login encontrado na página!")
                await page.screenshot(path="login_debug_no_button.png")
                return False

        # Log do texto e estado do botão
        btn_text = await login_btn.first.text_content()
        btn_enabled = await login_btn.first.is_enabled()
        btn_visible = await login_btn.first.is_visible()
        logger.info("Botão: texto='%s', enabled=%s, visible=%s", btn_text, btn_enabled, btn_visible)

        await human_delay(1.0, 2.0)

        # Screenshot antes do clique
        await page.screenshot(path="login_before_click.png")
        logger.info("Screenshot antes do clique salvo em login_before_click.png")

        # Tentar clique normal
        await login_btn.first.click()
        logger.info("Click executado.")

        # Aguardar 3s e capturar mensagem de erro/feedback
        await asyncio.sleep(3)

        # Capturar qualquer mensagem de erro visível na página
        error_selectors = [
            "[class*='error']", "[class*='Error']",
            "[class*='alert']", "[class*='Alert']",
            "[class*='toast']", "[class*='Toast']",
            "[class*='message']", "[class*='Message']",
            "[class*='notification']",
            "[role='alert']",
            "p.text-red", "span.text-red",
            ".Toastify", "[class*='Toastify']",
        ]
        for sel in error_selectors:
            try:
                els = page.locator(sel)
                count = await els.count()
                for i in range(min(count, 3)):
                    txt = await els.nth(i).text_content()
                    vis = await els.nth(i).is_visible()
                    if txt and txt.strip() and vis:
                        logger.warning("Mensagem na tela [%s]: '%s'", sel, txt.strip()[:200])
            except Exception:
                continue

        # Capturar todo texto visível no body para debug
        try:
            body_text = await page.evaluate("() => document.body.innerText")
            # Procurar por padrões de erro comuns
            for keyword in ["inválido", "invalid", "incorret", "erro", "error", "bloqueado", "blocked"]:
                if keyword.lower() in body_text.lower():
                    # Extrair contexto ao redor do keyword
                    idx = body_text.lower().index(keyword.lower())
                    start = max(0, idx - 50)
                    end = min(len(body_text), idx + 100)
                    logger.warning("Texto encontrado no body: '...%s...'", body_text[start:end].replace('\n', ' '))
                    break
        except Exception:
            pass

        url_after_click = page.url
        logger.info("URL após click: %s", url_after_click)

        # Se ainda na /login, tentar métodos alternativos de clique
        if "/login" in url_after_click:
            logger.warning("Ainda na /login após click normal. Tentando Enter no campo de senha...")
            await page.locator("#password").press("Enter")
            await asyncio.sleep(3)

            # Capturar erros novamente após Enter
            try:
                body_text = await page.evaluate("() => document.body.innerText")
                for keyword in ["inválido", "invalid", "incorret", "erro", "error", "bloqueado", "blocked"]:
                    if keyword.lower() in body_text.lower():
                        idx = body_text.lower().index(keyword.lower())
                        start = max(0, idx - 50)
                        end = min(len(body_text), idx + 100)
                        logger.warning("Texto após Enter: '...%s...'", body_text[start:end].replace('\n', ' '))
                        break
            except Exception:
                pass

            logger.info("URL após Enter: %s", page.url)

        # Screenshot após tentativas de clique
        await page.screenshot(path="login_after_click.png")
        logger.info("Screenshot após clique salvo em login_after_click.png")

        logger.info("Aguardando login...")

        # Aguardar redirecionamento ou indicadores de login (até 20s no total)
        for attempt in range(4):
            await asyncio.sleep(5)
            current_url = page.url
            logger.info("Verificação %d/4 — URL atual: %s", attempt + 1, current_url)

            # Verificar se CF apareceu após o submit
            if await check_cloudflare(page):
                try:
                    await page.screenshot(path="cloudflare_block.png")
                except Exception:
                    pass
                logger.error("="*60)
                logger.error("CLOUDFLARE BLOQUEOU APÓS O LOGIN.")
                logger.error("O captcha do Cloudflare apareceu após submeter as credenciais.")
                logger.error("O login NÃO foi concluído. Encerrando.")
                logger.error("="*60)
                return False

            # Verifica se login foi bem-sucedido (saiu da /login)
            if "/login" not in current_url:
                logger.info("Login realizado com sucesso! (redirecionado para: %s)", current_url)
                return True

            # Checar indicadores de usuário logado
            user_indicators = [
                "button:has-text('Depositar')",
                "button:has-text('DEPOSITAR')",
                "[class*='balance']",
                "[class*='wallet']",
                "[class*='avatar']",
            ]
            for indicator in user_indicators:
                try:
                    if await page.locator(indicator).first.is_visible(timeout=1_000):
                        logger.info("Login confirmado via indicador: %s", indicator)
                        return True
                except Exception:
                    continue

        # Salvar screenshot de debug antes de falhar
        try:
            await page.screenshot(path="login_debug.png")
            logger.info("Screenshot de debug salvo em login_debug.png")
        except Exception:
            pass

        logger.error("Login não confirmado após 20s. URL final: %s", page.url)
        return False

    except Exception as e:
        logger.error("Erro durante o login: %s", e)
        return False


async def dismiss_popups(page: Page) -> None:
    """
    Fecha popups que podem aparecer após o login:
    1. Popup de cookies ("Aceitar todos")
    2. Overlay promocional (ex: "INDIQUE E GANHE") cobrindo a tela inteira
    3. Caixinha flutuante de recompensas/mini-games no canto inferior direito
    """
    # 1. Popup de cookies
    try:
        cookie_btn = page.locator("text=Aceitar todos")
        if await cookie_btn.is_visible(timeout=2_000):
            await cookie_btn.click()
            logger.info("Popup de cookies fechado.")
            await page.wait_for_timeout(1_000)
    except Exception:
        pass

    # 2. Overlay promocional (div fixed cobrindo tela inteira com botão fechar)
    #    Detecta via JS: elemetos fixed que cobrem >90% da viewport
    try:
        closed = await page.evaluate("""() => {
            let closed = 0;
            const vw = window.innerWidth;
            const vh = window.innerHeight;
            document.querySelectorAll('div').forEach(el => {
                const style = window.getComputedStyle(el);
                if (style.position === 'fixed') {
                    const rect = el.getBoundingClientRect();
                    if (rect.width >= vw * 0.9 && rect.height >= vh * 0.9) {
                        const closeBtn = el.querySelector('button');
                        if (closeBtn) {
                            closeBtn.click();
                            closed++;
                        }
                    }
                }
            });
            return closed;
        }""")
        if closed:
            logger.info("Overlay promocional fechado (%d elemento(s)).", closed)
            await page.wait_for_timeout(1_000)
    except Exception:
        pass

    # 3. Caixinha flutuante de recompensas/mini-games (canto inferior direito)
    #    Pequeno widget fixed no canto inferior direito (<100px de largura)
    try:
        closed = await page.evaluate("""() => {
            let closed = 0;
            const vw = window.innerWidth;
            const vh = window.innerHeight;
            document.querySelectorAll('div').forEach(el => {
                const style = window.getComputedStyle(el);
                if (style.position === 'fixed') {
                    const rect = el.getBoundingClientRect();
                    // Widget pequeno no canto inferior direito
                    if (rect.width > 20 && rect.width < 120
                        && rect.height > 20 && rect.height < 120
                        && rect.right > vw * 0.8
                        && rect.bottom > vh * 0.8) {
                        el.style.display = 'none';
                        closed++;
                    }
                }
            });
            return closed;
        }""")
        if closed:
            logger.info("Caixa de recompensas/mini-games ocultada (%d elemento(s)).", closed)
            await page.wait_for_timeout(500)
    except Exception:
        pass


async def check_and_relogin(page: Page, context: BrowserContext, email: str, senha: str) -> bool:
    """
    Verifica se a página está pedindo login novamente.
    Se sim, realiza o login na aba atual.
    """
    try:
        entrar_btn = page.locator("button.uBcPR:has-text('ENTRAR')")
        if await entrar_btn.is_visible(timeout=3_000):
            logger.warning("Sessão expirada detectada. Realizando login novamente...")
            return await perform_login(page, email, senha)
    except Exception:
        pass
    return True


# ─── Captura de screenshots dos jogos ──────────────────────────────────────────
async def capture_game(
    context: BrowserContext,
    slug: str,
    evidence_dir: Path,
    email: str,
    senha: str,
) -> dict:
    """
    Abre uma nova aba, carrega o jogo, captura screenshot do iframe.
    Retorna dicionário com resultado.
    """
    link = f"{GAMES_BASE_URL}{slug}"
    result = {
        "slug": slug,
        "brand": BRAND,
        "status": "off",
        "motivo": "",
    }

    page = await context.new_page()
    try:
        logger.info("Carregando jogo: %s (%s)", slug, link)
        await page.goto(link, wait_until="domcontentloaded", timeout=30_000)
        await page.wait_for_timeout(3_000)

        # Verificar se Cloudflare bloqueou esta aba
        if await check_cloudflare(page):
            result["motivo"] = "Cloudflare bloqueou o acesso ao jogo."
            logger.error("CF bloqueou: %s", slug)
            return result

        # Verificar se precisa re-login (botão ENTRAR da navbar visível)
        needs_login = False
        try:
            entrar_btn = page.locator("button.uBcPR:has-text('ENTRAR')")
            if await entrar_btn.is_visible(timeout=3_000):
                needs_login = True
        except Exception:
            pass

        if needs_login:
            logger.warning("Jogo '%s' requer login. Realizando re-login...", slug)
            login_ok = await perform_login(page, email, senha)
            if not login_ok:
                result["motivo"] = "Falha no re-login (possível Cloudflare)"
                return result
            await page.goto(link, wait_until="domcontentloaded", timeout=30_000)
            await page.wait_for_timeout(3_000)

        # Aguardar 15 segundos para o jogo carregar
        logger.info("Aguardando 15 segundos para o jogo '%s' carregar...", slug)
        await page.wait_for_timeout(GAME_LOAD_TIMEOUT)

        # Tentar capturar o iframe do jogo
        iframe_selectors = [
            "iframe[src*='game']",
            "iframe[src*='play']",
            "iframe[src*='launch']",
            "iframe[class*='game']",
            "iframe[id*='game']",
            "iframe",
        ]

        iframe_element = None
        for selector in iframe_selectors:
            try:
                locator = page.locator(selector).first
                if await locator.is_visible(timeout=3_000):
                    iframe_element = locator
                    logger.info("Iframe encontrado para '%s': %s", slug, selector)
                    break
            except Exception:
                continue

        filename = f"{sanitize_filename(slug.replace('/', '_'))}_{BRAND}.png"
        filepath = evidence_dir / filename

        if iframe_element:
            result["status"] = "on"
            if IS_PROD:
                result["motivo"] = "Jogo carregado com sucesso (iframe encontrado)."
                logger.info("Iframe encontrado para '%s' — jogo ON", slug)
            else:
                await iframe_element.screenshot(path=str(filepath))
                result["motivo"] = "Jogo carregado e screenshot capturado com sucesso."
                logger.info("Screenshot capturado: %s", filepath)
        else:
            if IS_PROD:
                result["motivo"] = "Iframe do jogo não encontrado."
                logger.warning("Iframe não encontrado para '%s' — jogo OFF", slug)
            else:
                logger.warning("Iframe não encontrado para '%s'. Capturando página inteira.", slug)
                await page.screenshot(path=str(filepath), full_page=False)
                result["motivo"] = "Iframe do jogo não encontrado. Screenshot da página capturado."

    except PlaywrightTimeout:
        result["motivo"] = f"Timeout ao carregar o jogo."
        logger.error("Timeout: %s", slug)
    except Exception as e:
        result["motivo"] = f"Erro ao processar jogo: {e}"
        logger.error("Erro em %s: %s", slug, e)
    finally:
        await page.close()

    return result


async def process_batch(
    context: BrowserContext,
    batch: list[str],
    evidence_dir: Path,
    email: str,
    senha: str,
) -> list[dict]:
    """Processa um lote de slugs em abas simultâneas."""
    tasks = [
        capture_game(context, slug, evidence_dir, email, senha)
        for slug in batch
    ]
    return await asyncio.gather(*tasks)


# ─── Fluxo principal ──────────────────────────────────────────────────────────
async def main():
    # Carregar credenciais
    env_vars = load_env(ENV_FILE)
    email = os.environ.get("EMAIL") or env_vars.get("EMAIL", "")
    senha = os.environ.get("SENHA") or env_vars.get("SENHA", "")

    if not email or not senha or email == "seu_email@exemplo.com":
        logger.error("Credenciais não configuradas! Edite o arquivo .env com seu EMAIL e SENHA.")
        sys.exit(1)

    # Carregar jogos
    if not Path(INPUT_FILE).exists():
        logger.error("Arquivo %s não encontrado!", INPUT_FILE)
        sys.exit(1)

    slugs = load_games(INPUT_FILE)
    # DEBUG: apenas 10 primeiros para teste
    slugs = slugs[:10]
    logger.info("Total de jogos a verificar: %d", len(slugs))

    # Criar pasta de evidências
    evidence_dir = Path(EVIDENCE_DIR)
    evidence_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results: list[dict] = []

    # ─── Garantir pasta do perfil ───
    profile_abs = str(Path(PROFILE_DIR).resolve())
    Path(profile_abs).mkdir(exist_ok=True)

    # ─── Encerrar Chrome existente ───
    logger.info("Encerrando processos Chrome existentes...")
    if IS_PROD:
        subprocess.run(["pkill", "-f", "chrome"],
                       capture_output=True, timeout=10)
    else:
        subprocess.run(["taskkill", "/F", "/IM", "chrome.exe"],
                       capture_output=True, timeout=10)
    await asyncio.sleep(3)

    # ─── Lançar Chrome REAL via subprocess (sem flags de automação) ───
    logger.info("Lançando Chrome real na porta CDP %d...", CDP_PORT)
    chrome_args = [
        CHROME_PATH,
        f"--remote-debugging-port={CDP_PORT}",
        f"--user-data-dir={profile_abs}",
        "--no-first-run",
        "--no-default-browser-check",
        "--window-size=1366,768",
        "--lang=pt-BR",
    ]
    if IS_PROD:
        chrome_args.extend(["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"])
    chrome_proc = subprocess.Popen(chrome_args)
    logger.info("Chrome PID: %d", chrome_proc.pid)

    # ─── Aguardar CDP ficar pronto (polling) ───
    cdp_url = f"http://localhost:{CDP_PORT}/json/version"
    for attempt in range(15):
        await asyncio.sleep(1)
        try:
            urllib.request.urlopen(cdp_url, timeout=2)
            logger.info("CDP pronto na tentativa %d.", attempt + 1)
            break
        except Exception:
            if attempt == 14:
                logger.error("Chrome não respondeu no CDP após 15s. Abortando.")
                chrome_proc.terminate()
                sys.exit(1)

    async with async_playwright() as p:
        # Conectar ao Chrome via CDP
        logger.info("Conectando ao Chrome via CDP (localhost:%d)...", CDP_PORT)
        browser = await p.chromium.connect_over_cdp(f"http://localhost:{CDP_PORT}")
        logger.info("Conectado! Contextos: %d", len(browser.contexts))
        context = browser.contexts[0] if browser.contexts else await browser.new_context()

        # Adicionar header customizado em TODAS as requisições do contexto
        await context.set_extra_http_headers({
            "casinobot": "BB2017F6-49A1-4C56-86F3-51F6A5F4EEEF",
        })
        logger.info("Header customizado 'casinobot' adicionado a todas as requisições.")

        # Página de login — abrir nova aba dedicada
        main_page = await context.new_page()
        logger.info("Nova aba criada para login.")
        login_ok = await perform_login(main_page, email, senha)

        if not login_ok:
            logger.error("="*60)
            logger.error("PROGRAMA ENCERRADO: Falha no login.")
            logger.error("="*60)
            await browser.close()
            chrome_proc.terminate()
            sys.exit(1)

        # Fechar popups pós-login (cookies, promoções, caixa de recompensas)
        await dismiss_popups(main_page)

        # Manter main_page aberta como âncora (CDP fecha o contexto se todas as abas fecham)
        # Navegar para página leve para não consumir recursos
        await main_page.goto("about:blank")

        # Processar jogos em lotes de CONCURRENT_TABS (3 abas simultâneas)
        for i in range(0, len(slugs), CONCURRENT_TABS):
            batch = slugs[i : i + CONCURRENT_TABS]
            batch_num = (i // CONCURRENT_TABS) + 1
            total_batches = (len(slugs) + CONCURRENT_TABS - 1) // CONCURRENT_TABS
            logger.info(
                "Processando lote %d/%d (%d jogos)...",
                batch_num,
                total_batches,
                len(batch),
            )

            batch_results = await process_batch(
                context, batch, evidence_dir, email, senha
            )
            results.extend(batch_results)

            # Pequena pausa entre lotes para não sobrecarregar
            if i + CONCURRENT_TABS < len(slugs):
                await asyncio.sleep(2)

        await browser.close()
        chrome_proc.terminate()

    # Gerar relatório
    report = generate_report(results, timestamp)
    report_path = evidence_dir / "relatorio.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    logger.info("Relatório salvo em: %s", report_path)

    # Exibir resumo
    print_summary(results)

    # Enviar resultados ao Supabase
    try:
        send_results(results, BRAND)
    except Exception as e:
        logger.error("Erro ao enviar resultados ao Supabase: %s", e)


def generate_report(results: list[dict], timestamp: str) -> dict:
    """Gera relatório consolidado."""
    total = len(results)
    on = sum(1 for r in results if r["status"] == "on")
    off = sum(1 for r in results if r["status"] == "off")

    return {
        "timestamp": timestamp,
        "total_jogos": total,
        "on": on,
        "off": off,
        "resultados": results,
    }


def print_summary(results: list[dict]):
    """Exibe resumo no console."""
    print("\n" + "=" * 70)
    print("  RELATÓRIO DE MONITORAMENTO - 7K BET")
    print("=" * 70)

    for r in results:
        icon = "✅" if r["status"] == "on" else "❌"
        print(f"  {icon} {r['slug']} - {r['status'].upper()}")
        if r["motivo"]:
            print(f"     {r['motivo']}")

    total = len(results)
    on = sum(1 for r in results if r["status"] == "on")
    print(f"\n  Total: {total} | ON: {on} | OFF: {total - on}")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
