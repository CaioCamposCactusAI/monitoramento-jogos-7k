"""
schemas.py
----------
Schemas de resposta estruturada para chamadas ao modelo de IA.
"""


# ── Schema: análise de jogos monitorados ──────────────────────────────────────
MONITORAMENTO_JOGOS_SCHEMA = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {
            "slug":     {"type": "STRING"},
            "status":   {"type": "STRING", "enum": ["on", "off", "warning"]},
            "detalhes": {"type": "STRING"},
        },
        "required": ["slug", "status", "detalhes"],
    },
}
