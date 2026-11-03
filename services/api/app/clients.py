"""HTTP clients to other services. Fail closed: any error from the gateway == BLOCK."""
import os

import httpx
from securefin_contracts import AuthorizeRequest, Decision, GatewayDecision

EXTRACTOR_URL = os.getenv("EXTRACTOR_URL", "http://extractor:8000")
GATEWAY_URL = os.getenv("GATEWAY_URL", "http://gateway:8000")
GATEWAY_ENABLED = os.getenv("GATEWAY_ENABLED", "true").lower() == "true"  # false ONLY for the ASR baseline run


async def gateway_authorize(req: AuthorizeRequest) -> GatewayDecision:
    if not GATEWAY_ENABLED:
        return GatewayDecision(decision=Decision.ALLOW, reasons=["gateway disabled (baseline eval mode)"])
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.post(f"{GATEWAY_URL}/v1/authorize", json=req.model_dump(mode="json"))
            r.raise_for_status()
            return GatewayDecision.model_validate(r.json())
    except Exception as exc:  # noqa: BLE001 — fail closed on purpose
        return GatewayDecision(decision=Decision.BLOCK, reasons=[f"gateway unavailable: {type(exc).__name__}"])
