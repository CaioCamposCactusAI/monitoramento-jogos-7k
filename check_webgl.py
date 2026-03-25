"""
Diagnóstico: verifica se o Chrome no servidor suporta WebGL.
Executa no servidor com: python check_webgl.py
"""
import asyncio
import glob
import subprocess
import os
import urllib.request

from config import CHROME_PATH, IS_PROD, CDP_PORT


def find_all_chrome_binaries():
    """Lista todos os Chrome/Chromium disponíveis no sistema."""
    candidates = []
    # Playwright
    pw_paths = sorted(
        glob.glob(os.path.expanduser("~/.cache/ms-playwright/chromium-*/chrome-linux/chrome")),
        reverse=True,
    )
    for p in pw_paths:
        candidates.append(("playwright", p))
    # Sistema
    for path in ["/usr/bin/chromium-browser", "/usr/bin/chromium", "/usr/bin/google-chrome", "/usr/bin/google-chrome-stable"]:
        if os.path.exists(path):
            candidates.append(("system", path))
    # Snap real binary
    snap_paths = glob.glob("/snap/chromium/*/usr/lib/chromium-browser/chrome")
    for p in sorted(snap_paths, reverse=True):
        candidates.append(("snap-direct", p))
    return candidates


async def test_webgl_with_binary(chrome_path: str, label: str, port: int):
    """Tenta lançar Chrome e testar WebGL."""
    print(f"\n{'='*60}")
    print(f"  Testando: {label} — {chrome_path}")
    print(f"{'='*60}")

    if not os.path.exists(chrome_path):
        print(f"  ERRO: binário não encontrado")
        return

    # Versão
    try:
        ver = subprocess.check_output([chrome_path, "--version"], stderr=subprocess.STDOUT, timeout=5)
        print(f"  Versão: {ver.decode().strip()}")
    except Exception as e:
        print(f"  Versão: erro ({e})")

    # Listar libs SwiftShader
    chrome_dir = os.path.dirname(chrome_path)
    print(f"  Dir: {chrome_dir}")
    sw_found = False
    if chrome_dir != "/usr/bin":
        for root, dirs, files in os.walk(chrome_dir):
            for f in files:
                fl = f.lower()
                if any(kw in fl for kw in ["swiftshader", "egl", "gles", "vulkan", "libgl"]):
                    full = os.path.join(root, f)
                    size = os.path.getsize(full)
                    print(f"    {os.path.relpath(full, chrome_dir)} ({size:,} bytes)")
                    sw_found = True
    if not sw_found:
        print("    Nenhuma lib SwiftShader/EGL encontrada no diretório!")

    # Lançar Chrome
    chrome_args = [
        chrome_path,
        f"--remote-debugging-port={port}",
        "--user-data-dir=/tmp/webgl_test_profile",
        "--no-first-run",
        "--no-default-browser-check",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--use-gl=swiftshader",
        "--enable-webgl",
        "--window-size=800,600",
        "--headless=new",
    ]
    print(f"  Lançando na porta {port}...")
    proc = subprocess.Popen(chrome_args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    # Aguardar CDP
    cdp_ready = False
    for attempt in range(10):
        await asyncio.sleep(1)
        try:
            urllib.request.urlopen(f"http://localhost:{port}/json/version", timeout=2)
            cdp_ready = True
            print(f"  CDP pronto (tentativa {attempt + 1})")
            break
        except Exception:
            pass

    if not cdp_ready:
        print(f"  ERRO: CDP não respondeu após 10s")
        stderr = proc.stderr.read().decode()[-500:] if proc.stderr else ""
        if stderr:
            print(f"  stderr: {stderr}")
        proc.terminate()
        proc.wait()
        return

    from playwright.async_api import async_playwright
    try:
        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(f"http://localhost:{port}")
            ctx = browser.contexts[0] if browser.contexts else await browser.new_context()
            page = await ctx.new_page()

            # Test 1: chrome://gpu
            print("\n=== chrome://gpu ===")
            await page.goto("chrome://gpu", wait_until="domcontentloaded", timeout=10_000)
            await page.wait_for_timeout(2_000)
            body = await page.evaluate("() => document.body ? document.body.innerText : ''")
            # Extrair linhas relevantes
            for line in body.split('\n'):
                ll = line.lower()
                if any(kw in ll for kw in ["webgl", "opengl", "swiftshader", "gl_renderer", "gl_vendor", "hardware"]):
                    print(f"  {line.strip()}")

            # Test 2: WebGL via JavaScript
            print("\n=== WebGL JavaScript Test ===")
            await page.goto("about:blank")
            webgl_info = await page.evaluate("""() => {
                const canvas = document.createElement('canvas');
                const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
                if (!gl) return { supported: false };
                const debugInfo = gl.getExtension('WEBGL_debug_renderer_info');
                return {
                    supported: true,
                    vendor: debugInfo ? gl.getParameter(debugInfo.UNMASKED_VENDOR_WEBGL) : 'N/A',
                    renderer: debugInfo ? gl.getParameter(debugInfo.UNMASKED_RENDERER_WEBGL) : 'N/A',
                    version: gl.getParameter(gl.VERSION),
                    shadingVersion: gl.getParameter(gl.SHADING_LANGUAGE_VERSION),
                    maxTextureSize: gl.getParameter(gl.MAX_TEXTURE_SIZE),
                };
            }""")
            print(f"  WebGL supported: {webgl_info.get('supported')}")
            if webgl_info.get('supported'):
                print(f"  Vendor: {webgl_info.get('vendor')}")
                print(f"  Renderer: {webgl_info.get('renderer')}")
                print(f"  Version: {webgl_info.get('version')}")
                print(f"  GLSL: {webgl_info.get('shadingVersion')}")
                print(f"  Max texture: {webgl_info.get('maxTextureSize')}")

            # Test 3: WebGL2
            webgl2_info = await page.evaluate("""() => {
                const canvas = document.createElement('canvas');
                const gl = canvas.getContext('webgl2');
                if (!gl) return { supported: false };
                return { supported: true, version: gl.getParameter(gl.VERSION) };
            }""")
            print(f"  WebGL2 supported: {webgl2_info.get('supported')}")

            await browser.close()
    except Exception as e:
        print(f"  Erro ao testar: {e}")
    finally:
        proc.terminate()
        proc.wait()


async def main():
    print(f"CONFIG CHROME_PATH: {CHROME_PATH}")
    print(f"IS_PROD: {IS_PROD}")

    # Encontrar todos os Chrome disponíveis
    candidates = find_all_chrome_binaries()
    print(f"\nBinários encontrados: {len(candidates)}")
    for label, path in candidates:
        print(f"  [{label}] {path}")

    if not candidates:
        print("\nNENHUM Chrome/Chromium encontrado!")
        print("Instale o Playwright Chromium: playwright install chromium")
        return

    # Testar cada binário
    port = CDP_PORT + 1
    for label, path in candidates:
        await test_webgl_with_binary(path, label, port)
        port += 1

    # Recomendação
    has_playwright = any(l == "playwright" for l, _ in candidates)
    print(f"\n{'='*60}")
    print("  RECOMENDAÇÃO")
    print(f"{'='*60}")
    if not has_playwright:
        print("  ⚠ Playwright Chromium NÃO instalado!")
        print("  Execute: playwright install chromium")
        print("  O Chromium do Playwright inclui SwiftShader embutido.")
    else:
        print("  ✓ Playwright Chromium disponível.")


asyncio.run(main())
