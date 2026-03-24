"""
llm_service.py
--------------
Camada de abstração que orquestra Langfuse (prompt + tracing) e
VertexClient (Gemini) para processar relatórios de monitoramento.

Uso:
    from clients.llm_service import processar_relatorio
    resultado = processar_relatorio("game_evidence/relatorio_diagnostico.json")
"""

import json
import os
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional

from config import BRAND, logger

from clients.langfuse_client import LangfuseClient
from clients.vertex_client import VertexClient
from clients.schemas import MONITORAMENTO_JOGOS_SCHEMA


# ── Exceções específicas ──────────────────────────────────────────────────────

class LLMServiceError(Exception):
    """Erro base do serviço de LLM."""


class PromptError(LLMServiceError):
    """Langfuse não retornou o prompt."""


class ModelError(LLMServiceError):
    """Gemini não pôde ser acionado."""


class OutputError(LLMServiceError):
    """Resposta do modelo inválida ou fora do schema esperado."""


# ── Resultado ─────────────────────────────────────────────────────────────────

@dataclass
class LLMResult:
    """Resultado estruturado de uma chamada ao pipeline de IA."""
    jogos: list[dict]
    input_tokens: int
    output_tokens: int
    latency: float
    cost_usd: float
    model: str
    session_id: str


# ── Constantes ────────────────────────────────────────────────────────────────

PROMPT_NAME = "monitoramento_jogos_supervisor"
DEFAULT_MODEL = "gemini-3-flash-preview"


# ── Funções auxiliares ────────────────────────────────────────────────────────

def _parse_output(texto: str) -> list[dict]:
    """Converte a resposta do modelo em lista de jogos, validando o schema."""
    # Remove possíveis marcadores markdown
    clean = texto.strip()
    if clean.startswith("```"):
        clean = clean.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    try:
        dados = json.loads(clean)
    except json.JSONDecodeError as exc:
        raise OutputError(f"Resposta do modelo não é JSON válido: {exc}") from exc

    if not isinstance(dados, list):
        raise OutputError(f"Esperado array JSON, recebido: {type(dados).__name__}")

    campos_obrigatorios = {"slug", "status", "detalhes"}
    status_validos = {"on", "off", "warning"}

    for i, item in enumerate(dados):
        faltando = campos_obrigatorios - set(item.keys())
        if faltando:
            raise OutputError(f"Jogo #{i}: campos faltando: {faltando}")
        if item.get("status") not in status_validos:
            raise OutputError(
                f"Jogo #{i} ({item.get('slug')}): status inválido '{item.get('status')}'"
            )

    return dados


# ── Função principal ──────────────────────────────────────────────────────────

def processar_relatorio(
    caminho_relatorio: str,
    model: str = DEFAULT_MODEL,
    session_id: Optional[str] = None,
    tags: Optional[list[str]] = None,
) -> LLMResult:
    """
    Processa um relatório diagnóstico de monitoramento via pipeline de IA.

    1. Busca o prompt no Langfuse
    2. Envia ao Gemini com response_schema
    3. Valida e retorna o resultado estruturado

    Args:
        caminho_relatorio: Caminho para o arquivo relatorio_diagnostico.json.
        model: Nome do modelo Gemini a usar.
        session_id: ID de sessão para rastreamento no Langfuse.
        tags: Tags adicionais para o trace.

    Returns:
        LLMResult com a lista de jogos analisados.

    Raises:
        PromptError: Langfuse não retornou o prompt.
        ModelError: Gemini não pôde ser acionado.
        OutputError: Resposta do modelo inválida.
        FileNotFoundError: Relatório não encontrado.
    """
    # ── 1. Lê o relatório ────────────────────────────────────────────
    if not os.path.exists(caminho_relatorio):
        raise FileNotFoundError(f"Relatório não encontrado: {caminho_relatorio}")

    with open(caminho_relatorio, encoding="utf-8") as f:
        relatorio_raw = f.read()

    total_jogos = len(json.loads(relatorio_raw).get("jogos", []))
    logger.info("[LLMService] Relatório carregado: %d jogos (%.1f KB)",
                total_jogos, len(relatorio_raw) / 1024)

    # ── 2. Busca prompt no Langfuse ──────────────────────────────────
    langfuse = LangfuseClient.get_instance()
    try:
        langfuse.connect()
        prompt_text = langfuse.compile_prompt(
            name=PROMPT_NAME,
            variables={"brand": BRAND},
        )
    except Exception as exc:
        raise PromptError(f"Falha ao obter prompt '{PROMPT_NAME}' do Langfuse: {exc}") from exc

    logger.info("[LLMService] Prompt pronto (%d chars)", len(prompt_text))

    # ── 3. Chama Gemini ──────────────────────────────────────────────
    session_id = session_id or f"monit-ia-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    tags = tags or ["monitoramento-ia"]

    try:
        vertex = VertexClient(system_prompt="", model=model)
    except Exception as exc:
        raise ModelError(f"Falha ao inicializar VertexClient: {exc}") from exc

    user_content = f"{prompt_text}\n\n---\nRELATÓRIO JSON:\n{relatorio_raw}"

    with langfuse.trace_generation(
        name=PROMPT_NAME,
        model=model,
        input_data=prompt_text,
        session_id=session_id,
        tags=tags,
    ) as gen:
        try:
            resultado = vertex.chamar_modelo(
                user_content=user_content,
                response_schema=MONITORAMENTO_JOGOS_SCHEMA,
                max_output_tokens=16384,
            )
        except Exception as exc:
            raise ModelError(f"Falha ao chamar o modelo {model}: {exc}") from exc

        # ── 4. Valida output ─────────────────────────────────────────
        try:
            jogos = _parse_output(resultado["texto"])
        except OutputError:
            # Registra output com erro no Langfuse antes de propagar
            gen["update"](
                output=resultado["texto"],
                tokens={
                    "input":  resultado["input_tokens"],
                    "output": resultado["output_tokens"],
                    "total":  resultado["input_tokens"] + resultado["output_tokens"],
                },
                latency=resultado["latency"],
            )
            raise

        # ── 5. Registra no Langfuse ──────────────────────────────────
        gen["update"](
            output=resultado["texto"],
            tokens={
                "input":  resultado["input_tokens"],
                "output": resultado["output_tokens"],
                "total":  resultado["input_tokens"] + resultado["output_tokens"],
            },
            latency=resultado["latency"],
        )

    # ── 6. Calcula custo e retorna ───────────────────────────────────
    cost = langfuse.calculate_cost(
        model=model,
        input_tokens=resultado["input_tokens"],
        output_tokens=resultado["output_tokens"],
    )

    logger.info(
        "[LLMService] Concluído: %d jogos | %d in / %d out tokens | %.2fs | $%.6f",
        len(jogos), resultado["input_tokens"], resultado["output_tokens"],
        resultado["latency"], cost["total"],
    )

    return LLMResult(
        jogos=jogos,
        input_tokens=resultado["input_tokens"],
        output_tokens=resultado["output_tokens"],
        latency=resultado["latency"],
        cost_usd=cost["total"],
        model=model,
        session_id=session_id,
    )
