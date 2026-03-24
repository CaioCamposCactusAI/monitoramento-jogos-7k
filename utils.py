"""
Funções utilitárias de uso geral.
"""

import asyncio
import json
import random
from pathlib import Path
from urllib.parse import urlparse


async def human_delay(a: float = 0.15, b: float = 0.7):
    """Pausa com duração aleatória para simular comportamento humano."""
    await asyncio.sleep(random.uniform(a, b))


def load_games(filepath: str) -> list[str]:
    """Carrega a lista de jogos do arquivo JSON."""
    with open(filepath, encoding="utf-8") as f:
        slugs = json.load(f)
    return [s.lower() for s in slugs]


def build_diverse_batches(slugs: list[str], batch_size: int) -> list[list[str]]:
    """Monta lotes onde cada lote tem no máximo 1 jogo por provedora."""
    from collections import defaultdict

    # Agrupar slugs por provedora
    provider_queues: dict[str, list[str]] = defaultdict(list)
    for slug in slugs:
        provider = slug.split("/")[0] if "/" in slug else "unknown"
        provider_queues[provider].append(slug)

    batches: list[list[str]] = []
    while any(provider_queues.values()):
        batch: list[str] = []
        used_providers: set[str] = set()

        # Ordenar provedoras pela quantidade restante (maior primeiro)
        sorted_providers = sorted(
            provider_queues.keys(),
            key=lambda p: len(provider_queues[p]),
            reverse=True,
        )

        for provider in sorted_providers:
            if len(batch) >= batch_size:
                break
            if provider in used_providers:
                continue
            queue = provider_queues[provider]
            if queue:
                batch.append(queue.pop(0))
                used_providers.add(provider)

        # Remover provedoras vazias
        provider_queues = {p: q for p, q in provider_queues.items() if q}

        if batch:
            batches.append(batch)

    return batches


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
