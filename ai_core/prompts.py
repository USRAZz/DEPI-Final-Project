"""Prompts live in prompts/<name>_<version>.md with {{placeholders}} filled at runtime."""
import os
import re
import secrets
from pathlib import Path

PROMPTS_DIR = Path(os.getenv("PROMPTS_DIR") or Path(__file__).resolve().parents[1] / "prompts")
_VAR = re.compile(r"\{\{\s*(\w+)\s*\}\}")


def load_prompt(name: str, **variables) -> str:
    version = os.getenv(f"PROMPT_VERSION_{name.upper()}") or os.getenv("PROMPT_VERSION", "v1")
    path = PROMPTS_DIR / f"{name}_{version}.md"
    text = path.read_text(encoding="utf-8")
    missing = set(_VAR.findall(text)) - variables.keys()
    if missing:
        raise KeyError(f"{path.name}: missing variables {sorted(missing)}")
    return _VAR.sub(lambda m: str(variables[m.group(1)]), text)


def untrusted(text: str) -> str:
    """Wrap outside text (user message, OCR text, tool results) in a tag with a random suffix,
    so it cannot fake the closing tag. The prompts tell the model: tagged text is data, never instructions."""
    tag = f"UNTRUSTED_{secrets.token_hex(4)}"
    return f"<{tag}>\n{text}\n</{tag}>"