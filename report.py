"""
Geração de relatórios — operacional (relatorio.json) e AI-otimizado (relatorio_diagnostico.json).
"""

import json
from datetime import datetime
from pathlib import Path

from config import BRAND, logger
from utils import trim_url


def _build_frames_compact(diag_data: dict) -> list:
    """Extrai resumo compacto de todos os frames do diagnóstico."""
    frames = []
    for fc in (diag_data.get("game_iframe_frames") or []):
        entry = {"n": fc.get("nivel", 0), "url": fc.get("frame_url", "")}
        text = (fc.get("text") or "").strip()
        if text:
            entry["txt"] = text[:300]
        title = fc.get("title", "")
        if title:
            entry["title"] = title
        canvas = fc.get("canvas_count", 0)
        if canvas:
            entry["canvas"] = canvas
        frames.append(entry)
    return frames


def generate_reports(
    results: list[dict],
    evidence_dir: Path,
    timestamp: str,
    tempo_decorrido: str,
    recursos: dict,
) -> None:
    """Gera relatorio.json e relatorio_diagnostico.json."""
    total = len(results)
    on_count = sum(1 for r in results if r["status"] == "on")
    off_count = total - on_count

    on_list = [r["slug"] for r in results if r["status"] == "on"]
    off_list = [
        {"slug": r["slug"], "motivo": r.get("motivo", "")}
        for r in results if r["status"] == "off"
    ]

    # ─── Relatório operacional ─────────────────────────────────────────────
    report = {
        "ts": timestamp,
        "duracao": tempo_decorrido,
        "brand": BRAND,
        "recursos": recursos,
        "resumo": {"total": total, "on": on_count, "off": off_count},
        "on": on_list,
        "off": off_list,
    }

    report_path = evidence_dir / "relatorio.json"
    try:
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        logger.info("Relatório salvo em: %s", report_path)
    except OSError as exc:
        logger.error("Falha ao salvar relatório operacional (%s): %s", report_path, exc)

    # ─── Relatório AI-otimizado ────────────────────────────────────────────
    ai_report = {
        "meta": {
            "ts": datetime.now().isoformat(),
            "duracao": tempo_decorrido,
            "brand": BRAND,
            "total": total,
            "on": on_count,
            "off": off_count,
            "recursos": recursos,
        },
        "jogos": [],
    }

    for r in results:
        d = r.pop("_diag", {})
        t = r.pop("_tentativas", [])
        frames_compact = _build_frames_compact(d)

        jogo = {
            "slug": r["slug"],
            "status": r["status"],
            "motivo": r.get("motivo", ""),
        }
        if t:
            jogo["tentativa"] = t[-1]
            jogo["total_tentativas"] = len(t)
        if d.get("url_final"):
            jogo["url"] = trim_url(d["url_final"])
        if frames_compact:
            jogo["frames"] = frames_compact
        if d.get("textos_suspeitos"):
            jogo["textos_suspeitos"] = d["textos_suspeitos"]
        if d.get("erro"):
            jogo["erro"] = d["erro"]

        ai_report["jogos"].append(jogo)

    diag_path = evidence_dir / "relatorio_diagnostico.json"
    try:
        with open(diag_path, "w", encoding="utf-8") as f:
            json.dump(ai_report, f, ensure_ascii=False, indent=2)
        logger.info("Relatório AI-otimizado salvo em: %s", diag_path)
    except OSError as exc:
        logger.error("Falha ao salvar relatório AI (%s): %s", diag_path, exc)


def print_summary(results: list[dict]) -> None:
    """Exibe resumo no console."""
    print("\n" + "=" * 70)
    print("  RELATÓRIO DE MONITORAMENTO - 7K BET")
    print("=" * 70)

    for r in results:
        icon = "✅" if r["status"] == "on" else "❌"
        print(f"  {icon} {r['slug']} - {r['status'].upper()}")
        if r["motivo"]:
            print(f"     {r['motivo']}")

    total = len(results)
    on = sum(1 for r in results if r["status"] == "on")
    print(f"\n  Total: {total} | ON: {on} | OFF: {total - on}")
    print("=" * 70 + "\n")
