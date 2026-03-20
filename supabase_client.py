"""
Cliente Supabase para enviar resultados do monitoramento de jogos.
Envia em lote, só atualiza se status mudou, insere novos registros.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import httpx

logger = logging.getLogger("monitor-7k")

SUPABASE_URL = "https://zsjwisovauepmmftxjrs.supabase.co"
SUPABASE_TOKEN = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inpzandpc292YXVlcG1tZnR4anJzIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzM5NDgwOTYsImV4cCI6MjA4OTUyNDA5Nn0."
    "aMMvV6r8mICD4NrHQwcilyymJty-G0rt1U0BCYqEm30"
)
TABLE = "monitoramento_jogos"

HEADERS = {
    "apikey": SUPABASE_TOKEN,
    "Authorization": f"Bearer {SUPABASE_TOKEN}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal",
}


def _get_existing(brand: str) -> dict[str, dict]:
    """Busca todos os registros da brand no banco. Retorna dict slug -> row."""
    rows = []
    offset = 0
    page_size = 1000
    while True:
        r = httpx.get(
            f"{SUPABASE_URL}/rest/v1/{TABLE}",
            headers={**HEADERS, "Range": f"{offset}-{offset + page_size - 1}"},
            params={"brand": f"eq.{brand}", "select": "id,slug,brand,status,motivo"},
        )
        if r.status_code == 416:  # Range not satisfiable = no more rows
            break
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size

    return {row["slug"]: row for row in rows}


def _batch_insert(records: list[dict]) -> int:
    """Insere registros novos em lote. Retorna quantidade inserida."""
    if not records:
        return 0
    now = datetime.now(timezone.utc).isoformat()
    payload = [
        {
            "slug": r["slug"],
            "brand": r["brand"],
            "status": r["status"],
            "motivo": r["motivo"],
            "created_at": now,
            "updated_at": now,
        }
        for r in records
    ]
    r = httpx.post(
        f"{SUPABASE_URL}/rest/v1/{TABLE}",
        headers=HEADERS,
        json=payload,
        timeout=30,
    )
    r.raise_for_status()
    return len(payload)


def _batch_update(updates: list[dict], existing: dict[str, dict]) -> int:
    """Atualiza registros cujo status mudou. Retorna quantidade atualizada."""
    if not updates:
        return 0
    now = datetime.now(timezone.utc).isoformat()
    count = 0
    for rec in updates:
        row = existing[rec["slug"]]
        r = httpx.patch(
            f"{SUPABASE_URL}/rest/v1/{TABLE}",
            headers=HEADERS,
            params={"id": f"eq.{row['id']}"},
            json={
                "status": rec["status"],
                "motivo": rec["motivo"],
                "updated_at": now,
            },
            timeout=15,
        )
        r.raise_for_status()
        count += 1
    return count


def send_results(results: list[dict], brand: str = "7k") -> dict:
    """
    Envia resultados do monitoramento ao Supabase.
    - Busca todos os registros da brand em uma única query
    - Insere novos em lote
    - Atualiza apenas os que tiveram mudança de status

    Retorna resumo: {inserted, updated, unchanged}
    """
    logger.info("Consultando registros existentes no Supabase (brand=%s)...", brand)
    existing = _get_existing(brand)
    logger.info("Registros existentes: %d", len(existing))

    to_insert = []
    to_update = []
    unchanged = 0

    for rec in results:
        slug = rec["slug"]
        if slug not in existing:
            to_insert.append(rec)
        else:
            row = existing[slug]
            if row["status"] != rec["status"]:
                to_update.append(rec)
            else:
                unchanged += 1

    # Inserir novos em lote
    inserted = _batch_insert(to_insert)
    if inserted:
        logger.info("Inseridos: %d novos registros.", inserted)

    # Atualizar os que mudaram de status
    updated = _batch_update(to_update, existing)
    if updated:
        logger.info("Atualizados: %d registros (status mudou).", updated)

    if unchanged:
        logger.info("Sem alteração: %d registros.", unchanged)

    summary = {"inserted": inserted, "updated": updated, "unchanged": unchanged}
    logger.info("Supabase sync concluído: %s", summary)
    return summary


if __name__ == "__main__":
    # Teste standalone: lê relatorio.json e envia
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    report_path = Path("game_evidence") / "relatorio.json"
    if not report_path.exists():
        print(f"Arquivo {report_path} não encontrado. Execute o monitor primeiro.")
    else:
        report = json.load(open(report_path, encoding="utf-8"))
        results = report.get("resultados", [])
        summary = send_results(results)
        print(f"Resultado: {summary}")
