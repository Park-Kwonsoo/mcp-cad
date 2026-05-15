#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Attempt to enable coverage measurement in subprocesses
try:
    import coverage
    import os
    if os.environ.get("COVERAGE_RUN_SUBPROCESS"):
        coverage.process_startup()
except ImportError:
    pass # Coverage not installed, or not running under coverage


# -*- coding: utf-8 -*-
"""
Helper script executed within a workspace's virtual environment to run
a CadQuery script with parameter substitution and custom module support.

Reads input configuration (script, params, workspace path) from stdin as JSON.
Adds <workspace_path>/modules to sys.path.
Executes the script using cadquery.cqgi.
Prints the serialized BuildResult (or error info) as JSON to stdout.
"""

import sys
import os
import logging
import json

from runner_core import execute_cadquery_job

# --- Logging Setup (Basic for Runner) ---
# Log errors to stderr so they can be captured by the calling process
logging.basicConfig(
    level=logging.INFO, # Or DEBUG for more verbose runner logs
    format='%(asctime)s - ScriptRunner - %(levelname)s - %(message)s',
    stream=sys.stderr
)
log = logging.getLogger(__name__)

# --- Main Execution ---
def run():
    log.info("Script runner started.")
    try:
        log.info("Reading input JSON from stdin...")
        input_data_str = sys.stdin.read()
        log.debug(f"Received stdin data: {input_data_str[:200]}...")
        if not input_data_str:
            raise ValueError("No input data received from stdin.")
        input_data = json.loads(input_data_str)
        output_result = execute_cadquery_job(input_data)
    except Exception as e:
        log.exception("Error during script execution in runner.") # Log full traceback to stderr
        import traceback
        output_result = {
            "success": False,
            "results": [],
            "exception_str": "".join(traceback.format_exception(type(e), e, e.__traceback__)),
        }

    # 6. Print JSON result to stdout
    log.info("Execution finished. Printing JSON result to stdout.")
    try:
        json_output = json.dumps(output_result, indent=2)
        print(json_output)
    except Exception as json_err:
         # Fallback if JSON serialization fails
         log.exception("Failed to serialize result to JSON.")
         fallback_output = json.dumps({"success": False, "exception_str": f"JSON serialization error: {json_err}\nOriginal error: {output_result.get('exception_str', 'Unknown')}"})
         print(fallback_output)

if __name__ == "__main__":
    run()
