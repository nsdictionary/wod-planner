"""검증된 초안 JSON → 최종 출력(화이트보드 WOD + 검증 요약 + 코치 확인 항목).

  python3 scripts/render_wod.py <draft.json> [--total 60 --block ... --interval boxing=4x3/1 --require boxing]
      [--autofix-report PATH] [--check-text FILE] [--data-dir DIR] [--json]

하는 일
  1) 화이트보드 텍스트를 초안 JSON에서 생성한다 (LLM이 손으로 옮겨 쓰지 않는다).
     Rx와 Scale A/B/C의 모든 동작을 한 줄에 하나씩, 횟수·거리·load·무게·월볼 타깃과 함께 쓴다.
     스케일에 없는 동작이나 수치는 보충하지 않는다. 스케일 동작 수가 Rx와 다르면 오류로 알린다.
  2) 생성한 텍스트가 초안의 모든 동작 줄을 포함하는지 다시 검사한다 (완전성 검사).
  3) simulate · check_equipment(그리고 --total이 있으면 check_class)를 지금 실행해 검증 요약을 만든다.
     passed는 코드로 검사한 항목에만 쓴다. 자동 검증하지 않는 항목은 coach_review로 따로 둔다.
  4) --autofix-report가 있으면 자동 수정 전/후 상태와 수정 내역을 붙인다.
     보고서의 final_draft가 지금 초안과 다르면 전후 비교를 생략하고 경고한다.
  5) --check-text FILE: 다른 곳(응답 등)에 옮겨 쓴 WOD 텍스트가 생성 결과의 모든 줄을 포함하는지 검사한다.

종료 코드: 0 = 실패 항목 없음(경고 가능), 1 = 실패 항목 있음(출력 불완전, 검증 오류), 2 = 입력 오류.
"""

import argparse
import copy
import json
import sys
from pathlib import Path

from check_class import add_class_arguments, class_report_from_args
from check_equipment import check_equipment
from common import (
    DEFAULT_DATA_DIR,
    EXIT_FAIL,
    EXIT_INPUT,
    EXIT_OK,
    SCALE_LEVELS,
    InputError,
    fmt_num,
    input_error_report,
    issue,
    load_data,
    load_json,
    make_report,
    validate_draft,
)
from simulate import simulate

SCRIPT = "render_wod"
WEIGHT_UNIT = {"by_weight_kg": "kg", "by_weight_lb": "lb"}

# 자동 검증하지 않는 항목 — 출력에 항상 "코치 확인"으로 표시한다
COACH_REVIEW_ITEMS = [
    "운동 자극·강도가 오늘 수업 목적에 맞는지 (동작 조합, 반복 수)",
    "Scale A/B/C의 난도 단계가 회원 수준에 맞는지",
    "준비운동·마무리 내용이 WOD 동작을 충분히 준비·회복시키는지",
]
COACH_REVIEW_BOXING = "복싱 드릴의 내용·교육적 순서·강도 (시간 합계만 자동 검증됨)"
COACH_REVIEW_CONVERSION = "자동 수정에서 거리로 환산한 반복 수가 운동 의도에 맞는지"

STATUS_MARK = {
    "passed": "✓ passed",
    "passed_with_warnings": "✓ passed (경고 있음)",
    "estimated": "~ 추정",
    "failed": "✗ failed",
    "shortage": "! 부족",
    "not_checked": "- 검증 안 함",
    "not_estimable": "- 추정 불가",
}


# ---------------------------------------------------------------- 화이트보드 텍스트

def _weight_text(m, info, data):
    parts = []
    for eq_id, ws in (m.get("weights") or {}).items():
        e = data["equipment"]["equipment"].get(eq_id) or {}
        unit = next((u for f, u in WEIGHT_UNIT.items() if e.get(f) is not None), "")
        parts.append("/".join(fmt_num(w) for w in ws) + (f" {unit}" if unit else ""))
    return parts


def movement_line(m, data):
    """동작 1개 → 화이트보드 한 줄. 미등록 동작이면 None."""
    info = data["movements"]["movements"].get(m["id"])
    if info is None:
        return None
    reps = fmt_num(m["reps"])
    head = f"{reps}m {info['display']}" if info["unit"] == "m" else f"{reps} {info['display']}"
    extras = []
    if m.get("load"):
        extras.append(m["load"])
    elif m.get("weights"):
        extras += _weight_text(m, info, data)
    if "wall_target" in (info.get("space_tags") or []):
        h = ((data["equipment"]["space"].get("wall_target") or {}).get("height_m") or {})
        if h.get("value") is not None:
            extras.append(f"target {'~' if h.get('precision') == 'approx' else ''}{fmt_num(h['value'])}m")
    return head + "".join(f" ({x})" for x in extras)


def header_line(draft):
    fmt = draft.get("format")
    if fmt == "AMRAP":
        return f"WOD - AMRAP {fmt_num(draft['duration_min'])}" if draft.get("duration_min") else "WOD - AMRAP"
    if fmt == "EMOM":
        return f"WOD - EMOM {fmt_num(draft['duration_min'])}" if draft.get("duration_min") else "WOD - EMOM"
    if fmt == "FOR_TIME":
        rounds = draft.get("rounds")
        head = "WOD - For Time" if rounds in (None, 1) else f"WOD - {rounds} Rounds For Time"
        tc = draft.get("time_cap_min")
        return head + (f" (TC {fmt_num(tc)})" if tc else "")
    return f"WOD - {fmt}"


def render_sections(draft, data):
    """→ (sections, errors). section = {"name", "lines", "expected"(동작 수)}"""
    errors, sections = [], []
    groups = [("Rx", None, draft["movements"])]
    for level in SCALE_LEVELS:
        if level in (draft.get("scales") or {}):
            groups.append((f"Scale {level}", level, draft["scales"][level]))
    rx_count = len(draft["movements"])
    for name, level, movements in groups:
        lines = []
        for i, m in enumerate(movements):
            line = movement_line(m, data)
            if line is None:
                errors.append(issue("render_unregistered",
                                    f"{name} {i + 1}번째 동작 '{m['id']}'는 미등록이라 화이트보드 이름을 만들 수 없습니다.",
                                    section=name, index=i))
                continue
            lines.append(line)
        if level is not None and len(movements) != rx_count:
            errors.append(issue("scale_movement_count_mismatch",
                                f"{name}의 동작 수 {len(movements)}개가 Rx 동작 수 {rx_count}개와 다릅니다. "
                                f"빠진 동작을 임의로 채우지 않았으니 초안 scales.{level}를 고쳐야 합니다.",
                                section=name, expected=rx_count, actual=len(movements)))
        sections.append({"name": name, "lines": lines, "expected": len(movements)})
    if draft.get("group", "adult") == "adult":
        missing = [lv for lv in SCALE_LEVELS if lv not in (draft.get("scales") or {})]
        if missing:
            errors.append(issue("scale_missing",
                                f"성인 WOD인데 Scale {', '.join(missing)}가 초안에 없습니다. 스케일을 임의로 만들지 않았습니다.",
                                missing=missing))
    return sections, errors


def whiteboard_text(draft, sections):
    out = [header_line(draft)]
    for s in sections:
        if s["name"] != "Rx":
            out += ["", s["name"]]
        out += s["lines"]
    return "\n".join(out)


def missing_lines(text, draft, data):
    """text에 없는 화이트보드 줄 목록. 각 동작 줄이 한 줄 전체로 들어 있어야 한다."""
    sections, _ = render_sections(draft, data)
    have = {ln.strip() for ln in text.splitlines()}
    expected = [header_line(draft)] + [s["name"] for s in sections if s["name"] != "Rx"] + \
        [ln for s in sections for ln in s["lines"]]
    return [ln for ln in expected if ln not in have]


# ---------------------------------------------------------------- 검증 요약

def _item(item, status, source, detail):
    return {"item": item, "status": status, "source": source, "detail": detail}


def _workout_detail(v):
    if v["minutes"] is None:
        return "본운동 시간이 초안에 없습니다."
    field = "TC" if v["basis_field"] == "time_cap_min" else "설정 시간"
    limit = (f"코치 요청 상한 {fmt_num(v['max_minutes'])}분, 박스 상한 {fmt_num(v['rules_max_minutes'])}분"
             if v.get("limit_source") == "request" else f"박스 상한 {fmt_num(v['max_minutes'])}분")
    mark = "≤" if v["status"] == "verified" else ">"
    return f"{v['format']} {field} {fmt_num(v['minutes'])}분 {mark} 적용 상한 {fmt_num(v['max_minutes'])}분 ({limit})."


def _equipment_status(items):
    statuses = [e.get("status") for it in items for e in it["equipment"]]
    if any(s in ("short", "possibly_short") for s in statuses):
        return "shortage"
    if any(s in ("unknown", "not_compared", "availability_unknown") for s in statuses):
        return "not_checked"
    if any(s == "enough_approx" for s in statuses):
        return "passed_with_warnings"
    return "passed"


def verification_summary(sim, eq, render_errors, class_report=None):
    checks = []
    if sim["exit_code"] == EXIT_INPUT or eq["exit_code"] == EXIT_INPUT:
        checks.append(_item("초안 검증", "failed", "simulate/check_equipment", "초안 구조 오류로 검증하지 못했습니다."))
        return checks

    v = sim["result"]["workout_time"]
    checks.append(_item("본운동 시간 상한", "passed" if v["status"] == "verified" else "failed", "simulate",
                        _workout_detail(v)))
    est = sim["result"]["estimate"]
    if est["status"] == "estimated":
        checks.append(_item("완주 가능성", "estimated", "simulate", "시간 데이터 범위로 추정했습니다 (근거는 simulate 출력)."))
    else:
        missing = ", ".join(m["item"] for m in est.get("missing") or [])
        checks.append(_item("완주 가능성", "not_estimable" if est["status"] == "not_estimable" else "not_checked",
                            "simulate", est["reason"] + (f" 누락: {missing}." if missing else "")))

    rx_errors = [e for e in eq["errors"] if "scale" not in e]
    sc_errors = [e for e in eq["errors"] if "scale" in e]
    checks.append(_item("Rx 동작 사용 가능 (미보유·금지·층고·무게)", "failed" if rx_errors else "passed",
                        "check_equipment",
                        f"오류 {len(rx_errors)}건: " + " / ".join(e["message"] for e in rx_errors) if rx_errors
                        else "모든 Rx 동작이 보유 장비·공간 조건을 만족합니다."))
    rx_items = eq["result"]["movements"]
    st = _equipment_status(rx_items)
    detail = {
        "passed": "인원 대비 장비가 정확한 수량으로 충분합니다.",
        "passed_with_warnings": "충분하지만 일부는 추정 수량 기준입니다 (경고 참고).",
        "shortage": "인원 대비 장비가 부족하거나 부족할 수 있습니다 (경고 참고).",
        "not_checked": "수량 미확인 또는 예상 인원 없음으로 일부 장비 수량을 비교하지 못했습니다.",
    }[st]
    checks.append(_item("Rx 장비 수량 (예상 인원 기준)", st, "check_equipment", detail))

    scales = eq["result"].get("scales")
    if scales:
        checks.append(_item("스케일 동작 사용 가능", "failed" if sc_errors else "passed", "check_equipment",
                            f"오류 {len(sc_errors)}건." if sc_errors else
                            f"Scale {', '.join(sorted(scales))}의 모든 동작이 보유 장비·공간 조건을 만족합니다."))
        checks.append(_item("스케일 장비 수량", "not_checked", "check_equipment",
                            "스케일별 인원 배분을 몰라 비교하지 않았습니다. Rx와 같은 장비를 나눠 쓰는 총량도 확인하지 않았습니다."))
    else:
        checks.append(_item("스케일 동작 사용 가능", "not_checked", "check_equipment", "초안에 스케일이 없습니다."))

    checks.append(_item("화이트보드 출력 완전성 (Rx·스케일 모든 동작)", "failed" if render_errors else "passed",
                        SCRIPT, " / ".join(e["message"] for e in render_errors) if render_errors
                        else "초안의 모든 동작이 이름·횟수·표기와 함께 출력됐습니다."))

    if class_report is None:
        checks.append(_item("수업 시간 합계", "not_checked", "check_class", "수업 구성 인자(--total, --block)가 없습니다."))
        return checks
    if class_report["exit_code"] == EXIT_INPUT:
        checks.append(_item("수업 시간 합계", "failed", "check_class", "수업 구성 인자 오류로 검증하지 못했습니다."))
        return checks
    r = class_report["result"]
    ce = {e["code"]: e for e in class_report["errors"]}
    cw = {w["code"]: w for w in class_report["warnings"]}
    checks.append(_item("수업 시간 합계", "failed" if "class_total_mismatch" in ce else "passed", "check_class",
                        ce["class_total_mismatch"]["message"] + "." if "class_total_mismatch" in ce else
                        f"블록 합계 {fmt_num(r['block_sum_min'])}분 = 수업 시간 {fmt_num(r['total_min'])}분."))
    missing_blocks = [e for e in class_report["errors"] if e["code"] == "class_block_missing"]
    checks.append(_item("필수 블록", "failed" if missing_blocks else "passed", "check_class",
                        " / ".join(e["message"] for e in missing_blocks) if missing_blocks
                        else "필수 블록이 모두 있습니다."))
    if "wod_block_too_short" in ce:
        checks.append(_item("WOD 블록 ≥ 본운동", "failed", "check_class", ce["wod_block_too_short"]["message"] + "."))
    elif r.get("workout") and r["workout"].get("minutes") is not None and r["wod_block_min"]:
        checks.append(_item("WOD 블록 ≥ 본운동", "passed_with_warnings" if "wod_block_no_buffer" in cw else "passed",
                            "check_class", f"WOD 블록 {fmt_num(r['wod_block_min'])}분, 본운동 {fmt_num(r['workout']['minutes'])}분."))
    for b in r["blocks"]:
        if b["kind"] != "boxing":
            continue
        mismatch = [e for e in class_report["errors"] if e["code"] == "interval_total_mismatch" and e["kind"] == "boxing"]
        if mismatch:
            checks.append(_item("복싱 드릴 내부 시간", "failed", "check_class", mismatch[0]["message"] + "."))
        elif b.get("intervals"):
            checks.append(_item("복싱 드릴 내부 시간", "passed", "check_class",
                                f"{b['intervals']['text']} = 블록 {fmt_num(b['minutes'])}분."))
        else:
            checks.append(_item("복싱 드릴 내부 시간", "not_checked", "check_class",
                                "라운드·운동·휴식 시간이 지정되지 않았습니다 (--interval)."))
    return checks


def coach_review_items(class_report, autofix_report):
    items = list(COACH_REVIEW_ITEMS)
    if class_report and class_report.get("result") and any(b["kind"] == "boxing" for b in class_report["result"]["blocks"]):
        items.append(COACH_REVIEW_BOXING)
    if autofix_report and any(c.get("reps_note") for c in autofix_report["result"].get("changes") or []):
        items.append(COACH_REVIEW_CONVERSION)
    return items


def autofix_section(autofix_report, draft):
    """→ (section 또는 None, warnings)"""
    r = autofix_report.get("result") or {}
    if r.get("final_draft") != draft:
        return None, [issue("autofix_report_mismatch",
                            "자동 수정 보고서의 최종 초안이 지금 초안과 달라 전후 비교를 표시하지 않았습니다. autofix를 다시 실행하세요.")]
    hist = r.get("history") or []
    def state(h):
        v = h["validation"]
        return {"simulate_exit": v["simulate"]["exit_code"], "check_equipment_exit": v["check_equipment"]["exit_code"],
                "problems": h.get("problems") or []}
    return {"status": r.get("status"), "attempts_used": r.get("attempts_used"), "max_attempts": r.get("max_attempts"),
            "validation_runs": r.get("validation_runs"),
            "before": state(hist[0]) if hist else None, "after": state(hist[-1]) if hist else None,
            "changes": [{"reason": c["reason"], "reps_note": c.get("reps_note"), "note": c.get("note"),
                         "scale_changes": c.get("scale_changes") or []} for c in r.get("changes") or []]}, []


# ---------------------------------------------------------------- 실행

def build(draft, data, class_report=None, autofix_report=None, check_text=None):
    """→ (errors, warnings, result)"""
    d = validate_draft(copy.deepcopy(draft))
    sim = make_report("simulate", *simulate(d, data))
    eq = make_report("check_equipment", *check_equipment(d, data))
    sections, render_errors = render_sections(d, data)
    text = whiteboard_text(d, sections)
    # 생성한 텍스트를 다시 검사한다 (생성 로직 오류 방지)
    gaps = missing_lines(text, d, data)
    if gaps:
        render_errors.append(issue("render_incomplete", f"생성한 텍스트에 빠진 줄이 있습니다: {gaps}", missing=gaps))

    warnings = []
    af = None
    if autofix_report is not None:
        af, w = autofix_section(autofix_report, draft)
        warnings += w
    checks = verification_summary(sim, eq, render_errors, class_report)
    text_check = None
    if check_text is not None:
        gaps = missing_lines(check_text, d, data)
        text_check = {"complete": not gaps, "missing_lines": gaps}
        checks.append(_item("옮겨 쓴 WOD 텍스트 완전성", "failed" if gaps else "passed", SCRIPT,
                            f"빠진 줄 {len(gaps)}개: {' | '.join(gaps)}" if gaps else
                            "생성 결과의 모든 줄이 들어 있습니다."))

    errors = [dict(e, source=SCRIPT) for e in render_errors]
    for name, rep in (("simulate", sim), ("check_equipment", eq)):
        errors += [dict(e, source=name) for e in rep["errors"]]
        warnings += [dict(w, source=name) for w in rep["warnings"]]
    if class_report is not None:
        errors += [dict(e, source="check_class") for e in class_report["errors"]]
        warnings += [dict(w, source="check_class") for w in class_report["warnings"]]
    if text_check and not text_check["complete"]:
        errors.append(issue("text_incomplete", "옮겨 쓴 WOD 텍스트에 빠진 줄이 있습니다.",
                            missing=text_check["missing_lines"], source=SCRIPT))

    result = {
        "whiteboard": text,
        "sections": sections,
        "checks": checks,
        "coach_review": coach_review_items(class_report, autofix_report),
        "autofix": af,
        "class_blocks": class_report["result"]["blocks"] if class_report and class_report.get("result") else None,
        "text_check": text_check,
    }
    return errors, warnings, result


def _clock(minutes):
    sec = int(round(minutes * 60))
    h, m, s = sec // 3600, sec % 3600 // 60, sec % 60
    return f"{h}:{m:02d}" if s == 0 else f"{h}:{m:02d}:{s:02d}"


def render_text(report):
    r = report["result"]
    out = ["[WOD 화이트보드 — 초안 JSON에서 생성]", r["whiteboard"], ""]
    if r.get("class_blocks"):
        out.append("[수업 시간표 — check_class 결과]")
        for b in r["class_blocks"]:
            out.append(f"{_clock(b['start_min'])}–{_clock(b['end_min'])}  {b['label']} ({fmt_num(b['minutes'])})")
            iv = b.get("intervals")
            if iv:
                out.append(f"    {iv['text']}")
                for t in iv["timeline"]:
                    label = f"Round {t['round']}" if t["type"] == "work" else "Rest"
                    out.append(f"    {_clock(t['start_min'])}–{_clock(t['end_min'])}  {label}")
        out.append("")
    if r.get("autofix"):
        a = r["autofix"]
        out.append(f"[자동 수정 — {a['status']}, 수정 {a['attempts_used']}/{a['max_attempts']}회, 검증 실행 {a['validation_runs']}회]")
        for label, st in (("수정 전", a["before"]), ("수정 후", a["after"])):
            probs = ", ".join(st["problems"]) if st["problems"] else "없음"
            out.append(f"{label}: simulate exit {st['simulate_exit']}, check_equipment exit {st['check_equipment_exit']}, 문제: {probs}")
        for i, c in enumerate(a["changes"], 1):
            out.append(f"수정 {i}: {c['reason']}")
            if c.get("reps_note"):
                out.append(f"    {c['reps_note']}")
            for sc in c["scale_changes"]:
                if sc.get("changed"):
                    out.append(f"    스케일 {sc['location']}: {sc['before']['id']} {fmt_num(sc['before']['reps'])}"
                               f" → {sc['after']['id']} {fmt_num(sc['after']['reps'])}")
                else:
                    out.append(f"    스케일 {sc['location']} 미반영: {sc['reason']}")
        out.append("")
    out.append("[검증 요약 — 이번 실행 결과]")
    for c in r["checks"]:
        out.append(f"{STATUS_MARK[c['status']]} · {c['item']} — {c['detail']} ({c['source']})")
    out.append("")
    if report["warnings"]:
        out.append(f"[남은 경고 {len(report['warnings'])}건]")
        out += [f"! {w['message']}" for w in report["warnings"]]
        out.append("")
    if report["errors"]:
        out.append(f"[오류 {len(report['errors'])}건]")
        out += [f"✗ {e['message']}" for e in report["errors"]]
        out.append("")
    out.append("[코치 확인 필요 — 자동 검증하지 않음]")
    out += [f"- {x}" for x in r["coach_review"]]
    out.append(f"결과: 종료 코드 {report['exit_code']}")
    return "\n".join(out)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="render_wod.py", description="검증된 초안에서 최종 WOD 출력과 검증 요약을 만든다.")
    parser.add_argument("draft", help="WOD 초안 JSON 파일 경로")
    add_class_arguments(parser, total_required=False)
    parser.add_argument("--autofix-report", default=None, help="autofix.py --json 출력 파일 (전후 비교 표시)")
    parser.add_argument("--check-text", default=None, help="옮겨 쓴 WOD 텍스트 파일 (모든 줄 포함 여부 검사)")
    parser.add_argument("--data-dir", default=None, help=f"데이터 디렉터리 (기본: {DEFAULT_DATA_DIR})")
    parser.add_argument("--json", action="store_true", help="JSON으로 출력")
    args = parser.parse_args(argv)

    try:
        data = load_data(args.data_dir)
        draft = load_json(args.draft)
        validate_draft(copy.deepcopy(draft))
        class_report = None
        if args.total is not None:
            class_report = class_report_from_args(args, validate_draft(copy.deepcopy(draft)), data)
        elif args.block or args.interval or args.require:
            raise InputError("--block/--interval/--require는 --total과 함께 써야 합니다.")
        autofix_report = load_json(args.autofix_report) if args.autofix_report else None
        check_text = None
        if args.check_text:
            try:
                check_text = Path(args.check_text).read_text(encoding="utf-8")
            except OSError as e:
                raise InputError(f"--check-text 파일을 읽을 수 없습니다: {e}")
        errors, warnings, result = build(draft, data, class_report, autofix_report, check_text)
        report = make_report(SCRIPT, errors, warnings, result)
    except InputError as e:
        report = input_error_report(SCRIPT, e)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif report["exit_code"] == EXIT_INPUT:
        print("입력 오류 — 처리하지 않았습니다.", file=sys.stderr)
        for e in report["errors"]:
            print(e["message"], file=sys.stderr)
    else:
        print(render_text(report))
    return report["exit_code"]


assert (EXIT_OK, EXIT_FAIL) == (0, 1)

if __name__ == "__main__":
    sys.exit(main())
