#!/usr/bin/env python3
"""Priority Decision MCP server.

Render start command: python server.py
"""

from __future__ import annotations

import json
import math
import os
import traceback
from pathlib import Path
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Tuple

APP_NAME = "Priority Decision"
APP_VERSION = "1.0.0"
APP_DESCRIPTION = (
    "Determines the top-priority task from a list of tasks based on urgency, impact, and effort."
)
SUPPORT_EMAIL = "sidcraigau@gmail.com"

MCP_PROTOCOL_VERSION = "2024-11-05"
TOOL_NAME = "priority_decision"

# Deterministic scoring weights
WEIGHT_URGENCY = 0.45
WEIGHT_IMPACT = 0.45
WEIGHT_EFFORT = 0.10


PROJECT_ROOT = Path(__file__).resolve().parent
STATIC_PAGES = {
    "/privacy": PROJECT_ROOT / "privacy.html",
    "/terms": PROJECT_ROOT / "terms.html",
    "/support": PROJECT_ROOT / "support.html",
}

HOME_HTML = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>{APP_NAME}</title>
</head>
<body>
  <h1>{APP_NAME}</h1>
  <p>Helps users prioritize multiple tasks and choose the most important one based on urgency, impact, and effort.</p>
  <nav>
    <a href="/privacy">Privacy</a> |
    <a href="/terms">Terms</a> |
    <a href="/support">Support</a>
  </nav>
  <p>Support: <a href="mailto:{SUPPORT_EMAIL}">{SUPPORT_EMAIL}</a></p>
</body>
</html>
"""


class ValidationError(Exception):
    """Raised when input validation fails."""


def json_dumps(payload: Dict[str, Any], status: str = "ok") -> str:
    base = {"status": status, **payload}
    return json.dumps(base, sort_keys=True, separators=(",", ":"))


def _coerce_score(value: Any, field: str) -> float:
    if isinstance(value, bool):
        raise ValidationError(f"'{field}' must be a number between 0 and 10.")
    if not isinstance(value, (int, float)):
        raise ValidationError(f"'{field}' must be a number between 0 and 10.")
    numeric = float(value)
    if math.isnan(numeric) or math.isinf(numeric):
        raise ValidationError(f"'{field}' must be a finite number between 0 and 10.")
    if numeric < 0 or numeric > 10:
        raise ValidationError(f"'{field}' must be between 0 and 10.")
    return numeric


def _validate_task(task: Any, index: int) -> Dict[str, Any]:
    if not isinstance(task, dict):
        raise ValidationError(f"Task at index {index} must be an object.")

    for field in ("name", "urgency", "impact", "effort"):
        if field not in task:
            raise ValidationError(f"Task at index {index} is missing required field '{field}'.")

    name = task["name"]
    if not isinstance(name, str) or not name.strip():
        raise ValidationError(f"Task at index {index} has invalid 'name'.")

    urgency = _coerce_score(task["urgency"], "urgency")
    impact = _coerce_score(task["impact"], "impact")
    effort = _coerce_score(task["effort"], "effort")

    return {
        "name": name.strip(),
        "urgency": urgency,
        "impact": impact,
        "effort": effort,
    }


def _score_task(task: Dict[str, Any]) -> float:
    # Lower effort increases priority via (10 - effort)
    return (
        (task["urgency"] * WEIGHT_URGENCY)
        + (task["impact"] * WEIGHT_IMPACT)
        + ((10.0 - task["effort"]) * WEIGHT_EFFORT)
    )


def prioritize_tasks(tasks: Any) -> Dict[str, Any]:
    if not isinstance(tasks, list):
        raise ValidationError("Input must be a JSON array of tasks.")
    if len(tasks) == 0:
        raise ValidationError("At least one task is required.")

    validated = [_validate_task(task, i) for i, task in enumerate(tasks)]

    scored: List[Tuple[float, Dict[str, Any]]] = [(_score_task(task), task) for task in validated]
    # deterministic tie-breakers: score desc, urgency desc, impact desc, effort asc, name asc
    scored.sort(
        key=lambda item: (
            -item[0],
            -item[1]["urgency"],
            -item[1]["impact"],
            item[1]["effort"],
            item[1]["name"].lower(),
        )
    )

    priority_order = [task["name"] for _, task in scored]
    first_task = priority_order[0]

    top_score = scored[0][0]
    second_score = scored[1][0] if len(scored) > 1 else 0.0
    score_gap = max(0.0, top_score - second_score)
    confidence = round(min(0.99, 0.55 + (score_gap / 10.0)), 2)

    top_task = scored[0][1]
    reason = (
        f"'{top_task['name']}' ranks first due to high urgency ({top_task['urgency']:.1f}), "
        f"high impact ({top_task['impact']:.1f}), and manageable effort ({top_task['effort']:.1f})."
    )

    return {
        "priority_order": priority_order,
        "first_task": first_task,
        "reason": reason,
        "confidence": confidence,
    }


def mcp_initialize(_: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "protocolVersion": MCP_PROTOCOL_VERSION,
        "serverInfo": {"name": APP_NAME, "version": APP_VERSION},
        "capabilities": {"tools": {}},
        "instructions": (
            "Provide tasks as a JSON array with name, urgency, impact, effort. "
            "This tool only prioritizes tasks and does not schedule or plan long-term."
        ),
    }


def mcp_tools_list() -> Dict[str, Any]:
    return {
        "tools": [
            {
                "name": TOOL_NAME,
                "title": "Priority Decision",
                "description": APP_DESCRIPTION,
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "tasks": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "urgency": {"type": "number", "minimum": 0, "maximum": 10},
                                    "impact": {"type": "number", "minimum": 0, "maximum": 10},
                                    "effort": {"type": "number", "minimum": 0, "maximum": 10},
                                },
                                "required": ["name", "urgency", "impact", "effort"],
                                "additionalProperties": False,
                            },
                        }
                    },
                    "required": ["tasks"],
                    "additionalProperties": False,
                },
                "outputSchema": {
                    "type": "object",
                    "properties": {
                        "priority_order": {"type": "array", "items": {"type": "string"}},
                        "first_task": {"type": "string"},
                        "reason": {"type": "string"},
                        "confidence": {"type": "number"},
                    },
                    "required": ["priority_order", "first_task", "reason", "confidence"],
                    "additionalProperties": False,
                },
            }
        ]
    }


def mcp_tools_call(params: Dict[str, Any]) -> Dict[str, Any]:
    name = params.get("name")
    if name != TOOL_NAME:
        raise ValidationError(f"Unknown tool '{name}'.")

    arguments = params.get("arguments", {})
    if not isinstance(arguments, dict):
        raise ValidationError("'arguments' must be an object.")

    result = prioritize_tasks(arguments.get("tasks"))
    return {
        "content": [
            {
                "type": "text",
                "text": (
                    f"Top priority: {result['first_task']}\n"
                    f"Order: {', '.join(result['priority_order'])}\n"
                    f"Reason: {result['reason']}\n"
                    f"Confidence: {result['confidence']:.2f}"
                ),
            }
        ],
        # fixed structuredContent contract for official and human checks
        "structuredContent": {
            "priority_order": result["priority_order"],
            "first_task": result["first_task"],
            "reason": result["reason"],
            "confidence": result["confidence"],
        },
        "isError": False,
    }


def handle_mcp_rpc(request: Dict[str, Any]) -> Dict[str, Any]:
    jsonrpc = request.get("jsonrpc", "2.0")
    req_id = request.get("id")
    method = request.get("method")
    params = request.get("params", {})

    try:
        if jsonrpc != "2.0":
            raise ValidationError("Only JSON-RPC 2.0 is supported.")

        if method == "initialize":
            result = mcp_initialize(params if isinstance(params, dict) else {})
        elif method == "tools/list":
            result = mcp_tools_list()
        elif method == "tools/call":
            if not isinstance(params, dict):
                raise ValidationError("'params' must be an object for tools/call.")
            result = mcp_tools_call(params)
        else:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"},
            }

        return {"jsonrpc": "2.0", "id": req_id, "result": result}
    except ValidationError as exc:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32602, "message": str(exc)},
        }
    except Exception:
        traceback.print_exc()
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32000, "message": "Internal server error."},
        }


class AppHandler(BaseHTTPRequestHandler):
    server_version = "PriorityDecisionHTTP/1.0"

    def log_message(self, format: str, *args: Any) -> None:
        # Keep default style but deterministic prefix
        print(f"[priority-decision] {self.address_string()} - {format % args}")

    def _write(self, code: int, body: str, content_type: str = "text/plain; charset=utf-8") -> None:
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _write_static_html(self, path: Path) -> None:
        try:
            body = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            self._write(HTTPStatus.NOT_FOUND, "Not Found")
            return
        self._write(HTTPStatus.OK, body, content_type="text/html; charset=utf-8")

    def do_GET(self) -> None:
        if self.path == "/":
            self._write(HTTPStatus.OK, HOME_HTML, content_type="text/html; charset=utf-8")
            return

        if self.path == "/health":
            self._write(HTTPStatus.OK, "OK")
            return

        static_path = STATIC_PAGES.get(self.path)
        if static_path is not None:
            self._write_static_html(static_path)
            return

        if self.path == "/.well-known/openai-apps-challenge":
            challenge = os.getenv("OPENAI_APPS_CHALLENGE", "")
            self._write(HTTPStatus.OK, challenge)
            return

        self._write(HTTPStatus.NOT_FOUND, "Not Found")

    def do_POST(self) -> None:
        if self.path != "/mcp":
            self._write(HTTPStatus.NOT_FOUND, "Not Found")
            return

        content_length = self.headers.get("Content-Length")
        if content_length is None:
            self._write(
                HTTPStatus.BAD_REQUEST,
                json_dumps({"message": "Missing Content-Length header."}, status="error"),
                content_type="application/json; charset=utf-8",
            )
            return

        try:
            raw = self.rfile.read(int(content_length)).decode("utf-8")
            request_json = json.loads(raw)
        except Exception:
            self._write(
                HTTPStatus.BAD_REQUEST,
                json_dumps({"message": "Invalid JSON body."}, status="error"),
                content_type="application/json; charset=utf-8",
            )
            return

        response_json = handle_mcp_rpc(request_json)
        self._write(
            HTTPStatus.OK,
            json.dumps(response_json, sort_keys=True, separators=(",", ":")),
            content_type="application/json; charset=utf-8",
        )


def main() -> None:
    host = "0.0.0.0"
    port = int(os.getenv("PORT", "8000"))

    httpd = ThreadingHTTPServer((host, port), AppHandler)
    print(f"{APP_NAME} v{APP_VERSION} listening on http://{host}:{port}")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
