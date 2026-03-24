"""
Configuração central do robô de monitoramento — constantes, logging e detecção de ambiente.
Todas as credenciais e configurações ficam aqui. Variáveis de ambiente têm prioridade.
"""

import os
import logging

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
ACCESS_TOKEN = "4Le27ZD-mar25"
INPUT_FILE = "input2.json"
BRAND = "7k"
GAMES_BASE_URL = "https://7k.bet.br/games/"
EVIDENCE_DIR = "game_evidence"
PROFILE_DIR = "chrome_cdp_profile"
CDP_PORT = 9222
CONCURRENT_TABS = 3
GAME_LOAD_TIMEOUT = 10_000  # 10 segundos em ms
PER_GAME_TIMEOUT = 60  # timeout total por jogo em segundos (inclui retry)
LOGIN_TIMEOUT = 10_000
CF_MAX_WAIT = 30  # segundos máximos para aguardar challenge do Cloudflare

# ─── Supabase ──────────────────────────────────────────────────────────────────
SUPABASE_URL = "https://zsjwisovauepmmftxjrs.supabase.co"
SUPABASE_TOKEN = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inpzandpc292YXVlcG1tZnR4anJzIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzM5NDgwOTYsImV4cCI6MjA4OTUyNDA5Nn0."
    "aMMvV6r8mICD4NrHQwcilyymJty-G0rt1U0BCYqEm30"
)
SUPABASE_HEADERS = {
    "apikey": SUPABASE_TOKEN,
    "Authorization": f"Bearer {SUPABASE_TOKEN}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal",
}

# ─── Credenciais de login ─────────────────────────────────────────────────────
EMAIL = os.environ.get("EMAIL", "player@email.com")
SENHA = os.environ.get("SENHA", "secret")

# ─── Google AI Studio (Gemini) ────────────────────────────────────────────────
GOOGLE_AI_STUDIO_KEY = os.environ.get(
    "GOOGLE_AI_STUDIO_KEY",
    "AIzaSyCL4dPer0ryFF4VlLbUPZlvhx8rUujwOqg",
)

# ─── Langfuse ──────────────────────────────────────────────────────────────
LANGFUSE_PUBLIC_KEY = os.environ.get(
    "LANGFUSE_PUBLIC_KEY",
    "pk-lf-6a529a39-71ac-42d3-b8f4-04fe1a2af7b4",
)
LANGFUSE_SECRET_KEY = os.environ.get(
    "LANGFUSE_SECRET_KEY",
    "sk-lf-66e36bb2-07ba-496f-a1ca-208f952df104",
)
LANGFUSE_HOST = os.environ.get(
    "LANGFUSE_HOST",
    "https://us.cloud.langfuse.com",
)

# ─── Detecção de ambiente ──────────────────────────────────────────────────────
# environment: "staging" = Windows (dev local) | "prod" = Linux (produção)
ENVIRONMENT = os.environ.get("environment", "prod").lower()
IS_PROD = ENVIRONMENT == "prod"

if IS_PROD:
    import glob as _glob
    _pw_candidates = sorted(
        _glob.glob(os.path.expanduser("~/.cache/ms-playwright/chromium-*/chrome-linux/chrome")),
        reverse=True,
    )
    if _pw_candidates:
        CHROME_PATH = _pw_candidates[0]
    else:
        CHROME_PATH = "/usr/bin/chromium-browser"
    CONCURRENT_TABS = 3
    GAME_LOAD_TIMEOUT = 15_000  # 15 segundos em produção
else:
    CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
