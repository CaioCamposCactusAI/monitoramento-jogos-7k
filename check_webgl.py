"""
Diagnóstico: verifica se o Chrome no servidor suporta WebGL.
Testa múltiplas combinações de flags GL com o Playwright Chromium.
Executa no servidor com: python check_webgl.py
"""
import asyncio
import glob
import subprocess
import os
import urllib.request

from config import CHROME_PATH, IS_PROD, CDP_PORT


# Combinações de flags GL para testar
GL_FLAG_COMBOS = [
    ("swiftshader", ["--use-gl=swiftshader", "--enable-webgl"]),
    ("angle-swiftshader", ["--use-gl=angle", "--use-angle=swiftshader-webgl"]),
    ("angle-gles", ["--use-gl=angle", "--use-angle=gles"]),
    ("unsafe-swiftshader", ["--enable-unsafe-swiftshader"]),
    ("egl", ["--use-gl=egl"]),
    ("swiftshader+override", ["--use-gl=swiftshader", "--enable-webgl", "--ignore-gpu-blocklist", "--enable-gpu-rasterization"]),
    ("angle+override", ["--use-gl=angle", "--use-angle=swiftshader-webgl", "--ignore-gpu-blocklist"]),
    ("no-flags", []),
    ("headless-off+swiftshader", ["--use-gl=swiftshader", "--enable-webgl", "NO_HEADLESS"]),
    ("headless-off+angle", ["--use-gl=angle", "--use-angle=swiftshader-webgl", "NO_HEADLESS"]),
]


async def test_webgl_combo(chrome_path: str, combo_name: str, gl_flags: list, port: int) -> bool:
    """Testa uma combinação de flags GL. Retorna True se WebGL funciona."""
    use_headless = "NO_HEADLESS" not in gl_flags
    clean_flags = [f for f in gl_flags if f != "NO_HEADLESS"]

    chrome_args = [
        chrome_path,
        f"--remote-debugging-port={port}",
        f"--user-data-dir=/tmp/webgl_test_{combo_name}",
        "--no-first-run",
        "--no-default-browser-check",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--window-size=800,600",
    ]
    if use_headless:
        chrome_args.append("--headless=new")
    chrome_args.extend(clean_flags)

    mode = "headless" if use_headless else "headed (xvfb)"
    print(f"\n  [{combo_name}] ({mode}) flags: {clean_flags or '(nenhuma)'}")

    proc = subprocess.Popen(chrome_args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    cdp_ready = False
    for attempt in range(8):
        await asyncio.sleep(1)
        try:
            urllib.request.urlopen(f"http://localhost:{port}/json/version", timeout=2)
            cdp_ready = True
            break
        except Exception:
            pass

    if not cdp_ready:
        stderr = proc.stderr.read().decode()[-300:] if proc.stderr else ""
        print(f"    CDP falhou. stderr: {stderr[:200]}")
        proc.terminate()
        proc.wait()
        return False

    from playwright.async_api import async_playwright
    webgl_ok = False
    try:
        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(f"http://localhost:{port}")
            ctx = browser.contexts[0] if browser.contexts else await browser.new_context()
            page = await ctx.new_page()

            # chrome://gpu - extrair info GL
            await page.goto("chrome://gpu", wait_until="domcontentloaded", timeout=10_000)
            await page.wait_for_timeout(2_000)
            body = await page.evaluate("() => document.body ? document.body.innerText : ''")
            gpu_lines = []
            for line in body.split('\n'):
                ll = line.lower()
                if any(kw in ll for kw in ["webgl", "opengl", "swiftshader", "gl_renderer", "gl_vendor",
                                             "hardware", "disabled", "software", "accelerat"]):
                    gpu_lines.append(line.strip())
            if gpu_lines:
                for gl in gpu_lines[:5]:
                    print(f"    gpu: {gl}")
            else:
                print(f"    gpu: (nenhuma linha relevante)")

            # Testar WebGL
            await page.goto("about:blank")
            result = await page.evaluate("""() => {
                const canvas = document.createElement('canvas');
                const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
                if (!gl) return { webgl: false, webgl2: false };
                const debugInfo = gl.getExtension('WEBGL_debug_renderer_info');
                const canvas2 = document.createElement('canvas');
                const gl2 = canvas2.getContext('webgl2');
                return {
                    webgl: true,
                    webgl2: !!gl2,
                    vendor: debugInfo ? gl.getParameter(debugInfo.UNMASKED_VENDOR_WEBGL) : 'N/A',
                    renderer: debugInfo ? gl.getParameter(debugInfo.UNMASKED_RENDERER_WEBGL) : 'N/A',
                };
            }""")

            webgl_ok = result.get("webgl", False)
            status = "✓" if webgl_ok else "✗"
            print(f"    {status} WebGL={result.get('webgl')}  WebGL2={result.get('webgl2')}", end="")
            if webgl_ok:
                print(f"  renderer={result.get('renderer')}")
            else:
                print()

            await browser.close()
    except Exception as e:
        print(f"    Erro: {e}")
    finally:
        proc.terminate()
        proc.wait()

    return webgl_ok


async def main():
    print(f"CHROME_PATH: {CHROME_PATH}")
    print(f"IS_PROD: {IS_PROD}")

    if not os.path.exists(CHROME_PATH):
        print(f"ERRO: Chrome não encontrado em {CHROME_PATH}")
        return

    try:
        ver = subprocess.check_output([CHROME_PATH, "--version"], stderr=subprocess.STDOUT, timeout=5)
        print(f"Versão: {ver.decode().strip()}")
    except Exception as e:
        print(f"Versão: erro ({e})")

    # Listar SwiftShader libs
    chrome_dir = os.path.dirname(CHROME_PATH)
    print(f"Dir: {chrome_dir}")
    for root, dirs, files in os.walk(chrome_dir):
        for f in files:
            fl = f.lower()
            if any(kw in fl for kw in ["swiftshader", "egl", "gles", "vulkan"]):
                full = os.path.join(root, f)
                print(f"  {os.path.relpath(full, chrome_dir)} ({os.path.getsize(full):,} bytes)")

    # Testar todas as combinações de flags
    print(f"\n{'='*60}")
    print(f"  TESTANDO {len(GL_FLAG_COMBOS)} combinações de flags GL")
    print(f"{'='*60}")

    working = []
    port = CDP_PORT + 1
    for combo_name, gl_flags in GL_FLAG_COMBOS:
        ok = await test_webgl_combo(CHROME_PATH, combo_name, gl_flags, port)
        if ok:
            working.append((combo_name, gl_flags))
        port += 1

    # Resumo
    print(f"\n{'='*60}")
    print(f"  RESULTADO")
    print(f"{'='*60}")
    if working:
        print(f"  ✓ {len(working)} combinação(ões) com WebGL funcionando:")
        for name, flags in working:
            clean = [f for f in flags if f != "NO_HEADLESS"]
            print(f"    [{name}] {clean}")
        best = working[0]
        print(f"\n  Recomendação: usar [{best[0]}]")
    else:
        print("  ✗ NENHUMA combinação habilitou WebGL!")
        print("  Possíveis causas:")
        print("    - ARM64 (Graviton) pode não suportar SwiftShader WebGL")
        print("    - Falta xvfb para modo headed (instale: apt install xvfb)")
        print("    - Faltam libs: playwright install-deps")


asyncio.run(main())
