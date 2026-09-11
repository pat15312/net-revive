import json
import logging

logger = logging.getLogger("netrevive")


def audit(action, **fields):
    # Callers pass only explicit safe fields; never HTTP bodies, URLs, credentials or exceptions.
    logger.info(json.dumps({"action": action, **fields}, separators=(",", ":")))
