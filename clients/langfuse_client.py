"""
langfuse_client.py
------------------
Cliente Langfuse para gerenciamento de prompts e registro de
input/output/custos de chamadas a modelos de IA.

Interface principal:
    LangfuseClient.get_instance()          → singleton
    .get_prompt(name, label)               → objeto prompt
    .compile_prompt(name, variables)       → str pronto para uso
    .trace_generation(name, model, ...)    → context manager para tracing
    .flush()                               → força envio dos eventos pendentes
"""

import os
import time
import logging
from typing import Optional, Dict, Any
from contextlib import contextmanager

from langfuse import Langfuse, propagate_attributes

from config import ENVIRONMENT, logger


class LangfuseClient:
    """Cliente para gerenciar prompts e tracing no Langfuse."""

    _instance: Optional["LangfuseClient"] = None

    # ── Preços dos modelos (USD por 1 milhão de tokens) ──────────────
    # Fonte: https://ai.google.dev/gemini-api/docs/pricing (Paid tier, Standard)
    PRICING: Dict[str, Dict[str, float]] = {
        "gemini-2.5-flash": {
            "input":       0.30,
            "output":      2.50,
            "cache_read":  0.03,
            "cache_write": 0.30,
        },
        "gemini-3-flash": {
            "input":       0.50,
            "output":      3.00,
            "cache_read":  0.05,
            "cache_write": 0.50,
        },
        "default": {
            "input":       1.00,
            "output":      3.00,
            "cache_read":  0.25,
            "cache_write": 1.00,
        },
    }

    def __init__(self) -> None:
        self._client: Optional[Langfuse] = None

    # ── Conexão ──────────────────────────────────────────────────────

    def connect(self) -> None:
        """Estabelece conexão com o Langfuse."""
        if self._client is None:
            public_key = os.environ.get("LANGFUSE_PUBLIC_KEY", "")
            secret_key = os.environ.get("LANGFUSE_SECRET_KEY", "")
            host = os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com")

            if not public_key or not secret_key:
                raise ValueError("LANGFUSE_PUBLIC_KEY e LANGFUSE_SECRET_KEY não configuradas no .env")

            self._client = Langfuse(
                public_key=public_key,
                secret_key=secret_key,
                host=host,
                environment=ENVIRONMENT if ENVIRONMENT == "prod" else "staging",
            )
            logger.info("Conexão com Langfuse estabelecida: %s", host)

    def get_client(self) -> Langfuse:
        """Retorna o cliente Langfuse, conectando se necessário."""
        if self._client is None:
            self.connect()
        return self._client

    @classmethod
    def get_instance(cls) -> "LangfuseClient":
        """Retorna instância singleton do LangfuseClient."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ── Prompts ───────────────────────────────────────────────────────

    def get_prompt(
        self,
        name: str,
        version: Optional[int] = None,
        label: str = "production",
    ) -> Any:
        """Busca um prompt do Langfuse."""
        client = self.get_client()
        prompt = (
            client.get_prompt(name, version=version)
            if version
            else client.get_prompt(name, label=label)
        )
        logger.info("Prompt recuperado: '%s' (versão: %s)", name, prompt.version)
        return prompt

    def compile_prompt(
        self,
        name: str,
        variables: Dict[str, Any],
        version: Optional[int] = None,
        label: str = "production",
    ) -> str:
        """Busca e compila um prompt com variáveis."""
        prompt = self.get_prompt(name, version=version, label=label)
        compiled: str = prompt.compile(**variables)
        logger.info("Prompt compilado: '%s'", name)
        return compiled

    # ── Custos ────────────────────────────────────────────────────────

    def calculate_cost(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cache_read_tokens: int = 0,
        cache_write_tokens: int = 0,
    ) -> Dict[str, float]:
        """Calcula o custo de uma requisição com base no modelo e tokens."""
        model_lower = model.lower()

        pricing_key = "default"
        for key in self.PRICING:
            if key in model_lower:
                pricing_key = key
                break

        pricing = self.PRICING[pricing_key]

        uncached_input   = max(0, input_tokens - cache_read_tokens - cache_write_tokens)
        input_cost       = (uncached_input     / 1_000_000) * pricing["input"]
        cache_read_cost  = (cache_read_tokens  / 1_000_000) * pricing.get("cache_read",  pricing["input"])
        cache_write_cost = (cache_write_tokens / 1_000_000) * pricing.get("cache_write", pricing["input"])
        output_cost      = (output_tokens      / 1_000_000) * pricing["output"]
        total_cost       = input_cost + cache_read_cost + cache_write_cost + output_cost

        return {
            "input":        input_cost + cache_read_cost + cache_write_cost,
            "output":       output_cost,
            "total":        total_cost,
            "pricing_tier": pricing_key,
        }

    # ── Tracing ───────────────────────────────────────────────────────

    @contextmanager
    def trace_generation(
        self,
        name: str,
        model: str,
        input_data: Optional[Any] = None,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[list] = None,
    ):
        """
        Context manager que cria uma generation no Langfuse e calcula custos.

        Uso:
            with langfuse.trace_generation(
                name="monitoramento_jogos_supervisor",
                model="gemini-2.5-flash",
                input_data=prompt_text,
                session_id="run-20250323",
            ) as gen:
                resultado = vertex.chamar_modelo_com_arquivo(...)
                gen["update"](
                    output=resultado["texto"],
                    tokens={"input": 300, "output": 150, "total": 450},
                )
        """
        client = self.get_client()
        start_time = time.time()

        with propagate_attributes(
            user_id=str(user_id) if user_id else None,
            session_id=str(session_id) if session_id else None,
            tags=tags,
            trace_name=name,
        ):
          with client.start_as_current_observation(
            as_type="generation",
            name=name,
            model=model,
            input=input_data,
            metadata=metadata or {},
          ) as generation:

            logger.info("Generation iniciada: '%s' (model: %s, session: %s)", name, model, session_id)

            def update(
                output: Any,
                tokens: Dict[str, int],
                latency: Optional[float] = None,
            ) -> None:
                elapsed = latency if latency is not None else (time.time() - start_time)
                cache_read  = tokens.get("cache_read",  0)
                cache_write = tokens.get("cache_write", 0)
                cost = self.calculate_cost(
                    model=model,
                    input_tokens=tokens.get("input", 0),
                    output_tokens=tokens.get("output", 0),
                    cache_read_tokens=cache_read,
                    cache_write_tokens=cache_write,
                )

                usage_details: Dict[str, int] = {
                    "input":  tokens.get("input",  0),
                    "output": tokens.get("output", 0),
                    "total":  tokens.get("total",  0),
                }
                if cache_read:
                    usage_details["cache_read_input_tokens"] = cache_read
                if cache_write:
                    usage_details["cache_creation_input_tokens"] = cache_write

                generation.update(
                    output=output,
                    usage_details=usage_details,
                    cost_details={
                        "input":  cost["input"],
                        "output": cost["output"],
                        "total":  cost["total"],
                    },
                    metadata={
                        **(metadata or {}),
                        "latency_seconds": elapsed,
                        "pricing_tier":    cost["pricing_tier"],
                        "cost_usd":        cost["total"],
                    },
                )

                logger.info(
                    "Generation finalizada: '%s' | latency=%.2fs | tokens=%d | cost=$%.6f (%s)",
                    name, elapsed, tokens.get("total", 0), cost["total"], cost["pricing_tier"],
                )

            try:
                yield {"generation": generation, "update": update, "start_time": start_time}
            finally:
                self.flush()

    # ── Flush ─────────────────────────────────────────────────────────

    def flush(self) -> None:
        """Força o envio de todos os eventos pendentes ao Langfuse."""
        try:
            if self._client:
                self._client.flush()
        except Exception as exc:
            logger.warning("Falha no flush do Langfuse (não-crítico): %s", exc)
