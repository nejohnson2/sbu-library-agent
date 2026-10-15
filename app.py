"""Web chat UI for the agent. Run with: uv run uvicorn app:app --port 7860"""

from agent import agent

app = agent.to_web()
