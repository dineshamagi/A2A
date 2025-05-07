import os
import json
import random
import logging
from typing import Any, Dict, Optional, AsyncIterable, Literal
from pydantic import BaseModel
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Optional: Setup logger
logger = logging.getLogger(__name__)

# --- Response Format ---
class AgentResponse(BaseModel):
    status: Literal["input_required", "completed", "error"] = "input_required"
    message: str


# --- Base Agent Class ---
class BaseAgent:
    SUPPORTED_CONTENT_TYPES = ["text", "text/plain"]
    SYSTEM_INSTRUCTION: str = "You are a helpful AI agent."

    def __init__(self):
        self._agent = self._build_agent()
        self._runner = self._build_runner()

    def _build_agent(self):
        """Initialize and return an agent (e.g., LLM, LangChain, or Google ADK agent)."""
        raise NotImplementedError("Implement _build_agent in subclass")

    def _build_runner(self):
        """Optionally setup a runner (e.g., for Google ADK or LangChain's AgentExecutor)."""
        raise NotImplementedError("Implement _build_runner in subclass")

    def get_processing_message(self) -> str:
        return "Processing your request..."

    def invoke(self, query: str, session_id: str) -> Dict[str, Any]:
        logger.info(f"Invoking with query: {query}")
        raise NotImplementedError("Implement invoke in subclass")

    async def stream(self, query: str, session_id: str) -> AsyncIterable[Dict[str, Any]]:
        """Optionally implement streaming of intermediate steps."""
        raise NotImplementedError("Streaming not implemented.")

    def process_response(self, result: Dict[str, Any]) -> Dict[str, Any]:
        if "error" in result:
            return {
                "is_task_complete": False,
                "require_user_input": True,
                "content": f"Error: {result['error']}"
            }
        elif "output" in result:
            return {
                "is_task_complete": True,
                "require_user_input": False,
                "content": result["output"]
            }
        else:
            return {
                "is_task_complete": False,
                "require_user_input": True,
                "content": "I need more input to proceed."
            }

# --- Example Tool (can be extended per use case) ---
def create_generic_form(fields: Dict[str, Any], defaults: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Generate a form template with default values if not provided."""
    form_id = "form_" + str(random.randint(100000, 999999))
    defaults = defaults or {}
    return {
        "form_id": form_id,
        **{field: defaults.get(field, f"<{field}>") for field in fields}
    }
