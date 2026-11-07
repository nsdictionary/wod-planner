"""WOD 초안 자동 수정·재검증 루프.

  python3 scripts/autofix.py <draft.json> [--out PATH] [--history PATH] [--max-attempts N] [--data-dir DIR] [--json]

절차
  1) simulate + check_equipment를 실행한다 (같은 함수, 같은 데이터).
  2) 문제를 찾는다: 두 스크립트의 오류 + 수량 부족 경고(short / possibly_short).
  3) 결정적으로 고칠 수 있는 문제 1개를 고친다 (우선순위: 사용 불가 동작 → 시간 상한 → 수량 부족).
  4) 다시 1)부터. 수정은 최대 N회(기본 3). 수정마다 무엇을 왜 바꿨는지 기록한다.

한 번에 하나씩 고치는 이유: 수정이 서로 영향을 주지 않게 하고, 어떤 수정이 어떤 결과를 냈는지 추적하기 위해서다.
문제가 3개를 넘는 초안은 자동으로 다 고치지 않고 코치에게 돌려준다.

자동 수정 규칙 (지어낸 값 없음)
  - 시간 초과(workout_too_long / workout_over_request): 기준 필드를 적용 상한으로 줄인다.
  - 사용 불가 동작(미보유·금지·층고·없는 무게) / 수량 부족: 대체 동작으로 바꾼다.
    후보 = ① 동작의 등록 substitutes ② 같은 패턴 집합의 등록 동작 ③ 패턴이 겹치는 등록 동작.
    후보마다 check_equipment로 따로 검사해, 오류가 없고 장비가 "충분"인 것만 쓴다.
    정확한 수량으로 충분한 후보(또는 장비 없음)가 추정 수량으로 충분한 후보보다 우선한다.
    수량 미확인·부족(가능성)·무게 미지정·보유 미확인 후보는 쓰지 않는다.
    단위가 다르면 1단위 거리(m 동작 = 1m, space.<id>.rep_distance_m)가 둘 다 있을 때만 거리로 환산하고,
    없으면 그 후보는 쓰지 않는다.
  - 운영 방식(파트너 교대·시차 출발·스테이션 분산)은 자동 적용하지 않는다. 동작 변경으로 못 고치면
    필요/보유 수량과 각 방식의 동시 사용 인원 계산을 근거로 붙여 코치에게 돌려준다.
    스테이션별 시작 위치만 바꾸는 것은 동시 사용 감소를 보장하지 않으므로 해결책으로 보지 않는다.
  - 형식·필수 필드 누락·미등록 동작은 의도 판단이 필요하므로 자동 수정하지 않는다.

수정 이력 보존 (Phase 4)
  --out을 쓰면 이력 원장 <out 이름>.history.json(또는 --history PATH)에 이번 실행을 **추가**한다.
  원장에는 최초 초안(original_draft, 첫 실행의 입력)과 실행별 기록(runs[]: 시각, 입력·출력 해시, 수정 전/후
  검증 상태, 수정 내역)이 쌓인다. 이미 수정된 초안을 다시 검증해도 이전 실행 기록은 지워지지 않는다.
  결과 JSON의 changes/history는 이번 실행분이고, ledger는 누적 요약이다.
  원장이 손상됐거나 다른 날짜 초안의 것이면 덮어쓰지 않고 입력 오류(2)로 멈춘다.

종료 코드: 0 = 통과(두 검증 exit 0, 수량 부족 없음), 1 = 미해결 문제 남음, 2 = 입력 오류.
"""

import argparse
import copy
import json
import math
import sys
from pathlib import Path

from check_equipment import check_equipment
from common import (
    CODE_LEN,
    DEFAULT_DATA_DIR,
    EXIT_FAIL,
    EXIT_INPUT,
    EXIT_OK,
    ROOT,
    SCALE_LEVELS,
    InputError,
    fmt_num,
    input_error_report,
    issue,
    load_data,
    load_json,
    make_report,
    now_iso,
    sha256_json,
    validate_draft,
    atomic_write_text,
    dump_json,
)
from simulate import simulate

SCRIPT = "autofix"
LEDGER_SCHEMA = "autofix-ledger/1"
DEFAULT_MAX_ATTEMPTS = 3
SHORTAGE_CODES = ("short", "possibly_short")
SUBSTITUTE_ERROR_CODES = ("equipment_not_owned", "banned_movement", "space_restricted", "weight_not_owned")
TIME_ERROR_CODES = ("workout_too_long", "workout_over_request")
# 이 경고가 남는 후보는 장비가 충분하다는 근거가 없으므로 대체 동작으로 쓰지 않는다
CANDIDATE_REJECT_WARNINGS = ("short", "possibly_short", "quantity_unknown", "weight_unspecified",
                             "weight_inventory_unknown", "availability_unknown")
PRIORITY = {"substitute_error": 0, "time": 1, "shortage": 2}
NOT_AUTOFIXABLE_REASON = {
    "unregistered_movement": "미등록 동작 — 어떤 동작을 의도했는지 판단이 필요합니다. 등록된 동작으로 바꾸거나 코치가 등록하세요.",
    "duration_missing": "진행 시간이 없습니다 — 의도한 시간을 정해야 합니다.",
    "time_cap_missing": "TC가 없습니다 — 의도한 TC를 정해야 합니다.",
    "rounds_missing": "For Time 라운드 수가 없습니다 — 의도한 라운드 수를 정해야 합니다.",
    "unsupported_format": "지원하지 않는 형식입니다 — AMRAP / EMOM / FOR_TIME 중에서 골라야 합니다.",
}


# ---------------------------------------------------------------- 검증 실행

def run_validators(draft, data):
    """두 검증 도구를 실행해 각자의 공통 형식 보고서를 돌려준다."""
    try:
        d = validate_draft(copy.deepcopy(draft))
    except InputError as e:
        return {"simulate": input_error_report("simulate", e),
                "check_equipment": input_error_report("check_equipment", e)}
    return {"simulate": make_report("simulate", *simulate(d, data)),
            "check_equipment": make_report("check_equipment", *check_equipment(d, data))}


def summarize(reports):
    return {name: {"exit_code": r["exit_code"],
                   "errors": [e["code"] for e in r["errors"]],
                   "warnings": [w["code"] for w in r["warnings"]]}
            for name, r in reports.items()}


def find_problems(reports):
    """해결해야 할 문제 목록 (우선순위 순)."""
    problems = []
    for name in ("check_equipment", "simulate"):
        for e in reports[name]["errors"]:
            if e["code"] in SUBSTITUTE_ERROR_CODES:
                kind = "substitute_error"
            elif e["code"] in TIME_ERROR_CODES:
                kind = "time"
            else:
                kind = "not_autofixable"
            problems.append({"kind": kind, "source": name, "issue": e})
    for w in reports["check_equipment"]["warnings"]:
        if w["code"] in SHORTAGE_CODES:
            problems.append({"kind": "shortage", "source": "check_equipment", "issue": w})
    problems.sort(key=lambda p: PRIORITY.get(p["kind"], 9))
    return problems


# ---------------------------------------------------------------- 위치·단위 도우미

def _movement_list(draft, scale):
    return draft["movements"] if scale is None else draft["scales"][scale]


def _location_text(scale, index):
    return f"movements[{index}]" if scale is None else f"scales.{scale}[{index}]"


def unit_distance_m(mid, data):
    """동작 1단위의 거리(m). 모르면 None. m 단위 동작은 1, rep 동작은 space.<id>.rep_distance_m."""
    info = data["movements"]["movements"][mid]
    if info["unit"] == "m":
        return 1
    sp = data["equipment"]["space"].get(mid)
    if isinstance(sp, dict) and isinstance(sp.get("rep_distance_m"), (int, float)):
        return sp["rep_distance_m"]
    return None


def convert_reps(reps, from_id, to_id, data):
    """→ (새 reps, 설명) 또는 (None, 이유). 같은 단위는 그대로, 다르면 거리가 둘 다 있을 때만 환산."""
    mv = data["movements"]["movements"]
    if mv[from_id]["unit"] == mv[to_id]["unit"]:
        return reps, None
    d_from, d_to = unit_distance_m(from_id, data), unit_distance_m(to_id, data)
    if d_from is None or d_to is None:
        return None, "단위가 달라 반복 수를 환산할 근거(1단위 거리)가 없음"
    total = reps * d_from
    new = max(1, int(math.floor(total / d_to + 0.5)))
    unit = "m" if mv[to_id]["unit"] == "m" else "회"
    return new, (f"거리 환산 {fmt_num(total)}m ÷ {fmt_num(d_to)}m = {fmt_num(round(total / d_to, 2))}"
                 f" → {new}{unit} ({fmt_num(new * d_to)}m)")


# ---------------------------------------------------------------- 대체 동작 후보

def _candidate_ids(mid, problem_issue, data):
    """(id, source_tier) 순서대로. 0 = 등록 substitutes, 1 = 같은 패턴 집합, 2 = 패턴 겹침."""
    movements = data["movements"]["movements"]
    info = movements[mid]
    out, seen = [], {mid}
    listed = [s["id"] for s in problem_issue.get("substitutes") or []] or \
             [s["id"] for s in info.get("substitutes") or []]
    for sid in listed:
        if sid not in seen:
            out.append((sid, 0))
            seen.add(sid)
    pats = set(info.get("patterns") or [])
    if pats:
        for cid, c in movements.items():
            if cid not in seen and set(c.get("patterns") or []) == pats:
                out.append((cid, 1))
                seen.add(cid)
        for cid, c in movements.items():
            if cid not in seen and pats & set(c.get("patterns") or []):
                out.append((cid, 2))
                seen.add(cid)
    return out


def _build_replacement(old, new_id, data):
    """원래 동작 항목을 새 동작으로 바꾼 항목 → (항목, 반복 수 설명) 또는 (None, 이유)."""
    mv = data["movements"]["movements"]
    reps, note = convert_reps(old["reps"], old["id"], new_id, data)
    if reps is None:
        return None, note
    new = {"id": new_id, "reps": reps}
    same_equipment = set(mv[old["id"]].get("equipment") or []) == set(mv[new_id].get("equipment") or [])
    keys = ("load", "weights", "units_per_athlete", "concurrent_athletes") if same_equipment \
        else ("concurrent_athletes",)
    for k in keys:
        if k in old:
            new[k] = copy.deepcopy(old[k])
    return new, note


def evaluate_candidate(draft, entry, data):
    """후보 동작 1개를 장비 검사 → (certainty, 이유). certainty 0 = 확실, 1 = 추정 수량으로 충분, None = 불가."""
    trial = {k: v for k, v in draft.items() if k not in ("movements", "scales")}
    trial["movements"] = [entry]
    errors, warnings, _ = check_equipment(validate_draft(trial), data)
    if errors:
        return None, errors[0]["message"]
    bad = [w for w in warnings if w["code"] in CANDIDATE_REJECT_WARNINGS]
    if bad:
        return None, bad[0]["message"]
    uses_capacity = data["movements"]["movements"][entry["id"]].get("equipment") or \
        isinstance(data["equipment"]["space"].get(entry["id"]), dict)
    if any(w["code"] == "quantity_approx" for w in warnings):
        return 1, "추정 수량으로 충분"
    if draft.get("expected_athletes") is None and uses_capacity:
        return 1, "예상 인원이 없어 수량 비교 안 함"
    return 0, "장비 충분(정확 수량) 또는 장비 불필요"


def choose_substitute(draft, scale, index, problem_issue, data, tried):
    """→ (선택 결과 dict 또는 None, 검토한 후보 목록)"""
    lst = _movement_list(draft, scale)
    old = lst[index]
    in_use = {m["id"] for i, m in enumerate(lst) if i != index}
    reviewed, usable = [], []
    for order, (cid, tier) in enumerate(_candidate_ids(old["id"], problem_issue, data)):
        if cid in in_use:
            reviewed.append({"id": cid, "result": "rejected", "reason": "이미 WOD에 있는 동작"})
            continue
        if cid in tried:
            reviewed.append({"id": cid, "result": "rejected", "reason": "이전 시도에서 이미 바꿨던 동작"})
            continue
        entry, note = _build_replacement(old, cid, data)
        if entry is None:
            reviewed.append({"id": cid, "result": "rejected", "reason": note})
            continue
        certainty, reason = evaluate_candidate(draft, entry, data)
        if certainty is None:
            reviewed.append({"id": cid, "result": "rejected", "reason": reason})
            continue
        reviewed.append({"id": cid, "result": "usable", "reason": reason})
        usable.append((certainty, tier, order, cid, entry, note, reason))
    if not usable:
        return None, reviewed
    certainty, tier, _, cid, entry, note, reason = min(usable, key=lambda u: u[:3])
    return {"entry": entry, "certainty": certainty, "tier": tier, "reps_note": note, "reason": reason}, reviewed


TIER_TEXT = {0: "등록된 대체 동작", 1: "같은 운동 패턴", 2: "운동 패턴 일부 겹침"}


# ---------------------------------------------------------------- 수정 1건

def fix_time(draft, problem):
    e = problem["issue"]
    field, before, after = e["field"], e["minutes"], e["max_minutes"]
    draft[field] = after
    why = "코치 요청 상한" if e["code"] == "workout_over_request" else "박스 본운동 상한"
    note = "작업량(반복 수)은 그대로이므로 시간 데이터가 없으면 이 시간 안에 끝나는지는 추정 불가" \
        if field == "time_cap_min" else None
    return {"type": "time", "issue_code": e["code"], "field": field,
            "before": before, "after": after,
            "reason": f"{why} {fmt_num(after)}분 초과 → {field} {fmt_num(before)} → {fmt_num(after)}",
            "note": note}


def fix_substitute(draft, problem, data, tried):
    e = problem["issue"]
    scale, index = e.get("scale"), e.get("index")
    if index is None:
        return None, {"reason": "문제 위치(index)를 알 수 없음"}
    lst = _movement_list(draft, scale)
    old = lst[index]
    key = (scale, index)
    choice, reviewed = choose_substitute(draft, scale, index, e, data, tried.setdefault(key, {old["id"]}))
    if choice is None:
        return None, {"reason": "조건을 만족하는 대체 동작 없음", "candidates": reviewed}
    lst[index] = choice["entry"]
    tried[key].add(choice["entry"]["id"])
    mv = data["movements"]["movements"]
    why = "수량 부족" if problem["kind"] == "shortage" else "사용 불가"
    scale_changes = []
    if scale is None:
        scale_changes = _propagate_to_scales(draft, old["id"], choice["entry"]["id"], data)
    return {"type": "substitute", "issue_code": e["code"], "location": _location_text(scale, index),
            "scale": scale, "before": old, "after": choice["entry"],
            "reason": f"{mv[old['id']]['display']} {why}({e['code']}) → "
                      f"{mv[choice['entry']['id']]['display']} ({TIER_TEXT[choice['tier']]}, {choice['reason']})",
            "reps_note": choice["reps_note"], "candidates": reviewed, "scale_changes": scale_changes}, None


def _propagate_to_scales(draft, old_id, new_id, data):
    """Rx에서 바꾼 동작을 스케일에서도 같이 바꾼다.

    스케일 동작은 수량 비교를 하지 않으므로, 그대로 두면 스케일 회원이 부족한 장비를 계속 쓰게 된다.
    단위 환산 근거가 없으면 바꾸지 않고 그 사실을 기록한다 (지어낸 반복 수 없음).
    """
    out = []
    for level, lst in sorted((draft.get("scales") or {}).items()):
        if any(m["id"] == new_id for m in lst):
            for i, m in enumerate(lst):
                if m["id"] == old_id:
                    out.append({"location": _location_text(level, i), "changed": False,
                                "reason": f"스케일 {level}에 이미 {new_id}가 있어 바꾸지 않음 — 코치·에이전트 확인 필요"})
            continue
        for i, m in enumerate(lst):
            if m["id"] != old_id:
                continue
            entry, note = _build_replacement(m, new_id, data)
            if entry is None:
                out.append({"location": _location_text(level, i), "changed": False, "reason": note})
                continue
            lst[i] = entry
            out.append({"location": _location_text(level, i), "changed": True, "before": m, "after": entry,
                        "reps_note": note})
    return out


# ---------------------------------------------------------------- 운영 선택지 근거 (자동 적용 안 함)

def shortage_options(problem, draft, rules):
    """수량 부족을 동작 변경으로 못 고쳤을 때, 운영 방식별 동시 사용 인원 계산을 근거로 붙인다."""
    e = problem["issue"]
    needed, have = e.get("needed"), e.get("have") or {}
    value, precision = have.get("value"), have.get("precision")
    if needed is None or value is None:
        return []
    approx = precision == "approx"
    label = "약 " if approx else ""
    basis = (rules.get("workout_time_basis") or {}).get(draft.get("format"))
    minutes = draft.get(basis) if basis else None
    partner = math.ceil(needed / 2)
    opts = [{
        "option": "파트너(2인 1조) 교대",
        "concurrent": partner, "have": value, "precision": precision,
        "fits": partner <= value,
        "evidence": f"동시 {partner}명 / 보유 {label}{fmt_num(value)}"
                    f" → {'충분' if partner <= value else '여전히 부족'}{' (추정 수량)' if approx else ''}",
        "tradeoff": "1인당 작업량이 절반 수준으로 바뀌어 운동 자극이 달라짐",
    }]
    if value > 0:
        heats = math.ceil(needed / value)
        per = math.ceil(needed / heats)
        block = f"WOD 블록 최소 {fmt_num(heats * minutes)}분 필요 (히트 {heats} × {fmt_num(minutes)}분)" \
            if minutes else "WOD 블록 시간 계산 불가 (본운동 시간 없음)"
        opts.append({
            "option": f"시차 출발 — {heats}개 히트로 나눠 앞 히트가 끝난 뒤 시작",
            "heats": heats, "concurrent": per, "have": value, "precision": precision, "fits": per <= value,
            "evidence": f"히트당 동시 {per}명 / 보유 {label}{fmt_num(value)}{' (추정 수량)' if approx else ''}; {block}",
            "tradeoff": "수업 시간이 늘어남. 같은 히트 안에서 동시에 출발하면 시차 효과 없음",
        })
    opts.append({
        "option": "스테이션별 시작 동작 분산",
        "fits": None,
        "evidence": "시작 위치만 다르게 하면 라운드가 진행되며 같은 장비에 다시 몰릴 수 있어 동시 사용 감소를 보장하지 않음",
        "tradeoff": "단독 해결책으로 보지 않음",
    })
    return opts


# ---------------------------------------------------------------- 품질 점검 (자동 수정 대상 아님)

def quality_warnings(draft):
    out = []
    if draft.get("group", "adult") == "adult":
        missing = [lv for lv in SCALE_LEVELS if lv not in (draft.get("scales") or {})]
        if missing:
            out.append(issue("scaling_missing",
                             f"성인 WOD 스케일 {', '.join(missing)}가 없습니다. 초안 scales에 A/B/C를 작성하세요.",
                             missing=missing))
    return out


# ---------------------------------------------------------------- 루프

def autofix(draft, data, max_attempts=DEFAULT_MAX_ATTEMPTS):
    """→ (errors, warnings, result). errors = 남은 문제, warnings = 최종 검증 경고 + 품질 경고."""
    current = copy.deepcopy(draft)
    history, changes, tried = [], [], {}
    status, unresolved = None, []
    attempts = 0
    while True:
        reports = run_validators(current, data)
        if any(r["exit_code"] == EXIT_INPUT for r in reports.values()):
            history.append({"attempt": attempts, "validation": summarize(reports), "change": None})
            status = "input_error"
            unresolved = [{"kind": "input_error", "source": n, "issue": e}
                          for n, r in reports.items() for e in r["errors"]]
            break
        problems = find_problems(reports)
        step = {"attempt": attempts, "validation": summarize(reports),
                "problems": [p["issue"]["code"] for p in problems], "change": None}
        history.append(step)
        if not problems:
            status = "passed"
            break
        if attempts >= max_attempts:
            status = "unresolved"
            unresolved = problems
            break
        change, failures = None, []
        for p in problems:
            if p["kind"] == "time":
                change = fix_time(current, p)
            elif p["kind"] in ("substitute_error", "shortage"):
                change, fail = fix_substitute(current, p, data, tried)
                if change is None:
                    failures.append((p, fail))
            if change:
                break
        if change is None:
            status = "needs_coach"
            unresolved = problems
            break
        attempts += 1
        change["attempt"] = attempts
        step["change"] = change
        changes.append(change)

    # 남은 문제마다 왜 자동으로 못 고쳤는지 설명을 붙인다
    out_errors = []
    for p in unresolved:
        e = dict(p["issue"])
        e["source"] = p["source"]
        if p["kind"] == "not_autofixable":
            e["unresolved_reason"] = NOT_AUTOFIXABLE_REASON.get(e["code"], "자동 수정 규칙 없음 — 코치 판단 필요")
        elif p["kind"] == "input_error":
            e["unresolved_reason"] = "초안 구조 오류 — 초안을 고쳐야 검증할 수 있습니다"
        elif status == "unresolved":
            e["unresolved_reason"] = f"수정 {max_attempts}회를 모두 사용해 더 고치지 않았습니다"
        else:
            e["unresolved_reason"] = "조건을 만족하는 대체 동작이 없습니다 (아래 후보 검토 참고)"
            if p["kind"] in ("substitute_error", "shortage"):
                _, fail = fix_substitute(copy.deepcopy(current), p, data, copy.deepcopy(tried))
                e["candidates"] = (fail or {}).get("candidates", [])
        if p["kind"] == "shortage":
            e["operation_options"] = shortage_options(p, current, data["rules"])
        out_errors.append(e)

    final_warnings = []
    if status != "input_error":
        for name in ("simulate", "check_equipment"):
            for w in reports[name]["warnings"]:
                if w["code"] in SHORTAGE_CODES and status != "passed":
                    continue  # 남은 문제(errors)에 이미 포함
                final_warnings.append(dict(w, source=name))
        final_warnings += [dict(w, source=SCRIPT) for w in quality_warnings(current)]

    final_text = None
    if status != "input_error":
        # 최종 초안에서 화이트보드 텍스트를 생성한다 (수정 후 출력이 초안과 일치하도록)
        from render_wod import render_sections, whiteboard_text
        sections, _ = render_sections(current, data)
        final_text = whiteboard_text(current, sections, data)

    result = {
        "final_text": final_text,
        "status": status,
        "attempts_used": attempts,
        "max_attempts": max_attempts,
        "validation_runs": len(history),
        "changed": bool(changes),
        "changes": changes,
        "history": history,
        "final_draft": current,
        "final_reports": reports,
    }
    return out_errors, final_warnings, result


# ---------------------------------------------------------------- 수정 이력 원장

def default_ledger_path(draft_path):
    p = Path(draft_path)
    return p.with_name(p.stem + ".history.json")


def _state(h):
    v = h["validation"]
    return {"simulate_exit": v["simulate"]["exit_code"], "check_equipment_exit": v["check_equipment"]["exit_code"],
            "problems": h.get("problems") or []}


def load_ledger(path, date=None):
    """원장 읽기. 없으면 None. 손상·형식 불일치·날짜 불일치면 InputError (덮어쓰지 않기 위해)."""
    path = Path(path)
    if not path.exists():
        return None
    try:
        ledger = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise InputError(f"수정 이력 원장 {path}를 읽을 수 없습니다 ({e}). 덮어쓰지 않았습니다. 파일을 확인하세요.")
    if not isinstance(ledger, dict) or ledger.get("schema") != LEDGER_SCHEMA or not isinstance(ledger.get("runs"), list):
        raise InputError(f"수정 이력 원장 {path}의 형식이 {LEDGER_SCHEMA}가 아닙니다. 덮어쓰지 않았습니다.")
    if date is not None and ledger.get("date") not in (None, date):
        raise InputError(f"수정 이력 원장 {path}는 {ledger.get('date')} 초안의 것입니다 (지금 초안 {date}). "
                         f"--history로 다른 경로를 지정하세요.")
    return ledger


def append_run(ledger, input_draft, result, at=None):
    """원장에 이번 실행을 추가한 새 원장을 돌려준다 (이전 실행은 그대로 둔다)."""
    in_sha = sha256_json(input_draft)
    out_sha = sha256_json(result["final_draft"]) if result["status"] != "input_error" else None
    if ledger is None:
        ledger = {"schema": LEDGER_SCHEMA, "date": input_draft.get("date") if isinstance(input_draft, dict) else None,
                  "original_draft": copy.deepcopy(input_draft), "original_sha256": in_sha, "runs": []}
    else:
        ledger = copy.deepcopy(ledger)
    prev_out = ledger["runs"][-1]["output_sha256"] if ledger["runs"] else None
    hist = result.get("history") or []
    ledger["runs"].append({
        "run": len(ledger["runs"]) + 1,
        "at": at or now_iso(),
        "input_sha256": in_sha,
        "output_sha256": out_sha,
        # 직전 실행의 출력과 이번 입력이 다르면 그 사이에 초안이 손으로 바뀐 것
        "input_matches_previous_output": None if prev_out is None else prev_out == in_sha,
        "status": result["status"],
        "attempts_used": result["attempts_used"],
        "max_attempts": result["max_attempts"],
        "validation_runs": result["validation_runs"],
        "before": _state(hist[0]) if hist else None,
        "after": _state(hist[-1]) if hist else None,
        "changes": copy.deepcopy(result["changes"]),
    })
    return ledger


def ledger_summary(ledger):
    """누적 요약: 최초 초안 해시, 실행 수, 누적 수정 수·내역, 최초 수정 전 상태, 마지막 수정 후 상태."""
    if not ledger:
        return None
    runs = ledger["runs"]
    changes = [dict(c, run=r["run"]) for r in runs for c in r.get("changes") or []]
    return {
        "original_sha256": ledger.get("original_sha256"),
        "current_sha256": runs[-1]["output_sha256"] if runs else None,
        "runs": len(runs),
        "attempts_total": sum(r.get("attempts_used") or 0 for r in runs),
        "changes": changes,
        "first_before": runs[0]["before"] if runs else None,
        "last_after": runs[-1]["after"] if runs else None,
        "chain_intact": all(r["input_matches_previous_output"] in (None, True) for r in runs),
        "manual_edits_between_runs": [r["run"] for r in runs if r["input_matches_previous_output"] is False],
    }


# ---------------------------------------------------------------- 출력

STATUS_TEXT = {
    "passed": "통과 — 두 검증 모두 종료 코드 0, 수량 부족 없음",
    "needs_coach": "코치 판단 필요 — 자동으로 고칠 수 있는 방법이 없는 문제가 남음",
    "unresolved": "미해결 — 수정 횟수를 모두 사용했지만 문제가 남음",
    "input_error": "입력 오류 — 검증하지 못함",
}


def render_text(report):
    r = report["result"]
    lines = [f"[자동 수정] {STATUS_TEXT[r['status']]}",
             f"이번 실행: 수정 {r['attempts_used']}/{r['max_attempts']}회, 검증 실행 {r['validation_runs']}회"]
    lg = r.get("ledger")
    if lg:
        lines.append(f"누적 이력: 실행 {lg['runs']}회, 수정 {lg['attempts_total']}회 (원장 {r.get('ledger_path')})"
                     + ("" if lg["chain_intact"] else f" — 실행 {lg['manual_edits_between_runs']} 앞에서 초안이 손으로 바뀜"))
    for h in r["history"]:
        v = h["validation"]
        lines.append(f"  검증 #{h['attempt']}: simulate exit {v['simulate']['exit_code']}, "
                     f"check_equipment exit {v['check_equipment']['exit_code']}"
                     + (f" / 문제: {', '.join(h['problems'])}" if h.get("problems") else ""))
        c = h.get("change")
        if c:
            lines.append(f"    → 수정 {c['attempt']}: {c['reason']}")
            if c.get("reps_note"):
                lines.append(f"      ({c['reps_note']})")
            if c.get("note"):
                lines.append(f"      ※ {c['note']}")
            for sc in c.get("scale_changes") or []:
                if sc["changed"]:
                    lines.append(f"      스케일 반영 {sc['location']}: {sc['before']['id']} {fmt_num(sc['before']['reps'])}"
                                 f" → {sc['after']['id']} {fmt_num(sc['after']['reps'])}"
                                 + (f" ({sc['reps_note']})" if sc.get("reps_note") else ""))
                else:
                    lines.append(f"      스케일 미반영 {sc['location']}: {sc['reason']}")
    if report["errors"]:
        lines.append(f"남은 문제 {len(report['errors'])}건")
        for e in report["errors"]:
            lines.append(f"  ✗ {e['message']}")
            lines.append(f"    이유: {e['unresolved_reason']}")
            for c in e.get("candidates") or []:
                lines.append(f"    - 후보 {c['id']}: {c['reason']}")
            for o in e.get("operation_options") or []:
                lines.append(f"    · {o['option']}: {o['evidence']} — {o['tradeoff']}")
    if report["warnings"]:
        lines.append(f"경고 {len(report['warnings'])}건")
        lines += [f"  ! {w['message']}" for w in report["warnings"]]
    lines.append(f"결과: 종료 코드 {report['exit_code']}")
    return "\n".join(lines)


def _out_path_allowed(path):
    wods = (ROOT / "wods").resolve()
    p = Path(path).resolve()
    return p != wods and wods not in p.parents


def main(argv=None):
    parser = argparse.ArgumentParser(prog="autofix.py", description="WOD 초안을 검증하고 고칠 수 있는 문제를 최대 N회 수정·재검증한다.")
    parser.add_argument("draft", help="WOD 초안 JSON 파일 경로")
    parser.add_argument("--out", default=None, help="수정된 초안을 쓸 경로 (wods/ 안은 거부). 없으면 파일을 쓰지 않음")
    parser.add_argument("--history", default=None,
                        help="수정 이력 원장 경로 (기본: --out이 있으면 <out 이름>.history.json, 없으면 원장 안 씀)")
    parser.add_argument("--max-attempts", type=int, default=DEFAULT_MAX_ATTEMPTS, help="최대 수정 횟수 (기본 3)")
    parser.add_argument("--data-dir", default=None, help=f"데이터 디렉터리 (기본: {DEFAULT_DATA_DIR})")
    parser.add_argument("--json", action="store_true", help="JSON으로 출력")
    args = parser.parse_args(argv)

    try:
        if args.out and not _out_path_allowed(args.out):
            raise InputError("--out: wods/ 에는 쓸 수 없습니다. 승인된 WOD 저장은 save_wod.py만 합니다.")
        if args.max_attempts < 0:
            raise InputError("--max-attempts: 0 이상이어야 합니다.")
        history_path = args.history or (default_ledger_path(args.out) if args.out else None)
        if history_path and not _out_path_allowed(history_path):
            raise InputError("--history: wods/ 에는 쓸 수 없습니다.")
        data = load_data(args.data_dir)
        draft = load_json(args.draft)
        ledger = load_ledger(history_path, draft.get("date") if isinstance(draft, dict) else None) \
            if history_path else None
        errors, warnings, result = autofix(draft, data, args.max_attempts)
        report = make_report(SCRIPT, errors, warnings, result)
        if result["status"] == "input_error":
            report["exit_code"] = EXIT_INPUT
        if args.out and result["status"] != "input_error":
            atomic_write_text(args.out, dump_json(result["final_draft"]), overwrite=True)
            result["written_to"] = str(args.out)
        result["ledger"] = None
        if history_path and result["status"] != "input_error":
            ledger = append_run(ledger, draft, result)
            atomic_write_text(history_path, dump_json(ledger), overwrite=True)
            result["ledger_path"] = str(history_path)
            result["ledger"] = ledger_summary(ledger)
        result["final_sha256"] = sha256_json(result["final_draft"]) if result["status"] != "input_error" else None
        result["approval_code"] = result["final_sha256"][:CODE_LEN] if result["final_sha256"] else None
    except InputError as e:
        report = input_error_report(SCRIPT, e)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif report["exit_code"] == EXIT_INPUT and report["result"] is None:
        print("입력 오류 — 처리하지 않았습니다.", file=sys.stderr)
        for e in report["errors"]:
            print(e["message"], file=sys.stderr)
    else:
        print(render_text(report))
    return report["exit_code"]


assert EXIT_OK == 0 and EXIT_FAIL == 1  # make_report가 쓰는 종료 코드와 일치해야 한다

if __name__ == "__main__":
    sys.exit(main())
