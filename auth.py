"""
Autenticação e Cloudflare — login, popups e bypass do CF challenge.
"""

import asyncio

from playwright.async_api import Page, BrowserContext, TimeoutError as PlaywrightTimeoutError

from config import (
    BASE_URL, LOGIN_URL, CF_MAX_WAIT, logger,
)
from utils import human_delay


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

        if title in ("just a moment...", "just a moment", "attention required! | cloudflare"):
            logger.info("Cloudflare detectado via título: '%s'", title)
            return True

        has_challenge = await page.evaluate("""() => {
            const challengeIframe = document.querySelector('iframe[src*="/api/challenge"]');
            if (challengeIframe) {
                const rect = challengeIframe.getBoundingClientRect();
                if (rect.width > 300 && rect.height > 300) return true;
            }

            const allDivs = document.querySelectorAll('div');
            for (const el of allDivs) {
                const style = window.getComputedStyle(el);
                const z = parseInt(style.zIndex);
                if (style.position === 'fixed' && z >= 9999) {
                    const rect = el.getBoundingClientRect();
                    const vw = window.innerWidth;
                    const vh = window.innerHeight;
                    if (rect.width >= vw * 0.9 && rect.height >= vh * 0.9) {
                        const text = el.innerText || '';
                        if (text.includes('demorando') || text.includes('Atualizar')
                            || text.includes('Fechar') || el.querySelector('iframe[src*="challenge"]')
                            || el.querySelector('iframe[src*="/api/challenge"]')) {
                            return true;
                        }
                    }
                }
            }

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
    Retorna True se o login foi bem-sucedido.
    """
    try:
        logger.info("Acessando página de login: %s", LOGIN_URL)
        try:
            await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60_000)
        except PlaywrightTimeoutError:
            logger.error(
                "TIMEOUT ao carregar a página de login (%s). "
                "O site não respondeu em 60s. "
                "Causas prováveis: site fora do ar, instabilidade de rede, ou Cloudflare bloqueando a conexão antes mesmo de exibir o challenge.",
                LOGIN_URL,
            )
            try:
                await page.screenshot(path="login_timeout.png")
                logger.info("Screenshot do timeout salvo em login_timeout.png")
            except Exception:
                pass
            return False
        await page.wait_for_timeout(5_000)

        if await check_cloudflare(page):
            logger.warning("Cloudflare bloqueou o acesso na página de login.")
            if not await wait_for_cloudflare(page):
                logger.error(
                    "CLOUDFLARE BLOQUEOU O ACESSO. O captcha não foi resolvido após %ds. "
                    "Encerrando o programa.", CF_MAX_WAIT
                )
                return False
            logger.info("Cloudflare liberou o acesso.")

        logger.info("Digitando campo de login...")
        email_input = page.locator("#login")
        try:
            await email_input.wait_for(state="attached", timeout=30_000)
        except Exception as e_form:
            url_now = page.url
            title_now = await page.title()
            logger.error(
                "TIMEOUT: campo #login não encontrado em 30s após a página carregar. "
                "URL atual: %s | Título: '%s'. "
                "Possíveis causas: Cloudflare challenge não detectado (página intermediária), "
                "estrutura da página mudou (ID do campo alterado), "
                "ou redirecionamento inesperado antes do formulário. "
                "Detalhe: %s",
                url_now, title_now, e_form,
            )
            try:
                await page.screenshot(path="login_form_timeout.png")
                logger.info("Screenshot salvo em login_form_timeout.png para diagnóstico.")
            except Exception:
                pass
            return False
        await human_delay(1.0, 2.0)
        await email_input.click()
        await email_input.fill("")
        await email_input.press_sequentially(email, delay=50)
        await human_delay(0.5, 1.0)

        await human_delay(1.5, 2.0)

        logger.info("Digitando campo de senha...")
        senha_input = page.locator("#password")
        await senha_input.click()
        await senha_input.fill("")
        await senha_input.press_sequentially(senha, delay=50)
        await human_delay(0.5, 1.0)

        await human_delay(1.5, 2.0)

        logger.info("Clicando no botão de login (submit)...")
        login_btn = page.locator("button[type='submit']")
        btn_count = await login_btn.count()

        if btn_count == 0:
            for sel in ["button:has-text('Entrar')", "button:has-text('ENTRAR')", "form button"]:
                fallback = page.locator(sel)
                if await fallback.count() > 0:
                    login_btn = fallback.first
                    btn_count = 1
                    break
            if btn_count == 0:
                logger.error("Nenhum botão de login encontrado na página!")
                return False

        await human_delay(1.0, 2.0)
        await login_btn.first.click()
        logger.info("Click no botão de login executado.")
        await asyncio.sleep(3)

        url_after_click = page.url

        if "/login" in url_after_click:
            logger.warning("Ainda na /login após click. Tentando Enter...")
            await page.locator("#password").press("Enter")
            await asyncio.sleep(3)

        logger.info("Aguardando login...")

        for attempt in range(4):
            await asyncio.sleep(5)
            current_url = page.url
            logger.info("Verificação %d/4 — URL atual: %s", attempt + 1, current_url)

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

            if "/login" not in current_url:
                logger.info("Login realizado com sucesso! (redirecionado para: %s)", current_url)
                return True

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

        logger.error("Login não confirmado após 20s. URL final: %s", page.url)
        return False

    except Exception as e:
        logger.error("Erro inesperado durante o login: %s", e)
        return False


# ─── Popups ────────────────────────────────────────────────────────────────────
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

    # 2. Overlay promocional
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

    # 3. Caixinha flutuante de recompensas/mini-games
    try:
        closed = await page.evaluate("""() => {
            let closed = 0;
            const vw = window.innerWidth;
            const vh = window.innerHeight;
            document.querySelectorAll('div').forEach(el => {
                const style = window.getComputedStyle(el);
                if (style.position === 'fixed') {
                    const rect = el.getBoundingClientRect();
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
