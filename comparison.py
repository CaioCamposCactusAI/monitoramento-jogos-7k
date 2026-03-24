"""Módulo de comparação entre resultados do robô (scraping) e da IA.
Compara status e gera relatório + envia todos os jogos ao Supabase.
"""

import json
import logging
from pathlib import Path

from config import BRAND

logger = logging.getLogger("monitor-7k")


def gerar_relatorio_comparacao(
    resultados_robo: list[dict],
    resultados_ia: list[dict],
    evidence_dir: Path,
) -> list[dict]:
    """
    Gera arquivo de comparação e retorna TODOS os jogos com status do robô e da IA.

    Returns:
        Lista de todos os jogos: [{slug, brand, status_robo, status_ia, detalhes_ia}]
    """
    ia_por_slug = {j["slug"].lower(): j for j in resultados_ia}

    comparacoes = []
    todos = []
    for robo in resultados_robo:
        slug = robo["slug"].lower()
        ia = ia_por_slug.get(slug)

        status_robo = robo["status"]
        status_ia = ia["status"] if ia else None
        concordam = (status_robo == status_ia) if ia else False

        entry = {
            "slug": robo["slug"],
            "status_robo": status_robo,
            "status_ia": status_ia,
            "concordam": concordam,
        }
        if ia:
            entry["detalhes_ia"] = ia.get("detalhes", "")
        comparacoes.append(entry)

        todos.append({
            "slug": robo["slug"],
            "brand": BRAND,
            "status_robo": status_robo,
            "status_ia": status_ia or "unknown",
            "detalhes_ia": ia.get("detalhes", "") if ia else "",
        })

    total = len(comparacoes)
    concordam_count = sum(1 for c in comparacoes if c["concordam"])
    divergem = total - concordam_count

    relatorio = {
        "resumo": {
            "total": total,
            "concordam": concordam_count,
            "divergem": divergem,
        },
        "comparacoes": comparacoes,
    }

    path = evidence_dir / "comparacao_robo_ia.json"
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(relatorio, f, ensure_ascii=False, indent=2)
        logger.info(
            "Comparação Robô vs IA: %d concordam, %d divergem (salvo em %s)",
            concordam_count, divergem, path,
        )
    except OSError as exc:
        logger.error("Falha ao salvar comparação: %s", exc)

    return todos
