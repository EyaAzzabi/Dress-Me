"""Local development server using backend/.env, including over inherited env vars.

Run from backend/: python -m scripts.run_local
Production launch behavior remains unchanged.
"""
from pathlib import Path
import logging

from dotenv import load_dotenv
import uvicorn


def main() -> None:
    backend = Path(__file__).resolve().parents[1]
    load_dotenv(backend / ".env", override=True)
    logger = logging.getLogger("app.agents.llm_agent")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(
            "LLM event=%(llm_event)s status=%(status)s error=%(error_type)s attempt=%(attempt)s",
            defaults={"llm_event": "", "status": "", "error_type": "", "attempt": ""},
        ))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, app_dir=str(backend))


if __name__ == "__main__":
    main()
