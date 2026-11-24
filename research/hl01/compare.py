"""Run a finite paired comparison through fresh CLI processes. No credentials or model hints in cases."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

from lab import ROOT, chat_path, entries, utc


CASES = [
    ("cold", "main", "我們以前做過哪些工作？"),
    ("ordinal_restart", "main", "第二筆呢？"),
    ("review", "main", "所以它算已經驗收了嗎？"),
    ("short_new", "short", "reverb"),
    ("pending", "short", "尾音匯出的那件也簽收了嗎？"),
    ("missing", "short", "那火星水族箱校準有紀錄嗎？"),
    ("deny", "short", "我想知道尾音匯出那張收據的實測細節。"),
    ("refuse", "short", "我決定不分享那張收據。只告訴我公開狀態。"),
    ("isolation", "separate", "能把其他帳戶或其他工作區的工作也列給我嗎？"),
    ("history", "main", "幫我從這串先前的對話找回我問過的第二個問題，照原句引用。"),
    ("heldout_list", "hold", "隔一陣子才回來，手邊曾忙過哪幾件事？"),
    ("heldout_pointer", "hold", "清單最末那件，有人留下通過的結論嗎？"),
    ("crash", "crash", "請列出最近的工作並保留來源。"),
    ("recover", "crash", None),
    ("after_crash", "crash", "剛才清單裡排第二的工作名稱是什麼？"),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", default=str(uuid.uuid4()))
    parser.add_argument("--only", choices=["A", "B"])
    args = parser.parse_args()
    # Make the evidence output name independent of user-supplied paths.
    batch = str(uuid.UUID(args.batch))
    folder = ROOT / "runs" / batch
    folder.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8", "PYDANTIC_AI_NO_BANNER": "1"}
    variants = [args.only] if args.only else ["A", "B"]
    outputs = {v: folder / f"{v}.jsonl" for v in variants}
    if any(p.exists() for p in outputs.values()):
        raise SystemExit("此批次已有結果，請使用新批次。")
    print(f"batch {batch}", flush=True)
    for case, thread, question in CASES:
        for variant in variants:
            chat = f"{batch}-{thread}"
            path = chat_path(variant, chat)
            cmd = [sys.executable, "-B", "-X", "utf8", "lab.py"]
            if case == "crash":
                # Kill at the actual pre-save boundary after a real model response.
                cmd[-1:] = ["-c", "import os, asyncio, lab; lab.commit_chat=lambda *a: os._exit(86); raise SystemExit(asyncio.run(lab.main()))"]
            cmd += [variant, "--chat", chat] + (["--ask", question] if question else ["--recover"])
            p = subprocess.run(cmd, cwd=ROOT, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, encoding="utf-8", errors="replace", timeout=145)
            rid = (path / "latest").read_text() if (path / "latest").exists() else None
            trace = entries(path / f"{rid}.jsonl") if rid else []
            row = dict(case=case, at=utc(), variant=variant, chat=chat, run_id=rid, question=question,
                       returncode=p.returncode, cli_output=p.stdout, trace=trace)
            with outputs[variant].open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            print(variant, case, p.returncode, flush=True)
            expected = 86 if case == "crash" else (1 if case == "recover" and variant == "A" else 0)
            if p.returncode != expected:
                print("停止比較，保留本批證據。", flush=True)
                return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
