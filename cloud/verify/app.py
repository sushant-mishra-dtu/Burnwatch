"""P4 deployment stub. Claude Code implements the verifier in P5."""
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def lambda_handler(event, context):
    logger.error("BurnWatch P4 infrastructure stub invoked; implement P5 before uploading event frames")
    raise NotImplementedError("P5 verifier is not implemented; no verdict or alert was generated")
