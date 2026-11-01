import logging
import re

# Query parameters that carry secrets (MapTiler `key`, Esri `token`, ...).
_SECRET_PARAM = re.compile(r"([?&](?:key|token|api_key|apikey|access_token)=)[^&\s\"']+", re.IGNORECASE)

# HTTP client libraries log every request URL at INFO, keys included. Keep only their warnings.
_QUIET_LOGGERS = ("httpx", "httpx2", "httpcore")


class RedactSecrets(logging.Filter):
    """Masks secret query parameters in any log line that still contains a URL."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        redacted = _SECRET_PARAM.sub(r"\1<redacted>", message)
        if redacted != message:
            record.msg, record.args = redacted, None
        return True


def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    for name in _QUIET_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
    for handler in logging.getLogger().handlers:
        if not any(isinstance(f, RedactSecrets) for f in handler.filters):
            handler.addFilter(RedactSecrets())
