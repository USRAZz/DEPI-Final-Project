"""python -m ai_core.ping openrouter            -> list model ids your key can see
   python -m ai_core.ping openrouter <model>    -> send one tiny request and show reply + time"""
import sys
import time

from ai_core.llm import LLM

provider = sys.argv[1]
llm = LLM(provider, sys.argv[2] if len(sys.argv) > 2 else "unused")
if len(sys.argv) < 3:
    for m in llm.client.models.list():
        print(m.id)
else:
    t0 = time.perf_counter()
    try:
        print(llm.chat([{"role": "user", "content": "Reply with the single word OK"}]).strip()[:80])
        print(f"{time.perf_counter() - t0:.1f}s | tokens={llm.usage.prompt_tokens + llm.usage.completion_tokens}")
    except Exception as e:
        print(f"FAIL {type(e).__name__}: {str(e)[:200]}")