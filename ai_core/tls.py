"""Optional: trust the operating system's certificate store for HTTPS (USE_SYSTEM_CERTS=true).

On a machine where an antivirus or a company proxy inspects HTTPS, Python's bundled certificates (certifi) reject
the connection with CERTIFICATE_VERIFY_FAILED, so every LLM call fails. The OS store already trusts that proxy, and
`truststore` lets Python use it. Off by default (Docker images and CI do not need it). Needs `pip install truststore`.
"""
import logging
import os

log = logging.getLogger(__name__)
_done = False


def use_system_certs() -> bool:
    """Inject the OS trust store once when USE_SYSTEM_CERTS is true. Returns whether it is active."""
    global _done
    if _done:
        return True
    if os.getenv("USE_SYSTEM_CERTS", "").strip().lower() not in ("1", "true", "yes"):
        return False
    try:
        import truststore
    except ImportError:
        log.warning("USE_SYSTEM_CERTS is set but truststore is not installed: pip install truststore")
        return False
    truststore.inject_into_ssl()
    _done = True
    return True
