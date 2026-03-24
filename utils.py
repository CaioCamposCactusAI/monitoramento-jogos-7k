"""
Funções utilitárias de uso geral.
"""

import asyncio
import json
import os
import random
from pathlib import Path
from urllib.parse import urlparse


async def human_delay(a: float = 0.15, b: float = 0.7):
    """Pausa com duração aleatória para simular comportamento humano."""
    await asyncio.sleep(random.uniform(a, b))


def load_env(filepath: str) -> dict[str, str]:
    """Carrega variáveis do arquivo .env e injeta em os.environ (não sobrescreve)."""
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
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                env_vars[key] = value
                if key not in os.environ:
                    os.environ[key] = value
    return env_vars


def load_games(filepath: str) -> list[str]:
    """Carrega a lista de jogos do arquivo JSON."""
    with open(filepath, encoding="utf-8") as f:
        slugs = json.load(f)
    return [s.lower() for s in slugs]


def sanitize_filename(name: str) -> str:
    """Remove caracteres inválidos para nome de arquivo."""
    return "".join(c if c.isalnum() or c in (" ", "-", "_") else "_" for c in name).strip()


def trim_url(url: str, max_len: int = 100) -> str:
    """Remove query params and truncate URL to save tokens in reports."""
    try:
        parsed = urlparse(url)
        clean = f"{parsed.netloc}{parsed.path}"
        return clean[:max_len]
    except Exception:
        return url[:max_len]
