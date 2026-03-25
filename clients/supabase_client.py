"""
Cliente Supabase para enviar resultados do monitoramento de jogos.
Envia em lote: insere novos registros e atualiza todos os existentes (sempre),
garantindo que updated_at seja refrescado a cada ciclo.
"""

import logging
from datetime import datetime, timezone

import httpx

from config import SUPABASE_URL, SUPABASE_HEADERS

logger = logging.getLogger("monitor-7k")

TABLE = "monitoramento_jogos"
HEADERS = SUPABASE_HEADERS


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
    - Atualiza TODOS os registros existentes (independente de mudança de status),
      garantindo que updated_at seja sempre refrescado para visibilidade realtime

    Retorna resumo: {inserted, updated}
    """
    logger.info("Consultando registros existentes no Supabase (brand=%s)...", brand)
    existing = _get_existing(brand)
    logger.info("Registros existentes: %d", len(existing))

    to_insert = []
    to_update = []

    for rec in results:
        slug = rec["slug"]
        if slug not in existing:
            to_insert.append(rec)
        else:
            to_update.append(rec)

    # Inserir novos em lote
    inserted = _batch_insert(to_insert)
    if inserted:
        logger.info("Inseridos: %d novos registros.", inserted)

    # Atualizar todos os existentes (sempre, para refrescar updated_at)
    updated = _batch_update(to_update, existing)
    if updated:
        logger.info("Atualizados: %d registros.", updated)

    summary = {"inserted": inserted, "updated": updated}
    logger.info("Supabase sync concluído: %s", summary)
    return summary


# ─── monitoramento_jogos_ia ──────────────────────────────────────────────────

TABLE_IA = "monitoramento_jogos_ia"


def send_ia_results(jogos: list[dict], brand: str = "7k") -> dict:
    """
    Envia resultados da análise de IA ao Supabase (tabela monitoramento_jogos_ia).
    Usa upsert com on_conflict (slug, brand) para inserir ou atualizar.

    Args:
        jogos: Lista de dicts com {slug, status, detalhes}.
        brand: Identificador da marca.

    Returns:
        Resumo: {total}
    """
    if not jogos:
        return {"total": 0}

    now = datetime.now(timezone.utc).isoformat()
    payload = [
        {
            "slug": j["slug"].lower(),
            "brand": brand.lower(),
            "status": j["status"],
            "detalhes": j.get("detalhes", ""),
            "updated_at": now,
        }
        for j in jogos
    ]

    headers_upsert = {
        **HEADERS,
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }

    r = httpx.post(
        f"{SUPABASE_URL}/rest/v1/{TABLE_IA}",
        headers=headers_upsert,
        params={"on_conflict": "slug,brand"},
        json=payload,
        timeout=30,
    )
    r.raise_for_status()

    logger.info("Supabase IA sync: %d jogos enviados (upsert).", len(payload))
    return {"total": len(payload)}


# ─── agents_health_check ─────────────────────────────────────────────────────

TABLE_HEALTH = "agents_health_check"
TABLE_ERRORS = "agentes_health_check_errors"


def get_agent_status(agent_name: str) -> str | None:
    """Consulta o status atual do agente. Retorna None se não existir."""
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/{TABLE_HEALTH}",
        headers=HEADERS,
        params={"agent_name": f"eq.{agent_name}", "select": "status"},
        timeout=10,
    )
    r.raise_for_status()
    rows = r.json()
    return rows[0]["status"] if rows else None


def upsert_agent_health(agent_name: str, status: str, step: str) -> None:
    """Upsert no agents_health_check (on_conflict agent_name)."""
    now = datetime.now(timezone.utc).isoformat()
    headers_upsert = {
        **HEADERS,
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }
    r = httpx.post(
        f"{SUPABASE_URL}/rest/v1/{TABLE_HEALTH}",
        headers=headers_upsert,
        params={"on_conflict": "agent_name"},
        json={"agent_name": agent_name, "status": status, "step": step, "updated_at": now},
        timeout=10,
    )
    r.raise_for_status()


def insert_agent_error(agent_name: str, error_msg: str) -> None:
    """Registra um erro na tabela agentes_health_check_errors."""
    r = httpx.post(
        f"{SUPABASE_URL}/rest/v1/{TABLE_ERRORS}",
        headers=HEADERS,
        json={"agent_name": agent_name, "error": error_msg[:2000]},
        timeout=10,
    )
    r.raise_for_status()


# ─── monitoramento_jogos_ia_feedback ──────────────────────────────────────────

TABLE_FEEDBACK = "monitoramento_jogos_ia_feedback"


def send_ia_feedback(jogos: list[dict]) -> int:
    """
    Upsert de todos os jogos comparados (robô vs IA) na tabela de feedback.
    Chave única: slug + brand.

    Args:
        jogos: Lista de {slug, brand, status_ia, status_robo, detalhes_ia}.

    Returns:
        Quantidade de registros enviados.
    """
    if not jogos:
        return 0

    now = datetime.now(timezone.utc).isoformat()
    payload = [
        {
            "slug": j["slug"],
            "brand": j["brand"],
            "status_ia": j["status_ia"],
            "status_robo": j["status_robo"],
            "detalhes_ia": j.get("detalhes_ia", ""),
            "updated_at": now,
        }
        for j in jogos
    ]

    headers_upsert = {
        **HEADERS,
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }

    r = httpx.post(
        f"{SUPABASE_URL}/rest/v1/{TABLE_FEEDBACK}",
        headers=headers_upsert,
        params={"on_conflict": "slug,brand"},
        json=payload,
        timeout=30,
    )
    r.raise_for_status()

    logger.info("Feedback IA: %d divergências enviadas ao Supabase.", len(payload))
    return len(payload)
