# Priority-Decision

Render-ready Python MCP server for the **Priority Decision** task app.

## Start

```bash
python server.py
```

Environment variables:
- `PORT` (required by Render at runtime)
- `OPENAI_APPS_CHALLENGE` (served from `/.well-known/openai-apps-challenge`)

## Routes

- `GET /health`
- `POST /mcp` (JSON-RPC: `initialize`, `tools/list`, `tools/call`)
- `GET /privacy`
- `GET /terms`
- `GET /support`
- `GET /.well-known/openai-apps-challenge`

## Tool Input

`tasks: [{ name, urgency, impact, effort }]` where scores are numeric in `[0, 10]`.

## Tool Output (`structuredContent`)

- `priority_order: string[]`
- `first_task: string`
- `reason: string`
- `confidence: float`

## Notes

- Deterministic ranking logic and tie-breakers.
- Stateless processing.
- Does **not** schedule tasks or generate long-term plans.

## Example API Call (`POST /mcp`)

```bash
curl -X POST http://127.0.0.1:${PORT:-8000}/mcp \
  -H 'content-type: application/json' \
  -d '{
    "jsonrpc": "2.0",
    "id": "example-1",
    "method": "tools/call",
    "params": {
      "name": "priority_decision",
      "arguments": {
        "tasks": [
          {"name": "Submit tax filing", "urgency": 9, "impact": 10, "effort": 4},
          {"name": "Prepare demo", "urgency": 8, "impact": 9, "effort": 5},
          {"name": "Clean inbox", "urgency": 6, "impact": 4, "effort": 3}
        ]
      }
    }
  }'
```

Expected JSON response:

```json
{
  "jsonrpc": "2.0",
  "id": "example-1",
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Top priority: Submit tax filing\nOrder: Submit tax filing, Prepare demo, Clean inbox\nReason: 'Submit tax filing' ranks first due to high urgency (9.0), high impact (10.0), and manageable effort (4.0).\nConfidence: 0.65"
      }
    ],
    "structuredContent": {
      "priority_order": ["Submit tax filing", "Prepare demo", "Clean inbox"],
      "first_task": "Submit tax filing",
      "reason": "'Submit tax filing' ranks first due to high urgency (9.0), high impact (10.0), and manageable effort (4.0).",
      "confidence": 0.65
    },
    "isError": false
  }
}
```

## Quickstart Tip (Render + Dev Mode)

- **Render deploy:** set Start Command to `python server.py`, ensure `PORT` is provided by Render, and set `OPENAI_APPS_CHALLENGE` in environment variables.
- **Dev Mode verify:** after deploy, validate `GET /health`, then connect your MCP endpoint in ChatGPT Developer Mode and run `initialize` → `tools/list` → `tools/call` with a known deterministic payload to confirm stable output.
