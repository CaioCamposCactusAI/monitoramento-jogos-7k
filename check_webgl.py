"""
Diagnóstico: verifica se o Chrome no servidor suporta WebGL.
Executa no servidor com: python check_webgl.py
"""
import asyncio
import subprocess
import os

from config import CHROME_PATH, IS_PROD, CDP_PORT


async def main():
    print(f"CHROME_PATH: {CHROME_PATH}")
    print(f"IS_PROD: {IS_PROD}")

    # Verificar se o binário existe
    if not os.path.exists(CHROME_PATH):
        print(f"ERRO: Chrome não encontrado em {CHROME_PATH}")
        return

    # Mostrar versão
    try:
        ver = subprocess.check_output([CHROME_PATH, "--version"], stderr=subprocess.STDOUT, timeout=5)
        print(f"Chrome version: {ver.decode().strip()}")
    except Exception as e:
        print(f"Não foi possível obter versão: {e}")

    # Listar libs SwiftShader disponíveis
    chrome_dir = os.path.dirname(CHROME_PATH)
    print(f"\nChrome dir: {chrome_dir}")
    for root, dirs, files in os.walk(chrome_dir):
        for f in files:
            fl = f.lower()
            if any(kw in fl for kw in ["swiftshader", "egl", "gles", "vulkan", "libgl", "webgl"]):
                full = os.path.join(root, f)
                size = os.path.getsize(full)
                print(f"  {os.path.relpath(full, chrome_dir)} ({size:,} bytes)")

    # Lançar Chrome e testar WebGL via CDP
    from playwright.async_api import async_playwright

    chrome_args = [
        CHROME_PATH,
        f"--remote-debugging-port={CDP_PORT + 1}",
        "--user-data-dir=/tmp/webgl_test_profile",
        "--no-first-run",
        "--no-default-browser-check",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--use-gl=swiftshader",
        "--enable-webgl",
        "--window-size=800,600",
    ]
    print(f"\nLaunching: {' '.join(chrome_args[:5])}...")
    proc = subprocess.Popen(chrome_args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    await asyncio.sleep(3)

    try:
        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(f"http://localhost:{CDP_PORT + 1}")
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
        print(f"Erro ao testar: {e}")
    finally:
        proc.terminate()
        proc.wait()


asyncio.run(main())
