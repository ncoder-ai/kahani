"""Debug trace logging for agent executions.

Saves JSON traces to logs/agent_traces/ for inspection.
Gated behind the prompt_debug setting.
"""

import json
import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class AgentTraceLogger:
    """Log agent execution traces to JSON files."""

    def __init__(self, agent_name: str, enabled: bool = False):
        self.agent_name = agent_name
        self.enabled = enabled

    def log(
        self,
        query: str,
        trace: List[Dict[str, Any]],
        final_answer: Any,
    ) -> None:
        """Save a trace to disk if debug logging is enabled."""
        if not self.enabled:
            return

        try:
            logs_dir = self._get_logs_dir()
            os.makedirs(logs_dir, exist_ok=True)

            trace_data = {
                "agent": self.agent_name,
                "timestamp": datetime.now().isoformat(),
                "query": query,
                "turns": len(trace),
                "trace": trace,
                "final_answer": final_answer,
            }

            # Timestamped filename so traces don't overwrite each other
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = os.path.join(logs_dir, f"{self.agent_name}_trace_{ts}.json")
            with open(filepath, "w") as f:
                json.dump(trace_data, f, indent=2, default=str)

            # Also write latest as a fixed name for quick access
            latest = os.path.join(logs_dir, f"{self.agent_name}_trace.json")
            with open(latest, "w") as f:
                json.dump(trace_data, f, indent=2, default=str)

            logger.info(f"[{self.agent_name}] Trace saved to {filepath}")
        except Exception as e:
            logger.warning(f"[{self.agent_name}] Failed to save trace: {e}")

    @staticmethod
    def _get_logs_dir() -> str:
        """Get logs directory, handling Docker vs bare-metal."""
        if os.path.exists("/app") and os.getcwd().startswith("/app"):
            return "/app/root_logs/agent_traces"
        # Go up from: backend/app/services/agent/trace_logger.py
        here = os.path.dirname(__file__)
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(here))))
        return os.path.join(project_root, "logs", "agent_traces")
