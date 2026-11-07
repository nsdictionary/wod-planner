"""초안 보호: 같은 날짜 초안을 말없이 덮어쓰지 않는다.

  python3 scripts/draft_store.py status <date> [--drafts-dir DIR] [--json]
  python3 scripts/draft_store.py commit <date> [--candidate PATH] [--new-version | --keep-existing]
                                               [--drafts-dir DIR] [--json]

흐름
  에이전트는 새 초안을 drafts/<date>.candidate.json에 쓰고 commit을 실행한다.
  - drafts/<date>.json이 없으면 후보를 현재 초안으로 옮긴다.
  - 있고 내용이 같으면 아무것도 바꾸지 않는다.
  - 있고 내용이 다르면 **기본은 거부**(exit 1, draft_exists). 코치에게 둘 중 하나를 묻는다.
      --new-version   기존 초안(과 수정 이력 원장)을 drafts/versions/<date>.v<N>.json로 보존하고 후보를 현재 초안으로
      --keep-existing 기존 초안을 그대로 쓰고 후보를 버린다
  status는 현재 초안의 초안 코드(내용 해시 앞 12자리)와 보존된 버전 목록을 보여 준다.
  코치에게 보여 준 버전은 초안 코드로 식별한다. 보여 준 뒤 초안이 바뀌면 코드가 달라져 save_wod.py가 저장을 거부한다.
  (초안 코드는 무결성 확인용이며 사람의 승인을 증명하지 않는다.)

종료 코드: 0 = 처리됨, 1 = 기존 초안이 있어 코치 선택 필요, 2 = 입력 오류.
"""

import argparse
import json
import os
import sys
from pathlib import Path

from autofix import default_ledger_path
from common import (
    CODE_LEN,
    DATE_RE,
    DEFAULT_DRAFTS_DIR,
    EXIT_INPUT,
    InputError,
    atomic_write_text,
    input_error_report,
    issue,
    load_json,
    make_report,
    sha256_json,
    validate_draft,
)

SCRIPT = "draft_store"


def paths(drafts_dir, date):
    d = Path(drafts_dir)
    return {"draft": d / f"{date}.json", "candidate": d / f"{date}.candidate.json",
            "ledger": default_ledger_path(d / f"{date}.json"), "versions": d / "versions"}


def _code(obj):
    return sha256_json(obj)[:CODE_LEN]


def list_versions(drafts_dir, date):
    vdir = paths(drafts_dir, date)["versions"]
    out = []
    for f in sorted(vdir.glob(f"{date}.v*.json")) if vdir.exists() else []:
        stem = f.name[len(date) + 2:-len(".json")]
        if not stem.isdigit():
            continue                      # .history.json 등
        try:
            code = _code(json.loads(f.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            code = None
        out.append({"version": int(stem), "path": str(f), "approval_code": code})
    return sorted(out, key=lambda v: v["version"])


def _read_draft(path, label):
    obj = load_json(path)
    validate_draft(json.loads(json.dumps(obj)))
    return obj


def status(drafts_dir, date):
    p = paths(drafts_dir, date)
    result = {"date": date, "draft_path": str(p["draft"]), "exists": p["draft"].exists(), "approval_code": None,
              "candidate_exists": p["candidate"].exists(), "ledger_exists": p["ledger"].exists(),
              "versions": list_versions(drafts_dir, date)}
    warnings = []
    if result["exists"]:
        try:
            result["approval_code"] = _code(load_json(p["draft"]))
        except InputError as e:
            warnings.append(issue("draft_unreadable", f"현재 초안을 읽을 수 없습니다: {e.messages[0]}"))
    return [], warnings, result


def _archive(src, dest):
    """src를 dest로 복사 보존 (원자적, 덮어쓰지 않음)."""
    atomic_write_text(dest, Path(src).read_text(encoding="utf-8"), overwrite=False)


def commit(drafts_dir, date, candidate=None, new_version=False, keep_existing=False):
    if new_version and keep_existing:
        raise InputError("--new-version과 --keep-existing은 함께 쓸 수 없습니다.")
    p = paths(drafts_dir, date)
    cand_path = Path(candidate) if candidate else p["candidate"]
    if not cand_path.exists():
        raise InputError(f"후보 초안 {cand_path}가 없습니다. 새 초안은 먼저 {p['candidate'].name}에 쓰세요.")
    if cand_path.resolve() == p["draft"].resolve():
        raise InputError("후보 초안 경로가 현재 초안과 같습니다. 후보는 별도 파일이어야 합니다.")
    cand = _read_draft(cand_path, "후보")
    if cand.get("date") != date:
        raise InputError(f"후보 초안의 date({cand.get('date')})가 {date}와 다릅니다.")
    cand_code = _code(cand)
    result = {"date": date, "draft_path": str(p["draft"]), "candidate_code": cand_code, "action": None,
              "approval_code": None, "archived": None}

    if not p["draft"].exists():
        atomic_write_text(p["draft"], Path(cand_path).read_text(encoding="utf-8"), overwrite=False)
        os.unlink(cand_path)
        result.update(action="created", approval_code=cand_code)
        return [], [], result

    try:
        current = load_json(p["draft"])
        cur_code = _code(current)
    except InputError:
        current, cur_code = None, None
    result["existing_code"] = cur_code

    if current is not None and cur_code == cand_code:
        os.unlink(cand_path)
        result.update(action="unchanged", approval_code=cur_code)
        return [], [], result

    if keep_existing:
        os.unlink(cand_path)
        result.update(action="kept_existing", approval_code=cur_code)
        return [], [], result

    if not new_version:
        result["action"] = "refused"
        return [issue("draft_exists",
                      f"{p['draft'].name}가 이미 있습니다 (초안 코드 {cur_code or '읽을 수 없음'}). "
                      f"새 후보(초안 코드 {cand_code})로 덮어쓰지 않았습니다. 코치에게 기존 초안을 계속 쓸지"
                      f"(--keep-existing), 새 버전을 만들지(--new-version — 기존은 drafts/versions/에 보존) 확인하세요.",
                      existing_code=cur_code, candidate_code=cand_code)], [], result

    # 새 버전: 기존 초안과 원장을 versions/에 보존한 뒤 교체한다
    n = max([v["version"] for v in list_versions(drafts_dir, date)] + [0]) + 1
    vdir = p["versions"]
    archived = {"version": n, "draft": str(vdir / f"{date}.v{n}.json"), "ledger": None}
    _archive(p["draft"], vdir / f"{date}.v{n}.json")
    if p["ledger"].exists():
        _archive(p["ledger"], vdir / f"{date}.v{n}.history.json")
        os.unlink(p["ledger"])            # 새 초안은 새 원장으로 시작 (이전 원장은 보존본에 있음)
        archived["ledger"] = str(vdir / f"{date}.v{n}.history.json")
    atomic_write_text(p["draft"], Path(cand_path).read_text(encoding="utf-8"), overwrite=True)
    os.unlink(cand_path)
    result.update(action="new_version", approval_code=cand_code, archived=archived)
    return [], [], result


ACTION_TEXT = {
    "created": "새 초안을 만들었습니다",
    "unchanged": "기존 초안과 내용이 같아 바꾸지 않았습니다",
    "kept_existing": "기존 초안을 유지하고 후보를 버렸습니다",
    "new_version": "기존 초안을 보존하고 새 버전으로 교체했습니다",
    "refused": "기존 초안이 있어 덮어쓰지 않았습니다",
}


def render_text(report, cmd):
    r = report["result"]
    lines = []
    if cmd == "status":
        lines.append(f"[초안 상태] {r['date']}")
        lines.append(f"현재 초안: {r['draft_path']} — " +
                     (f"있음, 초안 코드 {r['approval_code']}" if r["exists"] else "없음"))
        lines.append(f"후보 초안: {'있음' if r['candidate_exists'] else '없음'} / 수정 이력 원장: {'있음' if r['ledger_exists'] else '없음'}")
        for v in r["versions"]:
            lines.append(f"보존 버전 v{v['version']}: {v['path']} (초안 코드 {v['approval_code']})")
    else:
        lines.append(f"[초안 반영] {r['date']} — {ACTION_TEXT[r['action']]}")
        if r.get("approval_code"):
            lines.append(f"현재 초안 코드: {r['approval_code']}")
        if r.get("archived"):
            lines.append(f"보존: {r['archived']['draft']}" + (f", {r['archived']['ledger']}" if r["archived"]["ledger"] else ""))
    lines += [f"✗ {e['message']}" for e in report["errors"]]
    lines += [f"! {w['message']}" for w in report["warnings"]]
    lines.append(f"결과: 종료 코드 {report['exit_code']}")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="draft_store.py", description="같은 날짜 초안을 말없이 덮어쓰지 않고 버전으로 보존한다.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("status", "commit"):
        sp = sub.add_parser(name)
        sp.add_argument("date", help="YYYY-MM-DD")
        sp.add_argument("--drafts-dir", default=None, help=f"초안 디렉터리 (기본: {DEFAULT_DRAFTS_DIR})")
        sp.add_argument("--json", action="store_true")
        if name == "commit":
            sp.add_argument("--candidate", default=None, help="후보 초안 경로 (기본: <drafts>/<date>.candidate.json)")
            sp.add_argument("--new-version", action="store_true", help="기존 초안을 versions/에 보존하고 교체")
            sp.add_argument("--keep-existing", action="store_true", help="기존 초안을 유지하고 후보를 버림")
    args = parser.parse_args(argv)
    drafts_dir = Path(args.drafts_dir) if args.drafts_dir else DEFAULT_DRAFTS_DIR
    try:
        if not DATE_RE.match(args.date):
            raise InputError("date: YYYY-MM-DD 형식이어야 합니다.")
        if args.cmd == "status":
            report = make_report(SCRIPT, *status(drafts_dir, args.date))
        else:
            report = make_report(SCRIPT, *commit(drafts_dir, args.date, args.candidate,
                                                 args.new_version, args.keep_existing))
    except (InputError, OSError) as e:
        report = input_error_report(SCRIPT, e if isinstance(e, InputError) else InputError(str(e)))
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
