"""
Robô de Monitoramento de Jogos - 7K Bet
Orquestrador: lança Chrome, faz login, processa lotes e gera relatórios.
Roda em loop infinito — NUNCA deve morrer.
"""

import os
import asyncio
import subprocess
import time
import urllib.request
from datetime import datetime
from pathlib import Path

import psutil
from playwright.async_api import async_playwright

from config import (
    ACCESS_TOKEN, BRAND, CDP_PORT, CHROME_PATH, CONCURRENT_TABS, EMAIL, SENHA,
    EVIDENCE_DIR, INPUT_FILE, IS_PROD, PROFILE_DIR, logger,
)
from utils import load_games, build_diverse_batches
from auth import perform_login, dismiss_popups
from capture import process_batch
from report import generate_reports, print_summary
from clients.supabase_client import send_results
from clients.health_check import HealthCheck

# Intervalo (segundos) entre ciclos de monitoramento
CYCLE_INTERVAL = 30
AGENT_NAME = "Monitor 7K-jogos"


# ─── Gerenciamento de processos Chrome ─────────────────────────────────────────

def kill_chrome_processes() -> None:
    """Mata todos os processos Chrome/Google para liberar memória."""
    cmds = (
        [["pkill", "-9", "-f", "chrome"], ["pkill", "-9", "-f", "google"]]
        if IS_PROD
        else [["taskkill", "/F", "/IM", "chrome.exe"], ["taskkill", "/F", "/IM", "GoogleUpdate.exe"]]
    )
    for cmd in cmds:
        try:
            subprocess.run(cmd, capture_output=True, timeout=10)
        except Exception:
            pass
    logger.info("Limpeza de processos Chrome concluída.")


# ─── Ciclo único de monitoramento ─────────────────────────────────────────────

async def run_cycle(email: str, senha: str, slugs: list[str], hc: HealthCheck) -> None:
    """Executa um ciclo completo de monitoramento. Não propaga exceções."""

    evidence_dir = Path(EVIDENCE_DIR)
    evidence_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    start_time = time.monotonic()
    results: list[dict] = []
    had_error = False  # rastreia se houve qualquer erro no ciclo

    # Monitoramento de recursos
    process = psutil.Process()
    mem_samples: list[float] = []
    cpu_samples: list[float] = []

    def sample_resources():
        try:
            mem_mb = process.memory_info().rss / (1024 * 1024)
            children = process.children(recursive=True)
            for child in children:
                try:
                    mem_mb += child.memory_info().rss / (1024 * 1024)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            mem_samples.append(round(mem_mb, 1))
            cpu_pct = process.cpu_percent(interval=None)
            for child in children:
                try:
                    cpu_pct += child.cpu_percent(interval=None)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            cpu_samples.append(round(cpu_pct, 1))
        except Exception:
            pass

    # ─── Garantir pasta do perfil ───
    profile_abs = str(Path(PROFILE_DIR).resolve())
    Path(profile_abs).mkdir(exist_ok=True)

    # ─── Health check: início ───
    hc.update("on", "Iniciou o processamento")

    # ─── Encerrar Chrome existente (início do ciclo) ───
    kill_chrome_processes()
    await asyncio.sleep(3)

    chrome_proc = None
    try:
        # ─── Lançar Chrome REAL via subprocess ───
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
        cdp_ready = False
        for attempt in range(15):
            await asyncio.sleep(1)
            try:
                urllib.request.urlopen(cdp_url, timeout=2)
                logger.info("CDP pronto na tentativa %d.", attempt + 1)
                cdp_ready = True
                break
            except Exception:
                pass

        if not cdp_ready:
            logger.error("Chrome não respondeu no CDP após 15s. Abortando ciclo.")
            hc.error("Iniciou o processamento", "Chrome não respondeu no CDP após 15s.")
            return

        async with async_playwright() as p:
            # Conectar ao Chrome via CDP
            logger.info("Conectando ao Chrome via CDP (localhost:%d)...", CDP_PORT)
            browser = await p.chromium.connect_over_cdp(f"http://localhost:{CDP_PORT}")
            logger.info("Conectado! Contextos: %d", len(browser.contexts))
            context = browser.contexts[0] if browser.contexts else await browser.new_context()

            async def _add_casinobot_header(route):
                headers = {**route.request.headers, "casinobot": "BB2017F6-49A1-4C56-86F3-51F6A5F4EEEF"}
                await route.continue_(headers=headers)

            async def _add_access_header(route):
                headers = {**route.request.headers, "access": ACCESS_TOKEN}
                await route.continue_(headers=headers)

            await context.route("**/*7k.bet.br/**", _add_casinobot_header)
            await context.route("**/*", _add_access_header)
            logger.info("Header 'casinobot' → 7k.bet.br | Header 'access' → todas as requisições (iframes/CDN).")

            # Página de login
            main_page = await context.new_page()
            logger.info("Nova aba criada para login.")
            hc.update("on", "Realizando login")
            login_ok = await perform_login(main_page, email, senha)

            if not login_ok:
                logger.error("Falha no login. Abortando ciclo.")
                hc.error("Realizando login", "Falha no login — não foi possível autenticar.")
                try:
                    await browser.close()
                except Exception:
                    pass
                return

            hc.update("on", "Login realizado com sucesso")

            await dismiss_popups(main_page)
            await main_page.goto("about:blank")

            # Inicializar CPU baseline
            process.cpu_percent(interval=None)
            for child in process.children(recursive=True):
                try:
                    child.cpu_percent(interval=None)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            # ─── Processar jogos em lotes (1 jogo por provedora por lote) ───
            batches = build_diverse_batches(slugs, CONCURRENT_TABS)
            total_batches = len(batches)
            for batch_num, batch in enumerate(batches, 1):
                logger.info(
                    "Processando lote %d/%d (%d jogos)...",
                    batch_num, total_batches, len(batch),
                )
                hc.update("on", f"Realizando scraping lote {batch_num} de {total_batches}")

                try:
                    sample_resources()
                    batch_results = await process_batch(
                        context, batch, evidence_dir, email, senha
                    )
                    results.extend(batch_results)
                    sample_resources()
                except Exception as exc:
                    logger.error("Erro no lote %d/%d (scraping): %s", batch_num, total_batches, exc)
                    hc.error(f"Realizando scraping lote {batch_num} de {total_batches}", str(exc))
                    had_error = True
                    for slug in batch:
                        results.append({
                            "slug": slug,
                            "brand": BRAND,
                            "status": "off",
                            "motivo": f"Erro no lote: {exc}",
                            "_diag": {"erro": str(exc)[:200]},
                            "_tentativas": [],
                        })
                    continue

                # Enviar resultados deste lote ao Supabase
                clean_batch = []
                for r in batch_results:
                    clean = {k: v for k, v in r.items() if not k.startswith("_")}
                    clean_batch.append(clean)
                try:
                    send_results(clean_batch, BRAND)
                    logger.info("Lote %d/%d enviado ao Supabase (%d jogos).", batch_num, total_batches, len(clean_batch))
                except Exception as e:
                    logger.error("Erro ao enviar lote %d ao Supabase: %s", batch_num, e)

                if batch_num < total_batches:
                    await asyncio.sleep(2)

            try:
                await browser.close()
            except Exception:
                pass

    except Exception as exc:
        logger.error("Erro crítico no ciclo de scraping: %s", exc)
        hc.error("Erro crítico no scraping", str(exc))
        had_error = True
    finally:
        # Sempre terminar o processo Chrome e matar processos residuais
        if chrome_proc is not None:
            try:
                chrome_proc.terminate()
            except Exception:
                pass
        kill_chrome_processes()

    # Se não capturou nenhum resultado, não há sentido continuar
    if not results:
        logger.error("Nenhum resultado capturado — pulando relatórios e IA.")
        if not had_error:
            hc.error("Scraping", "Nenhum resultado capturado no ciclo.")
        return

    # ─── Relatórios (fora do bloco do Chrome — já encerrado) ───
    elapsed = time.monotonic() - start_time
    mins, secs = divmod(int(elapsed), 60)
    tempo_decorrido = f"{mins:02d}:{secs:02d}"

    recursos = {}
    if mem_samples:
        recursos["mem_avg_mb"] = round(sum(mem_samples) / len(mem_samples), 1)
        recursos["mem_max_mb"] = round(max(mem_samples), 1)
    if cpu_samples:
        recursos["cpu_avg_pct"] = round(sum(cpu_samples) / len(cpu_samples), 1)
        recursos["cpu_max_pct"] = round(max(cpu_samples), 1)
    recursos["amostras"] = len(mem_samples)

    try:
        generate_reports(results, evidence_dir, timestamp, tempo_decorrido, recursos)
    except Exception as exc:
        logger.error("Erro ao gerar relatórios (disco/IO): %s", exc)
        hc.error("Gerando relatórios", str(exc))
        had_error = True

    # ─── Processamento IA ───
    hc.update("on", "Analisando relatório")
    relatorio_diag = evidence_dir / "relatorio_diagnostico.json"
    try:
        from clients.llm_service import processar_relatorio, PromptError, ModelError, OutputError
        import json

        resultado_ia = processar_relatorio(
            caminho_relatorio=str(relatorio_diag),
            session_id=f"monit-{timestamp}",
            tags=["monitoramento-jogos", BRAND, "production" if IS_PROD else "staging"],
        )

        output_ia_path = evidence_dir / "resultado_ia.json"
        with open(output_ia_path, "w", encoding="utf-8") as f:
            json.dump(resultado_ia.jogos, f, ensure_ascii=False, indent=2)

        counts = {"on": 0, "off": 0, "warning": 0}
        for j in resultado_ia.jogos:
            s = j.get("status", "?")
            counts[s] = counts.get(s, 0) + 1

        logger.info(
            "IA concluída: ON=%d | OFF=%d | WARNING=%d | $%.6f | %.1fs",
            counts["on"], counts["off"], counts["warning"],
            resultado_ia.cost_usd, resultado_ia.latency,
        )

        from clients.supabase_client import send_ia_results
        try:
            send_ia_results(resultado_ia.jogos, BRAND)
        except Exception as exc:
            logger.error("Erro ao enviar resultados de IA ao Supabase: %s", exc)

        # ─── Comparação Robô vs IA ───
        try:
            from comparison import gerar_relatorio_comparacao
            from clients.supabase_client import send_ia_feedback
            todos_jogos = gerar_relatorio_comparacao(results, resultado_ia.jogos, evidence_dir)
            try:
                send_ia_feedback(todos_jogos)
            except Exception as exc:
                logger.error("Erro ao enviar feedback de IA ao Supabase: %s", exc)
        except Exception as exc:
            logger.error("Erro na comparação Robô vs IA: %s", exc)
    except (PromptError, ModelError, OutputError) as exc:
        logger.error("Falha no processamento de IA: %s", exc)
        hc.error("Analisando relatório", str(exc))
        had_error = True
    except Exception as exc:
        logger.error("Erro inesperado no pipeline de IA (não-crítico): %s", exc)
        hc.error("Analisando relatório", str(exc))
        had_error = True

    # Exibir resumo
    try:
        print_summary(results)
    except Exception:
        pass

    # ─── Health check: conclusão ───
    if not had_error:
        hc.success("Processo realizado com sucesso")


# ─── Loop infinito ─────────────────────────────────────────────────────────────

async def main():
    """Loop infinito de monitoramento. NUNCA deve morrer."""
    email = EMAIL
    senha = SENHA

    if not email or not senha or email == "seu_email@exemplo.com":
        logger.critical("Credenciais não configuradas! Edite EMAIL e SENHA no config.py.")
        return

    if not Path(INPUT_FILE).exists():
        logger.critical("Arquivo %s não encontrado!", INPUT_FILE)
        return

    slugs = load_games(INPUT_FILE)
    logger.info("Total de jogos a verificar: %d", len(slugs))

    hc = HealthCheck(AGENT_NAME)

    single_run = os.environ.get("SINGLE_RUN", "").strip() == "1"

    ciclo = 0
    while True:
        ciclo += 1

        # Consultar status atual antes de iniciar
        hc.get_status()
        logger.info("=" * 60)
        logger.info("INÍCIO DO CICLO #%d", ciclo)
        logger.info("=" * 60)

        try:
            await run_cycle(email, senha, slugs, hc)
        except Exception as exc:
            logger.error("Exceção não tratada no ciclo #%d: %s", ciclo, exc)
            hc.error("Erro não tratado", str(exc))
            # Garantir limpeza mesmo em caso de erro catastrófico
            kill_chrome_processes()

        if single_run:
            logger.info("SINGLE_RUN=1 — encerrando após ciclo #%d.", ciclo)
            break

        logger.info("Ciclo #%d finalizado. Aguardando %ds para o próximo...", ciclo, CYCLE_INTERVAL)
        await asyncio.sleep(CYCLE_INTERVAL)


if __name__ == "__main__":
    asyncio.run(main())
