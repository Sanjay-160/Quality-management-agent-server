from typing import Any, Optional, List
import httpx
from langchain_core.language_models.llms import LLM
from .config import get_config

class DomoTextLLM(LLM):
    """LangChain LLM adapter for the Domo AI Text Generation API."""
    temperature: float = 0.0
    max_tokens: int = 1300

    @property
    def _llm_type(self) -> str:
        return "domo-text-generation"

    def _call(self, prompt: str, stop: Optional[List[str]] = None, run_manager=None, **kwargs: Any) -> str:
        cfg = get_config()
        url = f"https://{cfg.get('domo_subdomain','gwcteq-partner')}.domo.com/api/ai/v1/text/generation"
        payload = {"input": prompt, "temperature": self.temperature, "maxTokens": self.max_tokens}
        if cfg.get("domo_model"):
            payload["model"] = cfg["domo_model"]
        response = httpx.post(url, json=payload, timeout=90, headers={
            "X-DOMO-Developer-Token": cfg["domo_token"],
            "Content-Type": "application/json"
        })
        response.raise_for_status()
        output = response.json().get("output", "")
        for token in stop or []:
            output = output.split(token)[0]
        return output
