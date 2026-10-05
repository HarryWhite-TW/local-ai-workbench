"""Small read-only human projection; never an execution or review authority."""
import re
import unicodedata
from typing import Callable

from .domain import Execution, Failure, Progress, Task


def safe_text(text: str) -> str:
    """Bounded display hygiene, not a general-purpose secret discovery system."""
    # Normalize before matching so controls cannot split a sensitive field name.
    text = "".join(c for c in text if c in "\n\t" or unicodedata.category(c) not in {"Cc", "Cf"})
    if re.search(r"\b(?:set-cookie|cookie|authorization)\s*[\"']?\s*[:=]|"
                 r"\b(?:access_token|refresh_token|id_token)\b", text, re.IGNORECASE):
        # Conservative withholding also covers wrapped/multiline values.
        return "[private field withheld]"
    text = re.sub(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+|sk-[A-Za-z0-9_-]+",
                  "[credential redacted]", text)
    text = re.sub(r"(?i)\bBearer\s+\S+", "[credential redacted]", text)
    return text


FAILURES = {
    Failure.UNKNOWN: "執行失敗；原因尚未確認，未顯示服務端原始內容。",
    Failure.AUTHENTICATION: "無法取得可用的 ChatGPT 授權，請由可信任的登入端確認。",
    Failure.TIMEOUT: "等待執行結果逾時；未確認取消，也未接受任何結果。",
    Failure.PROTOCOL: "執行端通訊格式不相容，未取得可確認的結果。",
    Failure.POLICY: "執行端未符合唯讀政策，工作未獲准繼續。",
    Failure.CONNECTION: "與執行端的連線中斷；不代表已確認取消。",
    Failure.INTERRUPTED: "本機等待已中斷；未確認執行端取消或完成。",
}


class HumanView:
    def __init__(self, write: Callable[[str], None], *, details: bool = False):
        self.write = write
        self.details = details
        self._seen: set[str] = set()
        self.available = True

    def _write(self, text):
        if self.available:
            try:
                self.write(text)
            except Exception:
                # A disconnected display does not cancel or fail the task.
                self.available = False

    def progress(self, event: Progress):
        messages = {
            "task_created": "工作已建立，正在準備。權限：唯讀 READ_ONLY。",
            "working": "正在執行唯讀工作…",
            "inspecting_repository": "正在檢視 repository 內容…",
            "receiving_result": "正在接收與整理結果…",
            "execution_complete": "執行端已回傳結果，正在完成收尾…",
        }
        # Once per meaningful phase, even when transport stages alternate.
        if event.stage in messages and event.stage not in self._seen:
            self._seen.add(event.stage)
            self._write(messages[event.stage])

    def result(self, task: Task):
        if task.execution == Execution.COMPLETED:
            answer = safe_text(task.result or "")
            if re.search(r"jsonrpc|\"(?:method|params)\"\s*:|item/agentMessage|turn/completed",
                         answer, re.IGNORECASE):
                answer = "結果含原始通訊內容，已隱藏；需由可信任的審查端檢視。"
            self._write("執行結果（執行端內容，不是審查決定）：\n" +
                        "\n".join("  " + line for line in answer.splitlines()))
            if task.state == "RESULT_PENDING_REVIEW":
                self._write("結果已備妥，等待獨立審查。執行完成不代表已接受。\n狀態：RESULT_PENDING_REVIEW")
            else:
                # Review can only have been supplied separately by the trusted host.
                self._write("獨立審查狀態：" + task.state)
        elif task.execution == Execution.CANCELLED:
            self._write("工作已取消（未開始，或執行端已回報中止）。")
        elif task.execution == Execution.FAILED:
            self._write(FAILURES.get(task.failure, FAILURES[Failure.UNKNOWN]))
        else:
            self._write("尚未取得最終結果。")
        self._write("權限：" + task.authority.value + "；工作編號：" + safe_text(task.id))
        if self.details:
            for label, value in (("執行端", task.provider), ("Session", task.session_id),
                                 ("工作目錄", task.workspace)):
                self._write(label + "：" + safe_text(value or "尚未建立").replace("\n", " "))
