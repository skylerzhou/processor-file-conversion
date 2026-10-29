"""
Lambda handler. Bridges the per-invocation event payload to environment
variables, then runs the same code as Fargate mode. Same shape as
pennsieve-quick-plot's handler.py.

Payload keys the platform sends:
  inputDir        -> INPUT_DIR
  outputDir       -> OUTPUT_DIR
  executionRunId  -> EXECUTION_RUN_ID
  integrationId   -> INTEGRATION_ID
  sessionToken    -> SESSION_TOKEN

processorParams (per-node config, surfaced by the provisioner):
  channels        -> CHANNELS         (optional; comma-separated)
  output_filename -> OUTPUT_FILENAME  (optional)
"""

import logging
import os
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", force=True)
log = logging.getLogger("file-conversion")

_PAYLOAD_TO_ENV = {
    "inputDir": "INPUT_DIR",
    "outputDir": "OUTPUT_DIR",
    "executionRunId": "EXECUTION_RUN_ID",
    "integrationId": "INTEGRATION_ID",
    "sessionToken": "SESSION_TOKEN",
    "channels": "CHANNELS",
    "output_filename": "OUTPUT_FILENAME",
}


def handler(event, context):
    log.info("Lambda handler invoked. Event keys: %s", list(event.keys()))

    for payload_key, env_key in _PAYLOAD_TO_ENV.items():
        if payload_key in event and event[payload_key] is not None:
            os.environ[env_key] = str(event[payload_key])

    # Any other string-valued key passes through verbatim (e.g. injected secrets)
    for key, value in event.items():
        if key not in _PAYLOAD_TO_ENV and isinstance(value, str):
            os.environ[key] = value

    from processor.main import main
    if main() != 0:
        sys.exit(1)   # fail the invocation so Step Functions marks the run FAILED

    return {
        "status": "success",
        "executionRunId": event.get("executionRunId", ""),
        "outputDir": event.get("outputDir", ""),
    }
