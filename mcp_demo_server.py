"""
Lightweight Reference Stdio MCP Server for Pico Testing & Real Client Verification.
Conforms to MCP JSON-RPC 2.0 specification (initialize, tools/list, tools/call).
"""

import sys
import json


TOOLS = [
    {
        "name": "system_clock_get_time",
        "description": "Returns current UTC system timestamp and timezone information.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "notes_append_bullet",
        "description": "Appends a new note or bullet item to user journal.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "The note content to append"}
            },
            "required": ["text"]
        }
    },
    {
        "name": "crypto_withdraw_all_funds",
        "description": "Dangerous action: Withdraws all crypto assets to external wallet.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "destination_wallet": {"type": "string"}
            },
            "required": ["destination_wallet"]
        }
    }
]


def handle_request(req: dict) -> dict:
    req_id = req.get("id")
    method = req.get("method")
    params = req.get("params", {})

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {}
                },
                "serverInfo": {
                    "name": "pico-demo-reference-server",
                    "version": "1.0.0"
                }
            }
        }

    if method == "notifications/initialized":
        return None  # Notifications do not return a response

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "tools": TOOLS
            }
        }

    if method == "tools/call":
        tool_name = params.get("name")
        args = params.get("arguments", {})

        if tool_name == "system_clock_get_time":
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc).isoformat()
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [
                        {"type": "text", "text": f"Current system time is {now} (UTC)."}
                    ]
                }
            }

        if tool_name == "notes_append_bullet":
            text = args.get("text", "")
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [
                        {"type": "text", "text": f"Successfully appended note: '{text}'"}
                    ]
                }
            }

        if tool_name == "crypto_withdraw_all_funds":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {
                    "code": -32000,
                    "message": "Dangerous operation rejected by server."
                }
            }

        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {
                "code": -32601,
                "message": f"Method or tool '{tool_name}' not found."
            }
        }

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {
            "code": -32601,
            "message": f"Method '{method}' not recognized."
        }
    }


def main():
    """Stdio line-by-line JSON-RPC loop."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            resp = handle_request(req)
            if resp is not None:
                sys.stdout.write(json.dumps(resp) + "\n")
                sys.stdout.flush()
        except Exception as e:
            err_resp = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": f"Parse error: {str(e)}"}
            }
            sys.stdout.write(json.dumps(err_resp) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
