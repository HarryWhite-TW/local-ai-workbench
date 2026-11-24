"""Resolve saved Git work and answer locally in its conversation."""
import json
import re
import unicodedata
from uuid import uuid4

from .chat import LOCAL_MODEL, now
from .siwc import ChatError


QUERY = re.compile(r"進度|狀態|做到|到哪|完成了|做完|還剩|測試|驗證|證據|覆核|審查|結果|下一步|接下來")
FOLLOW_UP = re.compile(
    r"(?:請問|所以|另外|那麼|那|還有)*\s*(?:(?:這|那)(?:件|筆)(?:工作)?(?:的)?|先前|之前|當時)?\s*"
    r"(?:有哪些測試(?:結果)?|跑了哪些測試|做了哪些驗證|測試(?:結果|證據)?(?:是什麼|如何|呢)?|"
    r"驗證(?:結果|範圍|呢)?|審查(?:結果|狀態|呢)?|結果呢|進度呢|做到哪裡(?:了)?|"
    r"下一步(?:呢|是什麼|怎麼做)?|接下來(?:建議)?(?:怎麼做|做什麼)|我需要決定什麼)[？?。！!\s]*"
)
CHOICE = re.compile(r"(?:我指的是\s*|請?選(?:擇)?\s*)?第\s*([1-9][0-9]?|[一二三四五六七八九十])\s*(?:筆|項)[。！!\s]*")
READ_CUE = re.compile(r"進度|狀態|做到|到哪|做完|還剩|完成了|有哪些|哪些|怎麼|如何|下一步|接下來|結果|呢")
JOB_ID = re.compile(r"\b[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\b")
COUNTS = re.compile(r"\b[0-9]+ (?:passed|failed|skipped|errors?|xfailed|xpassed)\b|\bRan [0-9]+ tests?\b", re.I)


def normalize(value):
    return unicodedata.normalize("NFKC", value).casefold()


def text_line(value, limit=160):
    return " ".join(value.split())[:limit].translate(str.maketrans("[]<>*_#", "［］＜＞＊＿＃"))


def aliases(project):
    label = normalize(project)
    repo = label.rsplit("/", 1)[-1]
    primary = re.split(r"[\s_-]+", repo, maxsplit=1)[0]
    return primary, {label, repo, re.sub(r"[\s_]+", "-", repo), re.sub(r"[-_]+", " ", repo)}


def mentions(question, names):
    return any(re.search(r"(?<![a-z0-9_-])" + re.escape(name) + r"(?![a-z0-9_-])", question)
               for name in names if name)


def receipts(db, account, workspace, chat_id, legacy_name):
    jobs, linked = {}, set()
    types = [("git_jobs", "git_job_links", False)]
    if db.execute("SELECT count(*) FROM sqlite_master WHERE type='table' "
                  "AND name IN ('reverb_job', 'reverb_job_links')").fetchone()[0] == 2:
        types.append(("reverb_job", "reverb_job_links", True))
    for table, links, legacy in types:
        for row in db.execute(f"""
            SELECT j.id, j.data, MAX(CASE WHEN c.id=? THEN 1 ELSE 0 END) AS linked
            FROM {table} j JOIN {links} l ON l.job=j.id JOIN chats c ON c.id=l.chat
            WHERE j.account=? AND c.account=? AND c.workspace=?
            GROUP BY j.id ORDER BY j.rowid DESC
            """, (chat_id, account, account, workspace)):
            job = json.loads(row["data"])
            if (job.get("id") != row["id"] or not JOB_ID.fullmatch(row["id"])
                    or job.get("state") in ("PREVIEW", "EXPIRED")):
                continue
            jobs[row["id"]] = (legacy_name if legacy else job["project"]["name"], job)
            if row["linked"]:
                linked.add(row["id"])
    return jobs, linked


def summarize(adapter, project, job):
    recorded = job.get("state")
    lines = [f"**{text_line(project)}**｜工作 ID `{job['id']}`",
             f"工作目標：{text_line(job['goal'], 220)}"]
    try:
        result = adapter.verified_receipt(job)
    except ChatError:
        lines.append("已完成工作與測試：保存收據不足以核實已完成的變更或通過的測試。")
        tests = job.get("tests")
        if (isinstance(tests, dict) and type(tests.get("exitCode")) is int
                and any(e.get("kind") == "host_verification" and e.get("result") == tests
                        for e in job.get("events", []))):
            lines.append(f"保存的主機驗證事件記錄退出碼 {tests['exitCode']}。候選最終驗證仍未確認。")
    else:
        paths, scope, captured = result
        lines.extend([
            f"已完成：保存的差異顯示已修改 {', '.join(text_line(p) for p in dict.fromkeys(paths))}。",
            f"可信驗證：{text_line(scope)}。主機退出碼 0，驗證記錄時間 {text_line(captured)}。",
        ])
        output = job["tests"]["stdout"] + "\n" + job["tests"]["stderr"]
        if matches := list(dict.fromkeys(COUNTS.findall(output))):
            lines.append("保存的測試統計：" + "、".join(matches) + "。")
        if "Python syntax OK" in output:
            lines.append("Python 語法檢查通過。")
        verified = job["verified"]
        lines.append(f"保存的驗證版本：HEAD `{verified['head']}`，工作樹指紋 `{verified['sha256']}`。")
    if job.get("thread_id") and job.get("turn_id"):
        lines.append("收據記有歷史 Codex thread／turn，目前執行端狀態未核實。")
    if recorded == "PENDING_REVIEW":
        lines.extend(["審查狀態：PENDING_REVIEW，仍待獨立技術審查。",
                      "建議下一步：核對目前候選與收據後，再提交獨立審查。"
                      "若保存的驗證未涵蓋所需行為，應先補證據。目前無須批准新的修改。"])
    else:
        state = recorded if recorded in ("FAILED", "CANCELLED") else "UNKNOWN"
        lines.extend([f"保存的工作狀態：{state}。",
                      "建議下一步：先核對候選與保存證據，再決定是否需要其他處置。"])
    lines.append("目前候選：UNKNOWN。本次讀回保存收據，工作樹與測試均未重新驗證。")
    return "\n\n".join(lines)


def resolve(question, jobs, linked, context, choice, follow_up):
    previous = json.loads(context["options"]) if context else []
    if choice:
        value = choice[1]
        nth = int(value) if value.isascii() else "一二三四五六七八九十".index(value) + 1
        return [previous[nth - 1]] if nth <= len(previous) and previous[nth - 1] in jobs else []
    if ids := list(dict.fromkeys(JOB_ID.findall(question))):
        return ids if all(key in jobs for key in ids) else []
    exact, shorthand = {}, {}
    for key, (project, _) in jobs.items():
        primary, names = aliases(project)
        if mentions(question, names - {primary}):
            exact[key] = primary
        if re.fullmatch(r"[a-z][a-z0-9]{2,}", primary) and mentions(question, {primary}):
            shorthand[key] = primary
        elif names == {primary} and mentions(question, names):
            exact[key] = primary
    exact_subjects = set(exact.values())
    named = {**exact, **{key: subject for key, subject in shorthand.items() if subject not in exact_subjects}}
    if named:
        if (len(set(named.values())) == 1 and not (context and context["job"] in named)
                and not re.search(r"另一|其他|分別|所有|兩筆", question)):
            return [key for key in named if key in linked] or list(named)
        return list(named)
    if follow_up:
        if context:
            focus = context["job"]
            return [focus] if focus in jobs else [key for key in previous if key in jobs]
        return [key for key in jobs if key in linked]
    if re.fullmatch(r"(?:請問)?(?:上次|之前|先前)(?:的)?(?:那件)?(?:工程)?工作(?:的)?"
                    r"(?:進度|狀態|結果|做到哪(?:裡)?了?)[？?。]*", question):
        return [key for key in jobs if key in linked] or list(jobs)
    return []


def readback(adapter, body, account, digest, legacy_name):
    question = normalize(body["question"].strip())
    choice, follow_up = CHOICE.fullmatch(question), FOLLOW_UP.fullmatch(question)
    exact_id = JOB_ID.fullmatch(question)
    if not (choice or follow_up or exact_id or (QUERY.search(question) and READ_CUE.search(question))):
        return None
    chat, chat_id = adapter.chat, body["chat"]
    with chat.connect() as db:
        if chat_id is not None:
            chat._project_owner(db, chat_id, require_chat=True)
        context = db.execute("""
            SELECT r.job,r.options FROM git_work_readbacks r
            WHERE r.turn=(SELECT id FROM turns WHERE chat=? ORDER BY rowid DESC LIMIT 1)
            """, (chat_id,)).fetchone()
        jobs, linked = receipts(db, account, chat.workspace, chat_id, legacy_name)
        if (choice or follow_up) and not context and not linked:
            return None
        matches = resolve(question, jobs, linked, context, choice, follow_up)
        if not matches and not (choice or follow_up or JOB_ID.search(question)
                                or re.search(r"(?:工程|工作)(?:的)?(?:目前|現在)?(?:狀態|進度|結果|做到)|"
                                             r"(?:上次|先前).*(?:工程|工作)", question)):
            return None

        job_id = matches[0] if len(matches) == 1 else None
        options = matches if 1 < len(matches) <= 10 else []
        if choice and not job_id and context:
            options = [key for key in json.loads(context["options"]) if key in jobs]
        if job_id:
            answer = summarize(adapter, *jobs[job_id])
        elif options:
            answer = "找到多筆符合的已保存工作。請回覆「第一筆」、「第 2 筆」這類選項，或指出完整工作 ID。"
            for i, key in enumerate(options, 1):
                project, job = jobs[key]
                answer += f"\n\n{i}. {text_line(project)}｜{text_line(job['goal'], 105)}｜`{key}`"
        else:
            answer = "目前帳戶與工作區未找到能唯一對應的已保存工作。請提供更明確的專案名稱或工作 ID。"

        turn, ts = str(uuid4()), now()
        if chat_id is None:
            chat_id = str(uuid4())
            db.execute("INSERT INTO chats VALUES (?,?,?,?,?)",
                       (chat_id, chat.workspace, account, body["question"].strip()[:60], ts))
        db.execute("""
            INSERT INTO turns (id,chat,question,answer,sources,model,created,finished,status)
            VALUES (?,?,?,?,?,?,?,?,?)
            """, (turn, chat_id, body["question"].strip(), answer, "[]", LOCAL_MODEL, ts, ts, "complete"))
        db.execute("""
            INSERT INTO turn_delivery (turn,state,request_key,request_hash,owner,workspace)
            VALUES (?,?,?,?,?,?)
            """, (turn, "complete", body.get("request_id"), digest, account, chat.workspace))
        db.execute("INSERT INTO git_work_readbacks VALUES (?,?,?)", (turn, job_id, json.dumps(options)))
    return {"chat": chat_id, "turn": turn, "local_readback": True}
