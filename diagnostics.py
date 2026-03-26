"""
Diagnóstico de frames — coleta dados estruturados dos iframes do jogo.
"""

import asyncio

from playwright.async_api import Page

from config import logger
from utils import trim_url


# ─── Keywords de detecção ──────────────────────────────────────────────────────
MAINTENANCE_KEYWORDS = [
    "manutenção", "maintenance", "em manutenção",
    "under maintenance", "temporarily unavailable",
    "indisponível", "out of service", "fora de serviço",
]

ERROR_KEYWORDS = [
    "something went wrong", "algo deu errado",
    "alguma coisa deu errado", "deu errado",
    "failed to load", "falha ao carregar",
    "connection error", "erro de conexão",
    "internal server error",
    "game not found", "jogo não encontrado",
    "not available", "não disponível",
    "página não encontrada", "page not found",
    # CloudFront / CDN geo-block
    "403 error", "403 forbidden",
    "access denied", "acesso negado",
    "block access from your country",
    "request could not be satisfied",
    "cloudfront",
    # Erros de carregamento do provedor
    "o carregamento falhou", "loading failed",
    "transfer failed", "transferência falhou",
    "código de erro", "error code",
    "g1006",
    "could not connect", "connection refused",
    "service unavailable", "serviço indisponível",
    "502 bad gateway", "503 service",
    "504 gateway", "timeout error",
    # Erros genéricos de provedores — só considerar se o frame NÃO tem canvas
    # (ex: banana/magi-kat exibe "Ops...Reload Page" transitoriamente durante o load
    # mas renderiza normalmente via WebGL depois)
    "ops...", "reload page",
]

# Keywords que só indicam erro quando o frame não tem canvas (WebGL) ativo
_SOFT_ERROR_KEYWORDS = {"ops...", "reload page"}

SESSION_KEYWORDS = [
    "logged in from another device",
    "conectou de outro dispositivo", "conexão perdida",
]

EXCLUDED_DOMAINS = [
    "doubleclick", "criteo", "hotjar", "facebook",
    "google", "tiktok", "taboola",
    "gravity-service",
]

SUSPICIOUS_KEYWORDS = [
    "manutenção", "maintenance", "unavailable", "indisponível",
    "não encontrado", "not found", "404", "erro", "error",
    "offline", "closed", "fechado",
    "403", "access denied", "block access",
    "carregamento falhou", "loading failed",
]


async def collect_diagnostics(page: Page, diag: dict) -> None:
    """
    Coleta dados estruturados dos iframes do jogo.
    Preenche o dicionário `diag` in-place.
    Dividido internamente em fase rápida (frames) e fase lenta (textos suspeitos).
    """
    diag["url_final"] = page.url

    game_iframe_el = page.locator("iframe#gameIframe, iframe[src*='game']").first
    if await game_iframe_el.count() > 0:
        diag["game_iframe_found"] = True

        valid_frames = []
        for f in page.frames:
            if f == page.main_frame:
                continue
            if not f.url or f.url == "about:blank":
                continue
            if any(d in f.url for d in EXCLUDED_DOMAINS):
                continue
            valid_frames.append(f)

        all_frames_content = []
        for idx, frame in enumerate(valid_frames):
            frame_data = {
                "nivel": idx + 1,
                "frame_url": trim_url(frame.url),
                "text": "",
                "canvas_count": 0,
                "title": "",
            }
            try:
                frame_data["text"] = (await frame.evaluate(
                    "() => document.body ? document.body.innerText : ''"
                ) or "")[:500]
            except Exception as e:
                frame_data["text"] = f"ERRO: {e}"

            try:
                frame_data["title"] = await frame.evaluate("() => document.title || ''")
            except Exception:
                pass

            try:
                frame_data["canvas_count"] = await frame.evaluate(
                    "() => document.querySelectorAll('canvas').length"
                )
            except Exception:
                pass

            all_frames_content.append(frame_data)
            # Salvar incrementalmente para sobreviver a timeout
            diag["game_iframe_frames"] = all_frames_content

        if all_frames_content:
            diag["game_iframe_content"] = all_frames_content[-1]

    # Marcar fase rápida como concluída
    diag["_fast_phase_done"] = True

    # ─── Fase lenta: textos suspeitos na página principal ──────────────────
    try:
        body_text = await page.evaluate("() => document.body ? document.body.innerText : ''")
        for keyword in SUSPICIOUS_KEYWORDS:
            if keyword.lower() in (body_text or "").lower():
                ki = body_text.lower().index(keyword.lower())
                start = max(0, ki - 50)
                end = min(len(body_text), ki + 80)
                diag["textos_suspeitos"].append(body_text[start:end].replace('\n', ' '))
    except Exception:
        pass


async def run_diagnostics(page: Page, diag: dict, slug: str) -> bool:
    """
    Executa collect_diagnostics em 2 fases:
      - Fase rápida (5s): coleta frames do jogo (essencial para decidir on/off/warning)
      - Fase lenta (+10s): coleta textos suspeitos da página principal

    Se a fase rápida trava, retorna True (timeout) com o que foi coletado.
    Se a fase rápida completa mas a lenta trava, retorna False (dados essenciais OK).
    """
    try:
        await asyncio.wait_for(collect_diagnostics(page, diag), timeout=5)
        return False
    except asyncio.TimeoutError:
        if diag.get("_fast_phase_done"):
            # Fase rápida OK, fase lenta travou — dados essenciais disponíveis
            logger.info("[%s] Fase lenta do diagnóstico travou (textos suspeitos). Frames OK.", slug)
            return False
        else:
            # Fase rápida travou — tentar continuar com fase lenta em timeout estendido
            logger.warning("[%s] Fase rápida do diagnóstico travou (5s). Estendendo +10s...", slug)
            try:
                await asyncio.wait_for(collect_diagnostics(page, diag), timeout=10)
                return False
            except asyncio.TimeoutError:
                diag["erro"] = "Diagnóstico travou (timeout 15s) — provável jogo WebGL pesado"
                logger.warning("[%s] Diagnóstico travou completamente (15s total).", slug)
                return True
            except Exception as e:
                diag["erro"] = str(e)
                return True
    except Exception as e:
        diag["erro"] = str(e)
        return False


def check_session_expired(all_frames_content: list[dict]) -> bool:
    """Verifica se algum frame indica sessão expirada."""
    for fc in all_frames_content:
        iframe_text = (fc.get("text") or "").lower()
        iframe_title = (fc.get("title") or "").lower()
        combined = f"{iframe_text} {iframe_title}"
        for kw in SESSION_KEYWORDS:
            if kw in combined:
                return True
    return False


def check_iframe_off_reason(all_frames_content: list[dict]) -> str | None:
    """Verifica se algum frame indica manutenção ou erro. Retorna motivo ou None."""
    for fc in all_frames_content:
        iframe_text = (fc.get("text") or "").lower()
        iframe_title = (fc.get("title") or "").lower()
        combined = f"{iframe_text} {iframe_title}"
        iframe_text_clean = (fc.get("text") or "").strip()[:500]
        frame_url = fc.get("frame_url", "")
        has_canvas = fc.get("canvas_count", 0) > 0

        for kw in MAINTENANCE_KEYWORDS:
            if kw in combined:
                return f"Jogo em manutenção — frame: '{frame_url[:100]}' — texto: '{iframe_text_clean}'"

        for kw in ERROR_KEYWORDS:
            if kw in combined:
                # Keywords "soft" (ops..., reload page) são ignorados quando o
                # frame já possui canvas WebGL renderizando — texto residual.
                if kw in _SOFT_ERROR_KEYWORDS and has_canvas:
                    continue
                return f"Jogo com problema — frame: '{frame_url[:100]}' — texto: '{iframe_text_clean}'"

    return None


_403_INDICATORS = [
    "403 error", "403 forbidden",
    "block access from your country", "cloudfront",
    # Amusnet / outros provedores com geo-block por legislação local
    "local legislation",
    "not available in your country",
    "due to local legislation",
]


def is_403_error(motivo: str) -> bool:
    """Retorna True se o motivo indica um erro 403 / geo-block."""
    motivo_lower = (motivo or "").lower()
    return any(kw in motivo_lower for kw in _403_INDICATORS)
