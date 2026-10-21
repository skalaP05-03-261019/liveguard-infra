#!/usr/bin/env python3
"""Generate isolated local credentials; never replace an existing .env."""
from pathlib import Path
import os
import secrets

target = Path(__file__).resolve().parents[1] / ".env"
values = {
    "POSTGRES_DB": "liveguard",
    "POSTGRES_USER": "liveguard",
    "POSTGRES_PASSWORD": secrets.token_hex(24),
    "POSTGRES_PORT": "5433",
    "FRONTEND_PORT": "3000",
    "AGENT_PORT": "8001",
    "INTERNAL_SERVICE_TOKEN": secrets.token_hex(32),
    "AGENT_SERVICE_TOKEN": secrets.token_hex(32),
    "BUSINESS_MCP_AGENT_TOKEN": secrets.token_hex(32),
    "RAG_MCP_AGENT_TOKEN": secrets.token_hex(32),
    "MODEL_NAME": "",
    "MODEL_API_KEY": "",
    "OPENAI_API_KEY": "",
}
try:
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
except FileExistsError:
    raise SystemExit("Existing .env preserved. Add missing names from .env.example manually.")
with os.fdopen(descriptor, "w") as output:
    output.write("".join(f"{name}={value}\n" for name, value in values.items()))
print("Created .env with independent local credentials (mode 0600); no model calls enabled.")
