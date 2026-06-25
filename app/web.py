import json
import mimetypes
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from app.agent import create_world_cup_agent


ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
HOST = "127.0.0.1"
PORT = 8000

CHAT_HISTORIES: Dict[str, List[BaseMessage]] = {}
AGENT = create_world_cup_agent()
STREAMING_AGENT = create_world_cup_agent(streaming=True, verbose=False)

TOOL_LABELS = {
    "get_daily_report": "读取世界杯每日战报数据",
    "get_team_profile": "查询球队赛程和战绩",
    "get_match_analysis": "分析单场比赛上下文",
    "get_prediction_context": "整理预测所需信息",
    "get_fixtures": "搜索赛程信息",
    "get_match_result": "查询比赛结果",
    "query_vector_knowledge": "检索本地 RAG 知识库",
    "search_web": "搜索网络新闻背景",
}


class StreamEventCallback(BaseCallbackHandler):
    def __init__(self, sender: "StreamSender") -> None:
        self.sender = sender
        self.streamed_text = ""

    def on_tool_start(
        self,
        serialized: Dict[str, Any],
        input_str: str,
        **kwargs: Any,
    ) -> None:
        tool_name = serialized.get("name", "tool")
        label = TOOL_LABELS.get(tool_name, f"调用工具 {tool_name}")
        self.sender.send("tool_start", {"name": tool_name, "label": label, "input": input_str})

    def on_tool_end(self, output: Any, **kwargs: Any) -> None:
        preview = str(output)
        if len(preview) > 180:
            preview = f"{preview[:180]}..."
        self.sender.send("tool_end", {"preview": preview})

    def on_tool_error(self, error: BaseException, **kwargs: Any) -> None:
        self.sender.send("tool_error", {"message": str(error)})

    def on_llm_start(
        self,
        serialized: Dict[str, Any],
        prompts: List[str],
        **kwargs: Any,
    ) -> None:
        self.sender.send("status", {"message": "模型正在阅读上下文..."})

    def on_llm_new_token(self, token: str, **kwargs: Any) -> None:
        if not token:
            return
        self.streamed_text += token
        self.sender.send("token", {"text": token})


class StreamSender:
    def __init__(self, handler: BaseHTTPRequestHandler) -> None:
        self.handler = handler

    def begin(self) -> None:
        self.handler.send_response(HTTPStatus.OK)
        self.handler.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.handler.send_header("Cache-Control", "no-cache")
        self.handler.send_header("X-Accel-Buffering", "no")
        self.handler.end_headers()

    def send(self, event: str, payload: Optional[dict] = None) -> None:
        data = {"event": event, **(payload or {})}
        line = json.dumps(data, ensure_ascii=False).encode("utf-8") + b"\n"
        self.handler.wfile.write(line)
        self.handler.wfile.flush()


class WorldCupChatHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        request_path = parsed.path
        if request_path == "/":
            request_path = "/index.html"

        file_path = (WEB_DIR / request_path.lstrip("/")).resolve()
        if not str(file_path).startswith(str(WEB_DIR.resolve())):
            self._send_json({"error": "Invalid path."}, HTTPStatus.BAD_REQUEST)
            return

        if not file_path.is_file():
            self._send_json({"error": "Not found."}, HTTPStatus.NOT_FOUND)
            return

        content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        content = file_path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/chat":
            self._handle_chat()
            return
        if parsed.path == "/api/chat-stream":
            self._handle_chat_stream()
            return
        if parsed.path == "/api/reset":
            self._handle_reset()
            return

        self._send_json({"error": "Not found."}, HTTPStatus.NOT_FOUND)

    def _handle_chat(self) -> None:
        payload = self._read_json()
        message = str(payload.get("message", "")).strip()
        session_id = str(payload.get("session_id") or uuid.uuid4())

        if not message:
            self._send_json({"error": "Message is required."}, HTTPStatus.BAD_REQUEST)
            return

        history = CHAT_HISTORIES.setdefault(session_id, [])
        try:
            response = AGENT.invoke({"input": message, "chat_history": history})
            answer = response.get("output", "")
            if not isinstance(answer, str):
                answer = str(answer)
        except Exception as exc:  # Keep the demo UI responsive when a tool/API fails.
            self._send_json(
                {"error": f"Agent request failed: {exc}", "session_id": session_id},
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )
            return

        history.extend([HumanMessage(content=message), AIMessage(content=answer)])
        self._send_json({"answer": answer, "session_id": session_id})

    def _handle_chat_stream(self) -> None:
        payload = self._read_json()
        message = str(payload.get("message", "")).strip()
        session_id = str(payload.get("session_id") or uuid.uuid4())

        if not message:
            self._send_json({"error": "Message is required."}, HTTPStatus.BAD_REQUEST)
            return

        history = CHAT_HISTORIES.setdefault(session_id, [])
        sender = StreamSender(self)
        callback = StreamEventCallback(sender)
        sender.begin()
        sender.send("session", {"session_id": session_id})
        sender.send("status", {"message": "开球，正在判断是否需要调用赛程、搜索或 RAG 工具..."})

        try:
            response = STREAMING_AGENT.invoke(
                {"input": message, "chat_history": history},
                config={"callbacks": [callback]},
            )
            answer = response.get("output", "")
            if not isinstance(answer, str):
                answer = str(answer)
        except Exception as exc:
            sender.send("error", {"message": f"Agent request failed: {exc}", "session_id": session_id})
            return

        if not callback.streamed_text:
            self._send_text_as_tokens(sender, answer)

        history.extend([HumanMessage(content=message), AIMessage(content=answer)])
        sender.send("done", {"answer": answer, "session_id": session_id})

    def _send_text_as_tokens(self, sender: StreamSender, text: str) -> None:
        chunk_size = 18
        for index in range(0, len(text), chunk_size):
            sender.send("token", {"text": text[index : index + chunk_size]})

    def _handle_reset(self) -> None:
        payload = self._read_json()
        session_id = str(payload.get("session_id") or "")
        if session_id:
            CHAT_HISTORIES.pop(session_id, None)

        self._send_json({"ok": True, "session_id": session_id or str(uuid.uuid4())})

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length == 0:
            return {}

        raw_body = self.rfile.read(length)
        try:
            return json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError:
            return {}

    def _send_json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        content = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, format: str, *args: object) -> None:
        print(f"[web] {self.address_string()} - {format % args}")


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), WorldCupChatHandler)
    print(f"World Cup Agent web UI: http://{HOST}:{PORT}")
    print("Press Ctrl+C to stop.")
    server.serve_forever()


if __name__ == "__main__":
    main()
