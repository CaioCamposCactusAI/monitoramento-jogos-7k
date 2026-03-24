"""
Cliente de Health Check — gerencia status do agente nas tabelas
agents_health_check e agentes_health_check_errors via supabase_client.
"""

import logging

from clients.supabase_client import get_agent_status, upsert_agent_health, insert_agent_error

logger = logging.getLogger("monitor-7k")


class HealthCheck:
    """Gerencia o health check de um agente específico."""

    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        self._current_status: str | None = None  # cache do status lido no início

    # ─── Leitura ──────────────────────────────────────────────────────────

    def get_status(self) -> str | None:
        """Consulta o status atual do agente no banco. Retorna None se não existir."""
        try:
            self._current_status = get_agent_status(self.agent_name)
            return self._current_status
        except Exception as exc:
            logger.warning("Falha ao consultar health check: %s", exc)
            return None

    # ─── Escrita ──────────────────────────────────────────────────────────

    def update(self, status: str, step: str) -> None:
        """
        Atualiza (ou cria) o registro de health check do agente.

        Semáforos: Off→Warning, Warning→On (só no final), On→On, On→Off.
        Se o bot iniciou 'off', passos intermediários usam 'warning'.
        O status 'on' só é definido via success() no final.
        """
        if self._current_status == "off" and status == "on":
            status = "warning"

        try:
            upsert_agent_health(self.agent_name, status, step)
            logger.debug("Health check atualizado: status=%s step=%s", status, step)
        except Exception as exc:
            logger.warning("Falha ao atualizar health check: %s", exc)

    def success(self, step: str) -> None:
        """Marca o agente como 'on' — usado apenas no final com sucesso."""
        try:
            upsert_agent_health(self.agent_name, "on", step)
            self._current_status = "on"
            logger.debug("Health check: sucesso — status=on step=%s", step)
        except Exception as exc:
            logger.warning("Falha ao registrar sucesso no health check: %s", exc)

    def error(self, step: str, error_msg: str) -> None:
        """
        Marca o agente como 'off', atualiza o step e registra o erro
        na tabela de erros.
        """
        try:
            upsert_agent_health(self.agent_name, "off", step)
            self._current_status = "off"
        except Exception as exc:
            logger.warning("Falha ao atualizar health check (erro): %s", exc)

        try:
            insert_agent_error(self.agent_name, error_msg)
            logger.debug("Erro registrado no health check: %s", error_msg[:100])
        except Exception as exc:
            logger.warning("Falha ao registrar erro no health check: %s", exc)
