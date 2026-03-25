"""
Captura de jogos — abre abas, detecta iframes, verifica conteúdo e captura screenshots.
"""

import asyncio
from pathlib import Path

from playwright.async_api import BrowserContext, TimeoutError as PlaywrightTimeout

from config import (
    BRAND, GAMES_BASE_URL, GAME_LOAD_TIMEOUT, PER_GAME_TIMEOUT,
    BASE_URL, logger,
)
from utils import sanitize_filename
from auth import check_cloudflare, perform_login
from diagnostics import (
    run_diagnostics, check_session_expired, check_iframe_off_reason, is_403_error,
)


IFRAME_SELECTORS = [
    "iframe[src*='game']",
    "iframe[src*='play']",
    "iframe[src*='launch']",
    "iframe[class*='game']",
    "iframe[id*='game']",
    "iframe",
]


async def _verify_page_url(page, link: str, slug: str) -> bool:
    """Verifica se a página ainda está na URL correta do jogo. Renavega se necessário."""
    try:
        if slug.lower() not in page.url.lower():
            logger.warning("[%s] URL alterada (%s). Renavegando...", slug, page.url[:80])
            await page.goto(link, wait_until="domcontentloaded", timeout=15_000)
            await page.wait_for_timeout(3_000)
            return True
    except Exception as exc:
        logger.warning("[%s] Erro ao verificar URL: %s", slug, exc)
    return False


async def _restore_batch_pages(page_urls: dict, current_page) -> None:
    """Após re-login, verifica e restaura URLs de outras páginas do lote."""
    for pid, (other_page, expected_url) in list(page_urls.items()):
        if other_page == current_page:
            continue
        try:
            if other_page.is_closed():
                continue
            current_url = other_page.url
            if expected_url and (
                "login" in current_url
                or current_url.rstrip("/") == BASE_URL.rstrip("/")
                or current_url == "about:blank"
            ):
                logger.warning(
                    "Página do lote redirecionada (%s). Restaurando para %s...",
                    current_url[:80], expected_url,
                )
                await other_page.goto(expected_url, wait_until="domcontentloaded", timeout=15_000)
        except Exception as exc:
            logger.warning("Erro ao restaurar página do lote: %s", exc)


async def capture_game(
    context: BrowserContext,
    slug: str,
    evidence_dir: Path,
    email: str,
    senha: str,
    relogin_lock: asyncio.Lock | None = None,
    page_urls: dict | None = None,
) -> dict:
    """
    Abre uma nova aba, carrega o jogo, captura screenshot do iframe.
    Retorna dicionário com resultado + diagnóstico detalhado + tentativas.
    """
    link = f"{GAMES_BASE_URL}{slug}"
    result = {
        "slug": slug,
        "brand": BRAND,
        "status": "off",
        "motivo": "",
    }
    diag = {
        "url_final": "",
        "game_iframe_found": False,
        "game_iframe_frames": None,
        "game_iframe_content": None,
        "textos_suspeitos": [],
        "erro": None,
    }
    tentativas = []

    page = await context.new_page()
    page.set_default_timeout(15_000)
    if page_urls is not None:
        page_urls[id(page)] = (page, link)
    try:
        logger.info("[%s] Carregando...", slug)
        await page.goto(link, wait_until="domcontentloaded", timeout=15_000)
        logger.info("[%s] Página carregada. Estabilizando...", slug)
        await page.wait_for_timeout(2_000)

        # Verificar Cloudflare
        if await check_cloudflare(page):
            result["motivo"] = "Cloudflare bloqueou o acesso ao jogo."
            tentativas.append({"n": 1, "acao": "carga", "resultado": "cf_bloqueio"})
            logger.error("CF bloqueou: %s", slug)
            err_path = evidence_dir / f"ERR_{sanitize_filename(slug.replace('/', '_'))}.png"
            try:
                await page.screenshot(path=str(err_path), full_page=False)
            except Exception:
                pass
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
            _lock = relogin_lock or asyncio.Lock()
            async with _lock:
                login_ok = await perform_login(page, email, senha)
                if login_ok and page_urls:
                    await _restore_batch_pages(page_urls, page)
            if not login_ok:
                result["motivo"] = "Falha no re-login (possível Cloudflare)"
                tentativas.append({"n": 1, "acao": "relogin_navbar", "resultado": "falha_login"})
                err_path = evidence_dir / f"ERR_{sanitize_filename(slug.replace('/', '_'))}.png"
                try:
                    await page.screenshot(path=str(err_path), full_page=False)
                except Exception:
                    pass
                return result
            await page.goto(link, wait_until="domcontentloaded", timeout=30_000)
            await page.wait_for_timeout(3_000)

        # Aguardar o jogo carregar
        logger.info("[%s] Aguardando jogo carregar (%dms)...", slug, GAME_LOAD_TIMEOUT)
        await page.wait_for_timeout(GAME_LOAD_TIMEOUT)
        await _verify_page_url(page, link, slug)
        logger.info("[%s] Tempo de carga concluído. Analisando...", slug)

        # ── DIAGNÓSTICO ──
        diag_timed_out = await run_diagnostics(page, diag, slug)

        # Se o diagnóstico travou, o jogo WebGL está carregado
        if diag_timed_out:
            result["status"] = "on"
            result["motivo"] = "Jogo carregado (WebGL pesado — diagnóstico travou, iframe presente)."
            tentativas.append({"n": 1, "acao": "carga", "resultado": "ok_diag_timeout"})
            logger.info("[%s] Diagnóstico travou mas jogo está ON (WebGL pesado).", slug)
            ok_path = evidence_dir / f"{sanitize_filename(slug.replace('/', '_'))}_{BRAND}.png"
            try:
                await page.screenshot(path=str(ok_path), full_page=False)
            except Exception:
                pass
        else:
            iframe_element = None
            for selector in IFRAME_SELECTORS:
                try:
                    locator = page.locator(selector).first
                    if await locator.is_visible(timeout=3_000):
                        iframe_element = locator
                        logger.info("[%s] Iframe encontrado: %s", slug, selector)
                        break
                except Exception:
                    continue
            # Fallback: se não achou visível, tentar por count (iframes hidden/lazy)
            if not iframe_element:
                for selector in IFRAME_SELECTORS:
                    try:
                        locator = page.locator(selector).first
                        if await locator.count() > 0:
                            iframe_element = locator
                            logger.info("[%s] Iframe encontrado (por count, não visível): %s", slug, selector)
                            break
                    except Exception:
                        continue

            # Se não encontrou iframe, reload e tentar novamente
            if not iframe_element:
                tentativas.append({"n": 1, "acao": "carga", "resultado": "sem_iframe"})
                logger.warning("[%s] Iframe não encontrado. Recarregando página...", slug)
                try:
                    await page.reload(wait_until="domcontentloaded", timeout=15_000)
                    await page.wait_for_timeout(GAME_LOAD_TIMEOUT)
                    logger.info("[%s] Reload concluído. Buscando iframe novamente...", slug)
                    for selector in IFRAME_SELECTORS:
                        try:
                            locator = page.locator(selector).first
                            if await locator.is_visible(timeout=2_000):
                                iframe_element = locator
                                logger.info("[%s] Iframe encontrado após reload: %s", slug, selector)
                                tentativas.append({"n": 2, "acao": "reload", "resultado": "iframe_encontrado"})
                                break
                        except Exception:
                            continue
                    if not iframe_element:
                        tentativas.append({"n": 2, "acao": "reload", "resultado": "sem_iframe"})
                except Exception as reload_err:
                    tentativas.append({"n": 2, "acao": "reload", "resultado": "erro", "detalhe": str(reload_err)[:200]})
                    logger.error("[%s] Reload falhou: %s", slug, reload_err)

            filename = f"{sanitize_filename(slug.replace('/', '_'))}_{BRAND}.png"
            filepath = evidence_dir / filename

            if iframe_element:
                # Obter conteúdo dos frames para verificação
                all_frames_content = diag.get("game_iframe_frames") or []
                if not all_frames_content:
                    fc = diag.get("game_iframe_content")
                    if fc:
                        all_frames_content = [fc]

                # Verificar sessão expirada
                if check_session_expired(all_frames_content):
                    logger.warning("[%s] Sessão expirada detectada no iframe. Re-login...", slug)
                    tentativas.append({"n": len(tentativas) + 1, "acao": "carga", "resultado": "sessao_expirada"})
                    try:
                        _lock = relogin_lock or asyncio.Lock()
                        login_ok = False
                        async with _lock:
                            await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=15_000)
                            await page.wait_for_timeout(2_000)
                            login_ok = await perform_login(page, email, senha)
                            if login_ok and page_urls:
                                await _restore_batch_pages(page_urls, page)
                        if login_ok:
                            await page.goto(link, wait_until="domcontentloaded", timeout=15_000)
                            await page.wait_for_timeout(GAME_LOAD_TIMEOUT)
                            iframe_element = None
                            for selector in IFRAME_SELECTORS:
                                try:
                                    locator = page.locator(selector).first
                                    if await locator.is_visible(timeout=2_000):
                                        iframe_element = locator
                                        logger.info("[%s] Iframe encontrado após re-login: %s", slug, selector)
                                        break
                                except Exception:
                                    continue
                            if iframe_element:
                                result["status"] = "on"
                                await iframe_element.screenshot(path=str(filepath))
                                result["motivo"] = "Jogo carregado após re-login (sessão expirada)."
                                tentativas.append({"n": len(tentativas) + 1, "acao": "relogin_sessao", "resultado": "ok"})
                                logger.info("[%s] Jogo recuperado após re-login — ON", slug)
                            else:
                                result["status"] = "off"
                                result["motivo"] = "Iframe não encontrado mesmo após re-login (sessão expirada)."
                                tentativas.append({"n": len(tentativas) + 1, "acao": "relogin_sessao", "resultado": "sem_iframe"})
                                err_path = evidence_dir / f"ERR_{sanitize_filename(slug.replace('/', '_'))}.png"
                                try:
                                    await page.screenshot(path=str(err_path), full_page=False)
                                except Exception:
                                    pass
                        else:
                            result["status"] = "off"
                            result["motivo"] = "Re-login falhou após sessão expirada."
                            tentativas.append({"n": len(tentativas) + 1, "acao": "relogin_sessao", "resultado": "falha_login"})
                            err_path = evidence_dir / f"ERR_{sanitize_filename(slug.replace('/', '_'))}.png"
                            try:
                                await page.screenshot(path=str(err_path), full_page=False)
                            except Exception:
                                pass
                    except Exception as relogin_err:
                        result["status"] = "off"
                        result["motivo"] = f"Erro no re-login: {relogin_err}"
                        tentativas.append({"n": len(tentativas) + 1, "acao": "relogin_sessao", "resultado": "erro", "detalhe": str(relogin_err)[:200]})
                        logger.error("[%s] Erro no re-login: %s", slug, relogin_err)
                        err_path = evidence_dir / f"ERR_{sanitize_filename(slug.replace('/', '_'))}.png"
                        try:
                            await page.screenshot(path=str(err_path), full_page=False)
                        except Exception:
                            pass
                else:
                    # Verificar manutenção e erros
                    iframe_off_reason = check_iframe_off_reason(all_frames_content)

                    if iframe_off_reason and "g1006" in iframe_off_reason.lower():
                        # G1006 = falha de transferência PGSoft — tentar clicar "Confirmar" até 3x
                        MAX_G1006_RETRIES = 3
                        g1006_recovered = False
                        for g1006_attempt in range(1, MAX_G1006_RETRIES + 1):
                            logger.info("[%s] G1006 detectado — tentativa %d/%d de clicar 'Confirmar'...", slug, g1006_attempt, MAX_G1006_RETRIES)
                            tentativas.append({"n": len(tentativas) + 1, "acao": "g1006_retry", "resultado": f"tentativa_{g1006_attempt}"})
                            clicked = False
                            try:
                                for frame in page.frames:
                                    if frame == page.main_frame or not frame.url or frame.url == "about:blank":
                                        continue
                                    try:
                                        btn = frame.locator("text=Confirmar").first
                                        if await btn.is_visible(timeout=2_000):
                                            await btn.click()
                                            clicked = True
                                            logger.info("[%s] Botão 'Confirmar' clicado. Aguardando recarga (%ds)...", slug, GAME_LOAD_TIMEOUT // 1000)
                                            await page.wait_for_timeout(GAME_LOAD_TIMEOUT)
                                            break
                                    except Exception:
                                        continue
                            except Exception as g1006_err:
                                logger.error("[%s] Erro no retry G1006: %s", slug, g1006_err)
                                break

                            if not clicked:
                                logger.warning("[%s] Botão 'Confirmar' não encontrado nos frames.", slug)
                                break

                            # Revalidar conteúdo do iframe
                            retry_frames = []
                            for f in page.frames:
                                if f == page.main_frame or not f.url or f.url == "about:blank":
                                    continue
                                try:
                                    txt = (await f.evaluate("() => document.body ? document.body.innerText : ''") or "")[:500]
                                    title = await f.evaluate("() => document.title || ''") or ""
                                    retry_frames.append({"text": txt, "title": title, "frame_url": f.url[:100]})
                                except Exception:
                                    continue
                            retry_reason = check_iframe_off_reason(retry_frames)
                            if not retry_reason:
                                g1006_recovered = True
                                result["status"] = "on"
                                result["motivo"] = f"Jogo carregado após {g1006_attempt}x retry G1006."
                                tentativas.append({"n": len(tentativas) + 1, "acao": "g1006_confirmar", "resultado": "ok"})
                                logger.info("[%s] Jogo recuperado após %d retry(s) G1006 — ON", slug, g1006_attempt)
                                break
                            elif "g1006" not in retry_reason.lower():
                                # Erro mudou (não é mais G1006) — não insistir
                                iframe_off_reason = retry_reason
                                break
                            else:
                                iframe_off_reason = retry_reason
                                logger.warning("[%s] G1006 persiste após tentativa %d.", slug, g1006_attempt)

                        if not g1006_recovered:
                            result["status"] = "off"
                            result["motivo"] = iframe_off_reason
                            tentativas.append({"n": len(tentativas) + 1, "acao": "g1006_confirmar", "resultado": "falhou_todas_tentativas"})
                            logger.warning("G1006 persistiu após %d tentativas para '%s': %s", MAX_G1006_RETRIES, slug, iframe_off_reason[:100])
                        await iframe_element.screenshot(path=str(filepath))

                    elif iframe_off_reason:
                        if is_403_error(iframe_off_reason):
                            result["status"] = "403"
                        else:
                            result["status"] = "off"
                        result["motivo"] = iframe_off_reason
                        tentativas.append({"n": len(tentativas) + 1, "acao": "carga", "resultado": "erro_conteudo", "detalhe": iframe_off_reason[:200]})
                        logger.warning("Iframe encontrado mas jogo %s para '%s': %s", result["status"].upper(), slug, iframe_off_reason)
                        await iframe_element.screenshot(path=str(filepath))
                    else:
                        result["status"] = "on"
                        await iframe_element.screenshot(path=str(filepath))
                        result["motivo"] = "Jogo carregado com sucesso (iframe encontrado)."
                        logger.info("Iframe encontrado para '%s' — jogo ON (screenshot: %s)", slug, filepath)
                        tentativas.append({"n": len(tentativas) + 1, "acao": "carga", "resultado": "ok"})
            else:
                tentativas.append({"n": len(tentativas) + 1, "acao": "carga", "resultado": "sem_iframe"})
                logger.warning("Iframe não encontrado para '%s'. Capturando página inteira.", slug)
                await page.screenshot(path=str(filepath), full_page=False)
                # Capturar texto da página para detalhar o motivo do erro
                page_hint = ""
                try:
                    body = await page.evaluate("() => document.body ? document.body.innerText : ''")
                    if body:
                        page_hint = body.strip().replace('\n', ' ')[:200]
                except Exception:
                    pass
                if page_hint:
                    result["motivo"] = f"Iframe não encontrado — conteúdo da página: '{page_hint}'"
                else:
                    result["motivo"] = "Iframe do jogo não encontrado. Screenshot da página capturado."

    except PlaywrightTimeout:
        tentativas.append({"n": len(tentativas) + 1, "acao": "carga", "resultado": "timeout"})
        logger.warning("[%s] Timeout no carregamento. Recarregando para confirmar...", slug)
        try:
            await page.reload(wait_until="domcontentloaded", timeout=15_000)
            await page.wait_for_timeout(15_000)
            for selector in ["iframe#gameIframe", "iframe[src*='game']", "iframe[src*='play']", "iframe[src*='launch']"]:
                try:
                    loc = page.locator(selector).first
                    if await loc.is_visible(timeout=2_000):
                        # Validar conteúdo do iframe antes de marcar ON
                        retry_frames = []
                        for f in page.frames:
                            if f == page.main_frame or not f.url or f.url == "about:blank":
                                continue
                            try:
                                txt = (await f.evaluate("() => document.body ? document.body.innerText : ''") or "")[:500]
                                title = await f.evaluate("() => document.title || ''") or ""
                                retry_frames.append({"text": txt, "title": title, "frame_url": f.url[:100]})
                            except Exception:
                                continue
                        off_reason = check_iframe_off_reason(retry_frames)
                        if off_reason:
                            result["status"] = "403" if is_403_error(off_reason) else "off"
                            result["motivo"] = off_reason
                            tentativas.append({"n": len(tentativas) + 1, "acao": "reload_timeout", "resultado": "erro_conteudo", "detalhe": off_reason[:200]})
                            logger.warning("[%s] Iframe encontrado após reload mas conteúdo com erro — %s", slug, result["status"].upper())
                        else:
                            result["status"] = "on"
                            result["motivo"] = "Jogo carregado após retry (reload)."
                            tentativas.append({"n": len(tentativas) + 1, "acao": "reload_timeout", "resultado": "ok"})
                            logger.info("[%s] Jogo carregou após reload — ON", slug)
                        filepath = evidence_dir / f"{sanitize_filename(slug.replace('/', '_'))}_{BRAND}.png"
                        await loc.screenshot(path=str(filepath))
                        break
                except Exception:
                    continue
            if result["status"] == "off":
                result["motivo"] = "Instabilidade do provedor: timeout para carregar o jogo."
                diag["erro"] = "PlaywrightTimeout (mesmo após reload)"
                tentativas.append({"n": len(tentativas) + 1, "acao": "reload_timeout", "resultado": "timeout"})
                logger.error("[%s] Timeout confirmado após reload — OFF", slug)
                err_path = evidence_dir / f"ERR_{sanitize_filename(slug.replace('/', '_'))}.png"
                try:
                    await page.screenshot(path=str(err_path), full_page=False)
                except Exception:
                    pass
        except Exception as retry_err:
            result["motivo"] = "Instabilidade do provedor: timeout para carregar o jogo."
            diag["erro"] = f"PlaywrightTimeout + reload falhou: {retry_err}"
            tentativas.append({"n": len(tentativas) + 1, "acao": "reload_timeout", "resultado": "erro", "detalhe": str(retry_err)[:200]})
            logger.error("[%s] Reload também falhou: %s", slug, retry_err)
            err_path = evidence_dir / f"ERR_{sanitize_filename(slug.replace('/', '_'))}.png"
            try:
                await page.screenshot(path=str(err_path), full_page=False)
            except Exception:
                pass
    except Exception as e:
        result["motivo"] = f"Erro ao processar jogo: {e}"
        diag["erro"] = str(e)
        tentativas.append({"n": len(tentativas) + 1, "acao": "carga", "resultado": "erro", "detalhe": str(e)[:200]})
        logger.error("Erro em %s: %s", slug, e)
        err_path = evidence_dir / f"ERR_{sanitize_filename(slug.replace('/', '_'))}.png"
        try:
            await page.screenshot(path=str(err_path), full_page=False)
        except Exception:
            pass
    finally:
        result["_diag"] = diag
        result["_tentativas"] = tentativas
        if page_urls is not None:
            page_urls.pop(id(page), None)
        await page.close()

    return result


async def process_batch(
    context: BrowserContext,
    batch: list[str],
    evidence_dir: Path,
    email: str,
    senha: str,
) -> list[dict]:
    """Processa um lote de slugs em paralelo (asyncio.gather) com timeout por jogo."""
    relogin_lock = asyncio.Lock()
    page_urls: dict = {}

    async def _capture_with_timeout(slug: str) -> dict:
        try:
            return await asyncio.wait_for(
                capture_game(context, slug, evidence_dir, email, senha, relogin_lock, page_urls),
                timeout=PER_GAME_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.warning("[%s] TIMEOUT global (%ds). Verificando se iframe carregou...", slug, PER_GAME_TIMEOUT)
            # Antes de marcar OFF, verificar se o iframe existe na página
            try:
                pages = context.pages
                game_page = None
                for p in pages:
                    if slug.lower() in p.url.lower():
                        game_page = p
                        break
                if game_page:
                    for sel in IFRAME_SELECTORS:
                        try:
                            loc = game_page.locator(sel).first
                            if await loc.count() > 0:
                                # Iframe existe — verificar conteúdo
                                has_error = False
                                for f in game_page.frames:
                                    if f == game_page.main_frame or not f.url or f.url == "about:blank":
                                        continue
                                    try:
                                        txt = (await f.evaluate("() => document.body ? document.body.innerText : ''") or "")[:500]
                                        txt_lower = txt.lower()
                                        if any(kw in txt_lower for kw in ["403 error", "g1006", "carregamento falhou", "loading failed", "não encontrado", "not found"]):
                                            has_error = True
                                            break
                                    except Exception:
                                        continue
                                if not has_error:
                                    logger.info("[%s] Iframe detectado após timeout global — jogo ON.", slug)
                                    evidence_path = Path("game_evidence") / f"{slug.replace('/', '_')}_{BRAND}.png"
                                    try:
                                        await loc.screenshot(path=str(evidence_path))
                                    except Exception:
                                        pass
                                    return {
                                        "slug": slug,
                                        "brand": BRAND,
                                        "status": "on",
                                        "motivo": "Jogo carregado (detectado após timeout global).",
                                        "_diag": {"erro": f"PER_GAME_TIMEOUT ({PER_GAME_TIMEOUT}s) — recuperado"},
                                        "_tentativas": [{"n": 1, "acao": "timeout_global", "resultado": "ok_recuperado"}],
                                    }
                                break
                        except Exception:
                            continue
                    try:
                        await game_page.close()
                    except Exception:
                        pass
            except Exception as chk_err:
                logger.debug("[%s] Erro ao verificar iframe pós-timeout: %s", slug, chk_err)
            logger.error("[%s] TIMEOUT confirmado — jogo OFF.", slug)
            # Screenshot da página no estado atual
            if game_page:
                err_path = evidence_dir / f"ERR_{slug.replace('/', '_')}.png"
                try:
                    await game_page.screenshot(path=str(err_path), full_page=False)
                except Exception:
                    pass
            return {
                "slug": slug,
                "brand": BRAND,
                "status": "off",
                "motivo": "Instabilidade do provedor: timeout para carregar o jogo.",
                "_diag": {"erro": f"PER_GAME_TIMEOUT ({PER_GAME_TIMEOUT}s)"},
                "_tentativas": [{"n": 1, "acao": "carga", "resultado": "timeout_global", "detalhe": f">{PER_GAME_TIMEOUT}s"}],
            }

    tasks = [_capture_with_timeout(slug) for slug in batch]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    processed = []
    for slug, r in zip(batch, results):
        if isinstance(r, Exception):
            logger.error("Erro fatal ao processar '%s': %s", slug, r)
            processed.append({
                "slug": slug,
                "brand": BRAND,
                "status": "off",
                "motivo": f"Erro fatal: {r}",
                "_diag": {"erro": str(r)[:200]},
                "_tentativas": [{"n": 1, "acao": "carga", "resultado": "erro_fatal", "detalhe": str(r)[:200]}],
            })
        else:
            processed.append(r)
    return processed
