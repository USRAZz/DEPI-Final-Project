"""Tests run the same on a laptop and in CI: the LLM settings a developer's .env loaded (ai_core.llm calls
load_dotenv) are removed before every test. A test that needs one sets it itself with monkeypatch."""
import os
import re

import pytest

LLM_SETTINGS = re.compile(
    r"^(LLM_\w+|\w+_API_KEY|\w+_MODEL|\w+_PROVIDER|\w+_ROUTING|JEV_\w+|QUOTA_RETRY_SECONDS|USE_SYSTEM_CERTS|"
    r"EXPLAIN_USE_LLM|BACKEND|AGENT_SERVICE_TOKEN)$")


@pytest.fixture(autouse=True)
def no_developer_llm_settings(monkeypatch):
    for name in list(os.environ):
        if LLM_SETTINGS.match(name):
            monkeypatch.delenv(name)
