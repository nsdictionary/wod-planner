"""코치가 승인한 WOD 초안을 wods/YYYY-MM-DD.json에 저장한다.

  python3 scripts/save_wod.py check <draft.json> [--wods-dir DIR] [--data-dir DIR] [--json]
  python3 scripts/save_wod.py save  <draft.json> --draft-code CODE --coach-message TEXT
                                   [--accept-warnings CODE] [--replace-existing CODE]
                                   [--wods-dir DIR] [--data-dir DIR] [--json]
  (--approve는 --draft-code의 예전 이름이며 같은 뜻으로 받는다)

무엇을 보장하고 무엇을 보장하지 않는가
  - 코치 승인 판단은 이 스크립트 밖(Claude Code Skill과 대화)에서 한다. 이 스크립트는 **사람이 승인했다는 사실을
    증명하지 않는다.** 아래 코드는 모두 파일을 읽을 수 있으면 누구나 계산할 수 있는 해시라서, CLI 인자를 직접
    구성하면 코치 없이도 저장할 수 있다 (2026-11-08 재현 확인). 로컬 개인용 도구라는 범위에서 이 한계를 받아들인다.
  - 보장하는 것은 **무결성과 상태 확인**이다.
    · 초안 코드(--draft-code): 초안 내용 SHA-256 앞 12자리. 코치에게 보여 준 초안과 지금 저장하려는 초안이
      한 글자라도 다르면 거부한다 (보여 준 뒤 바뀐 초안이 저장되는 사고 방지).
    · 저장 직전 재검증(simulate·check_equipment·화이트보드 완전성)에 오류가 있거나 정확한 수량 부족(short)이 있으면 거부.
    · 경고 코드(--accept-warnings): 지금 남은 경고 목록의 해시. 경고가 있는데 이 값이 없거나 다르면 거부한다
      (경고가 바뀐 줄 모르고 저장하는 사고 방지 — 코치가 경고를 봤다는 증명은 아님).
    · 기록 코드(--replace-existing): 같은 날짜 기존 기록 파일의 해시. 없으면 덮어쓰지 않고, 교체할 때는
      이전 기록을 wods/archive/에 보존한다.
    · 초안 JSON 안의 "approved" 같은 필드는 보지 않는다.
  - --coach-message: 에이전트가 전달한 코치 발화 원문. 검증하지 않는 감사용 기록이다.
  - Claude Code 권한: .claude/settings.json에서 `python3 scripts/save_wod.py save`는 "ask"라서 그 형태로
    실행하면 권한 확인 창이 뜬다. 이것도 WOD 승인이 아니라 명령 실행 허가이며, 다른 형태의 명령에는 적용되지 않는다.
  저장은 임시 파일 → fsync → 원자적 반영. approved_at은 save를 실행한 실제 시스템 시각이다 (코치 발화 시각 아님).

종료 코드: 0 = 저장됨(save) / 저장 가능(check), 1 = 거부(검증 실패·승인 불일치·경고 미확인·기존 기록), 2 = 입력 오류.
"""

import argparse
import copy
import json
import re
import sys
from pathlib import Path

from autofix import default_ledger_path, ledger_summary, load_ledger
from common import (
    CODE_LEN,
    DEFAULT_DATA_DIR,
    DEFAULT_WODS_DIR,
    EXIT_INPUT,
    ROOT,
    InputError,
    atomic_write_text,
    dump_json,
    input_error_report,
    issue,
    load_data,
    load_json,
    make_report,
    now_iso,
    sha256_file,
    sha256_json,
    validate_draft,
)
from render_wod import build

SCRIPT = "save_wod"
RECORD_SCHEMA = "wod-record/1"
BLOCKING_WARNING_CODES = ("short",)      # 정확한 수량 부족 = 미해결 문제
CODE_RE = re.compile(r"^[0-9a-f]{%d}([0-9a-f]{%d})?$" % (CODE_LEN, 64 - CODE_LEN))


def _rel(path):
    p = Path(path).resolve()
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        return str(p)


def warnings_code(warnings):
    keys = sorted([w.get("source", ""), w["code"], w["message"]] for w in warnings)
    return sha256_json(keys)[:CODE_LEN] if keys else None


def _code_matches(given, full):
    return bool(given) and bool(CODE_RE.match(given)) and full.startswith(given)


def summarize(draft, data):
    movs = data["movements"]["movements"]
    items = []
    for m in draft["movements"]:
        info = movs.get(m["id"]) or {}
        items.append({"id": m["id"], "display": info.get("display", m["id"]), "patterns": info.get("patterns") or []})
    fmt = draft.get("format")
    minutes = draft.get("time_cap_min") if fmt == "FOR_TIME" else draft.get("duration_min")
    return {"format": fmt, "workout_min": minutes, "movements": items,
            "patterns": sorted({p for it in items for p in it["patterns"]})}


def evaluate(draft_path, wods_dir, data):
    """저장 전 재검증 → (blocking_errors, warnings, context). 파일은 쓰지 않는다."""
    draft = load_json(draft_path)
    validate_draft(copy.deepcopy(draft))
    date = draft.get("date")
    if not date:
        raise InputError("초안에 date가 없습니다. 저장할 날짜를 알 수 없습니다.")
    draft_sha = sha256_json(draft)
    errors, warnings, result = build(draft, data)
    blocking = list(errors)
    rest = []
    for w in warnings:
        if w["code"] in BLOCKING_WARNING_CODES:
            blocking.append(dict(w, code="unresolved_shortage",
                                 message="미해결 장비 부족: " + w["message"] +
                                 " 운영 방식(concurrent_athletes) 또는 동작을 정해 초안을 고친 뒤 다시 검증하세요."))
        else:
            rest.append(w)

    ledger_path = default_ledger_path(draft_path)
    ledger = None
    try:
        ledger = load_ledger(ledger_path, date)
    except InputError as e:
        rest.append(issue("autofix_history_unreadable", e.messages[0], source=SCRIPT))
    autofix = None
    if ledger:
        summary = ledger_summary(ledger)
        stale = summary["current_sha256"] != draft_sha
        autofix = {"ledger_path": _rel(ledger_path), "stale": stale, "summary": summary,
                   "original_draft": ledger.get("original_draft"), "runs": ledger["runs"]}
        if stale:
            rest.append(issue("autofix_history_stale",
                              "마지막 자동 수정 이후 초안이 바뀌었습니다. 수정 이력은 이전 초안 기준입니다 "
                              "(지금 초안은 방금 다시 검증함).", source=SCRIPT))

    record_path = Path(wods_dir) / f"{date}.json"
    existing = None
    if record_path.exists():
        existing = {"path": _rel(record_path), "record_code": sha256_file(record_path)[:CODE_LEN]}
    ctx = {"date": date, "draft": draft, "draft_path": _rel(draft_path), "draft_sha256": draft_sha,
           "approval_code": draft_sha[:CODE_LEN], "warnings_code": warnings_code(rest),
           "record_path": record_path, "existing_record": existing, "render": result, "autofix": autofix}
    return blocking, rest, ctx


def _public(ctx):
    return {"date": ctx["date"], "draft_path": ctx["draft_path"], "draft_code": ctx["approval_code"],
            "approval_code": ctx["approval_code"],      # 예전 이름 (호환용, draft_code와 같은 값)
            "draft_sha256": ctx["draft_sha256"], "warnings_code": ctx["warnings_code"],
            "record_path": _rel(ctx["record_path"]), "existing_record": ctx["existing_record"],
            "whiteboard": ctx["render"]["whiteboard"], "checks": ctx["render"]["checks"],
            "autofix_history": ({"stale": ctx["autofix"]["stale"], **{k: ctx["autofix"]["summary"][k]
                                 for k in ("runs", "attempts_total", "chain_intact")}} if ctx["autofix"] else None)}


def check(draft_path, wods_dir, data):
    blocking, warnings, ctx = evaluate(draft_path, wods_dir, data)
    result = _public(ctx)
    result["saveable"] = not blocking
    return blocking, warnings, result


def save(draft_path, wods_dir, data, approve, coach_message, accept_warnings=None, replace_existing=None):
    if not coach_message or not coach_message.strip():
        raise InputError("--coach-message: 코치의 승인 발화 원문이 필요합니다.")
    blocking, warnings, ctx = evaluate(draft_path, wods_dir, data)
    result = _public(ctx)
    result["saved"] = False
    refusals = []

    if not _code_matches(approve, ctx["draft_sha256"]):
        refusals.append(issue("draft_code_mismatch",
                              f"--draft-code {approve!r}가 지금 초안의 초안 코드 {ctx['approval_code']}와 다릅니다. "
                              "코치에게 보여 준 뒤 초안이 바뀌었거나 다른 초안의 코드입니다. 바뀐 초안을 다시 보여 주고 "
                              "코치의 승인을 새로 받으세요."))
    if blocking:
        refusals.append(issue("validation_failed",
                              f"저장 직전 재검증에서 해결되지 않은 문제 {len(blocking)}건이 있어 저장하지 않았습니다.",
                              problems=blocking))
    if warnings and accept_warnings != ctx["warnings_code"]:
        refusals.append(issue("warnings_not_accepted",
                              f"남은 경고 {len(warnings)}건을 코치가 확인했다는 --accept-warnings {ctx['warnings_code']}가 "
                              "필요합니다. 경고를 코치에게 보여 주고 확인을 받으세요."
                              + (f" (받은 값 {accept_warnings!r}는 지금 경고 목록과 다름)" if accept_warnings else "")))
    if not warnings and accept_warnings:
        warnings = warnings + [issue("no_warnings_to_accept", "남은 경고가 없어 --accept-warnings는 무시했습니다.",
                                     source=SCRIPT)]
    existing = ctx["existing_record"]
    if existing and replace_existing != existing["record_code"]:
        refusals.append(issue("record_exists",
                              f"{existing['path']}에 이미 저장된 WOD가 있습니다 (기록 코드 {existing['record_code']}). "
                              "덮어쓰지 않았습니다. 기존 기록을 바꾸려면 코치의 별도 확인 후 "
                              f"--replace-existing {existing['record_code']}로 다시 실행하세요."))
    if not existing and replace_existing:
        refusals.append(issue("nothing_to_replace", "교체할 기존 기록이 없습니다. --replace-existing을 빼고 다시 실행하세요."))
    if refusals:
        return refusals + blocking, warnings, result

    at = now_iso()
    archived = None
    if existing:
        stamp = at.replace(":", "").replace("+", "p")
        archive = Path(wods_dir) / "archive" / f"{ctx['date']}.{stamp}.json"
        atomic_write_text(archive, ctx["record_path"].read_text(encoding="utf-8"), overwrite=False)
        archived = _rel(archive)
    record = {
        "schema": RECORD_SCHEMA,
        "date": ctx["date"],
        "approved_at": at,
        "approval": {
            "method": "agent_reported",
            "note": "코치 승인은 에이전트가 대화에서 판단해 저장을 실행한 것이다. 이 기록은 사람의 승인을 증명하지 않는다. "
                    "draft_code는 저장된 초안이 코치에게 보여 준 초안과 같다는 무결성 확인용이다.",
            "draft_code": ctx["approval_code"],
            "approval_code": ctx["approval_code"],
            "draft_sha256": ctx["draft_sha256"],
            "coach_message": coach_message.strip(),
            "coach_message_verified": False,
            "accepted_warnings_code": ctx["warnings_code"] if warnings else None,
            "accepted_warnings": [{"source": w.get("source"), "code": w["code"], "message": w["message"]}
                                  for w in warnings if w["code"] != "no_warnings_to_accept"],
            "replaced_record": {"record_code": existing["record_code"], "archived_to": archived} if existing else None,
        },
        "draft_path": ctx["draft_path"],
        "wod": ctx["draft"],
        "summary": summarize(ctx["draft"], data),
        "whiteboard": ctx["render"]["whiteboard"],
        "validation": {"validated_at": at, "checks": ctx["render"]["checks"], "errors": [],
                       "warnings": [{"source": w.get("source"), "code": w["code"], "message": w["message"]}
                                    for w in warnings]},
        "autofix": ({"stale": ctx["autofix"]["stale"], "summary": ctx["autofix"]["summary"],
                     "original_draft": ctx["autofix"]["original_draft"], "runs": ctx["autofix"]["runs"]}
                    if ctx["autofix"] else None),
    }
    try:
        atomic_write_text(ctx["record_path"], dump_json(record), overwrite=bool(existing))
    except FileExistsError:
        return [issue("record_exists", f"{_rel(ctx['record_path'])}가 저장 도중 생겼습니다. 덮어쓰지 않았습니다.")], \
            warnings, result
    result.update(saved=True, saved_path=_rel(ctx["record_path"]), approved_at=at, approval_method="agent_reported",
                  record_code=sha256_file(ctx["record_path"])[:CODE_LEN], archived_previous=archived)
    return [], warnings, result


def render_text(report, cmd):
    r = report["result"]
    out = []
    if r:
        out.append(f"[{'저장 전 확인' if cmd == 'check' else '저장'}] {r['date']} — 초안 {r['draft_path']}")
        out.append(f"초안 코드: {r['draft_code']} (무결성 확인용 — 사람 승인 증명 아님)")
        if r.get("warnings_code"):
            out.append(f"경고 코드: {r['warnings_code']} (코치가 남은 경고를 검토하고 수용했을 때만 --accept-warnings로 전달)")
        ex = r.get("existing_record")
        out.append(f"같은 날짜 기록: {ex['path']} (기록 코드 {ex['record_code']})" if ex else "같은 날짜 기록: 없음")
        if r.get("autofix_history"):
            a = r["autofix_history"]
            out.append(f"자동 수정 이력: 실행 {a['runs']}회, 누적 수정 {a['attempts_total']}회"
                       + (" — 마지막 수정 이후 초안 변경됨" if a["stale"] else ""))
        for c in r.get("checks") or []:
            out.append(f"  {c['status']} · {c['item']} — {c['detail']}")
        if cmd == "save" and r.get("saved"):
            out.append(f"저장됨: {r['saved_path']} (승인 시각 {r['approved_at']}, 기록 코드 {r['record_code']})")
            if r.get("archived_previous"):
                out.append(f"이전 기록 보존: {r['archived_previous']}")
        elif cmd == "save":
            out.append("저장하지 않았습니다.")
    for e in report["errors"]:
        out.append(f"✗ {e['message']}")
        for p in e.get("problems") or []:
            out.append(f"    - {p['message']}")
    out += [f"! {w['message']}" for w in report["warnings"]]
    out.append(f"결과: 종료 코드 {report['exit_code']}")
    return "\n".join(out)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="save_wod.py", description="코치가 승인한 WOD 초안을 wods/에 저장한다.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("check", "save"):
        sp = sub.add_parser(name)
        sp.add_argument("draft", help="초안 JSON 경로 (보통 drafts/<date>.json)")
        sp.add_argument("--wods-dir", default=None, help=f"기록 디렉터리 (기본: {DEFAULT_WODS_DIR})")
        sp.add_argument("--data-dir", default=None, help=f"데이터 디렉터리 (기본: {DEFAULT_DATA_DIR})")
        sp.add_argument("--json", action="store_true")
        if name == "save":
            sp.add_argument("--draft-code", "--approve", dest="approve", required=True,
                            help="check가 보여 준 초안 코드 (코치에게 보여 준 초안과 같은지 확인하는 무결성 코드, 승인 증명 아님)")
            sp.add_argument("--coach-message", required=True, help="코치의 승인 발화 원문 (검증하지 않는 감사 기록)")
            sp.add_argument("--accept-warnings", default=None, help="코치가 확인한 경고 목록의 경고 코드")
            sp.add_argument("--replace-existing", default=None, help="교체를 코치가 따로 확인한 기존 기록 코드")
    args = parser.parse_args(argv)
    wods_dir = Path(args.wods_dir) if args.wods_dir else DEFAULT_WODS_DIR
    try:
        data = load_data(args.data_dir)
        if args.cmd == "check":
            report = make_report(SCRIPT, *check(args.draft, wods_dir, data))
        else:
            report = make_report(SCRIPT, *save(args.draft, wods_dir, data, args.approve, args.coach_message,
                                               args.accept_warnings, args.replace_existing))
    except InputError as e:
        report = input_error_report(SCRIPT, e)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif report["exit_code"] == EXIT_INPUT:
        print("입력 오류 — 처리하지 않았습니다.", file=sys.stderr)
        for e in report["errors"]:
            print(e["message"], file=sys.stderr)
    else:
        print(render_text(report, args.cmd))
    return report["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
