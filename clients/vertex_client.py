"""
vertex_client.py
----------------
Cliente Vertex AI (Google GenAI SDK) para chamadas ao modelo Gemini.

Responsabilidade:
    - Conectar via API key (staging) ou ADC (prod).
    - Executar chamadas com retry em rate-limit.
    - Suportar envio de arquivos JSON como Part (não texto).
    - Forçar response_schema (JSON estruturado).
    - Retornar texto + metadados de tokens.
"""

import os
import time
import logging

from google import genai
from google.genai import types

from config import ENVIRONMENT, logger

# ─── Safety desligada (conteúdo de jogos/apostas) ─────────────────────────────
_SAFETY_OFF: list[types.SafetySetting] = [
    types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH",       threshold="OFF"),
    types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="OFF"),
    types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="OFF"),
    types.SafetySetting(category="HARM_CATEGORY_HARASSMENT",        threshold="OFF"),
]

WAIT_SECONDS  = 10
MAX_WAIT_TIME = 600  # 10 min de tolerância para rate-limit


class VertexClient:
    """Cliente Vertex AI / Google AI Studio para o modelo Gemini."""

    DEFAULT_MODEL = "gemini-3-flash-preview"

    def __init__(self, system_prompt: str = "", model: str = DEFAULT_MODEL) -> None:
        self.model = model
        self.system_prompt = system_prompt

        api_key = os.environ.get("GOOGLE_AI_STUDIO_KEY", "")
        if ENVIRONMENT == "prod":
            self._client = genai.Client(vertexai=True)
        else:
            if not api_key:
                raise ValueError("GOOGLE_AI_STUDIO_KEY não configurada no .env")
            self._client = genai.Client(api_key=api_key)

    # ── helpers ────────────────────────────────────────────────────────

    def _build_config(
        self,
        temperature: float,
        top_p: float,
        max_output_tokens: int,
        response_schema: dict | None = None,
    ) -> types.GenerateContentConfig:
        kwargs: dict = dict(
            system_instruction=self.system_prompt,
            temperature=temperature,
            top_p=top_p,
            max_output_tokens=max_output_tokens,
            safety_settings=_SAFETY_OFF,
        )
        if response_schema is not None:
            kwargs["response_mime_type"] = "application/json"
            kwargs["response_schema"] = response_schema
        return types.GenerateContentConfig(**kwargs)

    @staticmethod
    def _is_rate_limit(exc: Exception) -> bool:
        return "ResourceExhausted" in type(exc).__name__ or "429" in str(exc)

    def _call_with_retry(self, contents: list, config: types.GenerateContentConfig):
        inicio = time.time()
        while True:
            try:
                return self._client.models.generate_content(
                    model=self.model,
                    contents=contents,
                    config=config,
                )
            except Exception as exc:
                if self._is_rate_limit(exc):
                    if time.time() - inicio >= MAX_WAIT_TIME:
                        raise TimeoutError(
                            "Rate-limit persistente no Vertex AI (>10 min)."
                        ) from exc
                    logger.warning("[VertexClient] Rate-limit — aguardando %ds…", WAIT_SECONDS)
                    time.sleep(WAIT_SECONDS)
                else:
                    raise

    # ── interface pública ──────────────────────────────────────────────

    def chamar_modelo(
        self,
        user_content: str,
        temperature: float = 0.2,
        top_p: float = 0.95,
        max_output_tokens: int = 8192,
        response_schema: dict | None = None,
    ) -> dict:
        """
        Envia requisição com conteúdo texto.

        Returns:
            {"texto", "input_tokens", "output_tokens", "latency"}
        """
        contents = [
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=user_content)],
            )
        ]
        config = self._build_config(temperature, top_p, max_output_tokens, response_schema)

        inicio = time.time()
        response = self._call_with_retry(contents, config)

        usage = getattr(response, "usage_metadata", None)
        return {
            "texto":         response.text.strip(),
            "input_tokens":  getattr(usage, "prompt_token_count", 0) if usage else 0,
            "output_tokens": getattr(usage, "candidates_token_count", 0) if usage else 0,
            "latency":       time.time() - inicio,
        }

    def chamar_modelo_com_arquivo(
        self,
        user_content: str,
        file_path: str,
        temperature: float = 0.2,
        top_p: float = 0.95,
        max_output_tokens: int = 8192,
        response_schema: dict | None = None,
    ) -> dict:
        """
        Envia requisição com conteúdo texto + arquivo JSON via File API.

        O arquivo é enviado como Part nativo (não como texto inline).

        Returns:
            {"texto", "input_tokens", "output_tokens", "latency"}
        """
        logger.info("[VertexClient] Fazendo upload do arquivo: %s", file_path)
        uploaded_file = self._client.files.upload(
            file=file_path,
            config=types.UploadFileConfig(mime_type="application/json"),
        )
        logger.info("[VertexClient] Upload concluído: %s", uploaded_file.name)

        contents = [
            types.Content(
                role="user",
                parts=[
                    types.Part.from_text(text=user_content),
                    types.Part.from_uri(file_uri=uploaded_file.uri, mime_type="application/json"),
                ],
            )
        ]
        config = self._build_config(temperature, top_p, max_output_tokens, response_schema)

        inicio = time.time()
        response = self._call_with_retry(contents, config)

        usage = getattr(response, "usage_metadata", None)
        return {
            "texto":         response.text.strip(),
            "input_tokens":  getattr(usage, "prompt_token_count", 0) if usage else 0,
            "output_tokens": getattr(usage, "candidates_token_count", 0) if usage else 0,
            "latency":       time.time() - inicio,
        }
