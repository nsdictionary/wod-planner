"""WOD 본운동 시간 검증 + 완주 가능성 추정.

  python3 scripts/simulate.py <draft.json> [--data-dir DIR] [--json]

두 단계를 분리해 출력한다.
  1) 본운동 시간 검증 (verified/failed): 형식과 설정 시간만으로 결정된다. 시간 데이터가 없어도 항상 수행.
     AMRAP/EMOM = duration_min, For Time = time_cap_min(필수). 상한 = rules.md workout_max_min(30분).
  2) 완주 가능성 추정 (estimated/not_estimable/skipped): 근거 있는 시간 범위가 모두 있을 때만 계산.
     하나라도 없으면 계산하지 않고 누락 항목을 나열한다. 시간 값을 임의로 만들지 않는다.

종료 코드: 0 = 본운동 검증 통과(추정 불가여도 0), 1 = 규칙 위반, 2 = 입력 오류.
"""

import math
import sys

from common import (
    draft_label,
    fmt_num,
    fmt_sec,
    issue,
    render_issues,
    render_verdict,
    run_cli,
)

SCRIPT = "simulate"
FORMAT_LABEL = {"AMRAP": "AMRAP", "EMOM": "EMOM", "FOR_TIME": "For Time"}
FIELD_LABEL = {"duration_min": "설정 시간", "time_cap_min": "TC"}


# ---------------------------------------------------------------- 1) 본운동 시간 검증

def verify_workout_time(draft, rules):
    """→ (errors, warnings, section)"""
    errors, warnings = [], []
    fmt = draft["format"]
    max_min = rules["workout_max_min"]
    basis = rules["workout_time_basis"]
    section = {"status": "failed", "format": fmt, "basis_field": None, "minutes": None, "max_minutes": max_min}

    if fmt not in rules["supported_formats"] or fmt not in basis:
        errors.append(issue("unsupported_format",
                            f"지원하지 않는 형식 '{fmt}' (지원: {', '.join(rules['supported_formats'])})",
                            format=fmt))
        return errors, warnings, section

    field = basis[fmt]
    section["basis_field"] = field
    minutes = draft.get(field)
    other = "time_cap_min" if field == "duration_min" else "duration_min"
    if draft.get(other) is not None:
        warnings.append(issue("ignored_field",
                              f"{FORMAT_LABEL[fmt]}은 {field} 기준이므로 {other}({fmt_num(draft[other])})는 무시합니다.",
                              field=other))

    if minutes is None:
        if fmt == "FOR_TIME":
            errors.append(issue("time_cap_missing", "For Time은 TC(time_cap_min)가 필수입니다. TC가 없으면 30분 검증을 할 수 없습니다."))
        else:
            errors.append(issue("duration_missing", f"{FORMAT_LABEL[fmt]}은 진행 시간(duration_min)이 필수입니다."))
    elif minutes > max_min:
        errors.append(issue("workout_too_long",
                            f"본운동 {FIELD_LABEL[field]} {fmt_num(minutes)}분이 상한 {fmt_num(max_min)}분을 넘습니다.",
                            minutes=minutes, max_minutes=max_min))
    else:
        section["status"] = "verified"
    section["minutes"] = minutes

    if fmt == "FOR_TIME" and draft.get("rounds") is None:
        errors.append(issue("rounds_missing", "For Time은 rounds가 필수입니다 (단일 라운드면 1)."))
        section["status"] = "failed"
    return errors, warnings, section


# ---------------------------------------------------------------- 2) 완주 가능성 추정

def _grow(base, fatigue, k):
    """k번째(0부터) 라운드 시간. 피로도 = 라운드마다 느려지는 비율."""
    return base * (1 + fatigue) ** k


def amrap_rounds(round_sec, total_sec, fatigue=0.0):
    """제한 시간 안에 끝나는 라운드 수(소수 = 마지막 라운드 진행률)."""
    elapsed, k = 0.0, 0
    while True:
        r = _grow(round_sec, fatigue, k)
        if elapsed + r > total_sec:
            return k + (total_sec - elapsed) / r
        elapsed += r
        k += 1


def for_time_finish(round_sec, rounds, fatigue=0.0):
    return sum(_grow(round_sec, fatigue, k) for k in range(rounds))


def missing_estimate_inputs(draft, data):
    movements = data["movements"]["movements"]
    est = data["rules"].get("estimation") or {}
    missing = []
    for m in draft["movements"]:
        info = movements.get(m["id"])
        if info is None:
            missing.append({"item": m["id"], "reason": "미등록 동작 (data/movements.json)"})
        elif info.get("time_estimate") is None:
            missing.append({"item": info["display"], "reason": "시간 데이터 없음 (movements.json time_estimate)"})
    if est.get("transition_sec_range") is None:
        missing.append({"item": "동작 간 전환 시간", "reason": "rules.md estimation.transition_sec_range 없음"})
    return missing


def estimate(draft, data, verification):
    """→ (warnings, section)"""
    warnings = []
    fmt = draft["format"]
    section = {"status": None, "reason": None, "missing": [], "breakdown": [], "round_sec": None,
               "transition_sec": None, "fatigue": None, "notes": []}

    if verification["status"] != "verified":
        section.update(status="skipped", reason="본운동 시간 검증을 통과하지 못해 추정하지 않습니다.")
        return warnings, section
    if fmt == "EMOM":
        section.update(status="not_estimable",
                       reason="EMOM의 분당 작업량 추정은 아직 지원하지 않습니다 (Post-MVP). 설정 시간 검증만 수행했습니다.")
        return warnings, section

    missing = missing_estimate_inputs(draft, data)
    if missing:
        section.update(status="not_estimable", missing=missing,
                       reason="추정에 필요한 시간 데이터가 없어 라운드 시간·완주 가능성을 계산하지 않았습니다.")
        return warnings, section

    movements = data["movements"]["movements"]
    est = data["rules"]["estimation"]
    low = high = 0.0
    for m in draft["movements"]:
        info = movements[m["id"]]
        spu = info["time_estimate"]["sec_per_unit"]
        lo, hi = m["reps"] * spu["low"], m["reps"] * spu["high"]
        low, high = low + lo, high + hi
        unit = "m" if info["unit"] == "m" else "회"
        section["breakdown"].append({
            "id": m["id"], "display": info["display"], "reps": m["reps"], "unit": info["unit"],
            "sec_per_unit": spu, "sec": {"low": lo, "high": hi}, "basis": info["time_estimate"]["basis"],
            "text": f"{info['display']} {fmt_num(m['reps'])}{unit} × {fmt_num(spu['low'])}~{fmt_num(spu['high'])}초"
                    f" = {fmt_num(round(lo, 1))}~{fmt_num(round(hi, 1))}초",
        })
    tr = est["transition_sec_range"]
    n = len(draft["movements"])
    t_lo, t_hi = n * tr["low"], n * tr["high"]
    section["transition_sec"] = {"low": t_lo, "high": t_hi,
                                 "text": f"전환 {n}회 × {fmt_num(tr['low'])}~{fmt_num(tr['high'])}초"
                                         f" = {fmt_num(t_lo)}~{fmt_num(t_hi)}초"}
    low, high = low + t_lo, high + t_hi
    section["round_sec"] = {"low": low, "high": high}

    fatigue = est.get("fatigue_slowdown_per_round")
    if fatigue is None:
        f_lo = f_hi = 0.0
        section["notes"].append("피로도 미반영 (rules.md estimation.fatigue_slowdown_per_round 없음) — 후반 라운드는 더 느릴 수 있음")
    else:
        f_lo, f_hi = fatigue["low"], fatigue["high"]
        section["fatigue"] = fatigue
    section["notes"].append("반복 수가 많을 때 세트 분할로 느려지는 효과는 반영하지 않음")

    minutes = verification["minutes"]
    if fmt == "AMRAP":
        total = minutes * 60
        r_lo, r_hi = amrap_rounds(high, total, f_hi), amrap_rounds(low, total, f_lo)
        section["expected_rounds"] = {"low": round(r_lo, 2), "high": round(r_hi, 2),
                                      "completed_low": math.floor(r_lo), "completed_high": math.floor(r_hi)}
    else:  # FOR_TIME
        rounds = draft["rounds"]
        fin_lo, fin_hi = for_time_finish(low, rounds, f_lo), for_time_finish(high, rounds, f_hi)
        tc = minutes * 60
        section["expected_finish_sec"] = {"low": fin_lo, "high": fin_hi}
        if fin_lo > tc:
            section["tc_risk"] = "likely_over"
            warnings.append(issue("tc_likely_over",
                                  f"추정상 빠른 회원도 TC {fmt_num(minutes)}분 안에 끝내기 어렵습니다 "
                                  f"(예상 {fmt_sec(fin_lo)}~{fmt_sec(fin_hi)}). 횟수·라운드 조정 검토."))
        elif fin_hi > tc:
            section["tc_risk"] = "possible_over"
            warnings.append(issue("tc_possible_over",
                                  f"추정상 느린 회원은 TC {fmt_num(minutes)}분을 넘길 수 있습니다 "
                                  f"(예상 {fmt_sec(fin_lo)}~{fmt_sec(fin_hi)})."))
        else:
            section["tc_risk"] = "within"
    section["status"] = "estimated"
    return warnings, section


def simulate(draft, data):
    """→ (errors, warnings, result)"""
    errors, warnings, verification = verify_workout_time(draft, data["rules"])
    est_warnings, estimation = estimate(draft, data, verification)
    return errors, warnings + est_warnings, {"workout_time": verification, "estimate": estimation}


# ---------------------------------------------------------------- 출력

VERIFY_LABEL = {"verified": "검증됨", "failed": "실패"}
ESTIMATE_LABEL = {"estimated": "추정", "not_estimable": "추정 불가", "skipped": "건너뜀"}


def render_text(report, draft):
    v = report["result"]["workout_time"]
    e = report["result"]["estimate"]
    lines = [f"[시뮬레이션] {draft_label(draft)}"]

    lines.append(f"1) 본운동 시간 검증 — {VERIFY_LABEL[v['status']]}")
    if v["minutes"] is not None and v["basis_field"]:
        mark = "≤" if v["minutes"] <= v["max_minutes"] else ">"
        lines.append(f"   {FORMAT_LABEL.get(v['format'], v['format'])} {FIELD_LABEL[v['basis_field']]} "
                     f"{fmt_num(v['minutes'])}분 {mark} 상한 {fmt_num(v['max_minutes'])}분")

    lines.append(f"2) 완주 가능성 추정 — {ESTIMATE_LABEL[e['status']]}")
    if e["status"] == "estimated":
        for b in e["breakdown"]:
            lines.append(f"   {b['text']}  (근거: {b['basis']})")
        lines.append(f"   {e['transition_sec']['text']}")
        rs = e["round_sec"]
        lines.append(f"   라운드당 {fmt_sec(rs['low'])}~{fmt_sec(rs['high'])}")
        if "expected_rounds" in e:
            er = e["expected_rounds"]
            lines.append(f"   예상 라운드 {er['low']:.2f}~{er['high']:.2f} "
                         f"(완료 라운드 {er['completed_low']}~{er['completed_high']})")
        if "expected_finish_sec" in e:
            fin = e["expected_finish_sec"]
            lines.append(f"   예상 완료 {fmt_sec(fin['low'])}~{fmt_sec(fin['high'])}")
        for note in e["notes"]:
            lines.append(f"   ※ {note}")
    else:
        lines.append(f"   {e['reason']}")
        for m in e["missing"]:
            lines.append(f"   - 누락: {m['item']} — {m['reason']}")

    lines += render_issues(report)
    lines.append(render_verdict(report))
    return "\n".join(lines)


def main(argv=None):
    return run_cli(SCRIPT, "WOD 본운동 시간을 검증하고 근거가 있으면 완주 가능성을 추정한다.",
                   simulate, render_text, argv)


if __name__ == "__main__":
    sys.exit(main())
