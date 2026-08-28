from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import threading


def test_cli_over_real_local_http_transport(tmp_path):
    check_command = f'"{sys.executable}" -c "print(123)"'
    replies = [
        _tool_reply("one", "write_text", {"path": "result.py", "content": "print(123)\n"}),
        _tool_reply("two", "run_local", {"command": check_command}),
        _tool_reply(
            "three",
            "submit_result",
            {
                "summary": "CLI path works",
                "changed_files": ["result.py"],
                "checks": [check_command],
                "evidence_ids": ["op-0001", "op-0002"],
                "limitations": [],
            },
        ),
    ]

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802 - stdlib handler API
            length = int(self.headers.get("Content-Length", "0"))
            json.loads(self.rfile.read(length))
            payload = replies.pop(0)
            encoded = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, _format, *args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        environment = os.environ.copy()
        environment.update(
            {
                "EVIDENCECODER_MODEL": "fake",
                "EVIDENCECODER_BASE_URL": f"http://127.0.0.1:{server.server_port}/v1",
                "EVIDENCECODER_API_KEY": "local-test-key",
            }
        )
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "evidencecoder",
                "--workspace",
                str(tmp_path),
                "--yes",
                "--no-save-log",
                "create and verify result.py",
            ],
            cwd=Path(__file__).parents[1],
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
            check=False,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Status: completed" in result.stdout
    assert (tmp_path / "result.py").read_text(encoding="utf-8") == "print(123)\n"
    assert not replies


def _tool_reply(call_id: str, name: str, arguments: dict[str, object]) -> dict[str, object]:
    return {
        "choices": [
            {
                "message": {
                    "content": None,
                    "tool_calls": [
                        {
                            "id": call_id,
                            "type": "function",
                            "function": {
                                "name": name,
                                "arguments": json.dumps(arguments),
                            },
                        }
                    ],
                }
            }
        ]
    }
