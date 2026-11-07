"""수업 전체 구성(예: 60분)의 시간 배분 검증. WOD 본운동 시간과 수업 시간은 따로 관리한다.

  python3 scripts/check_class.py --total 60 \\
      --block warmup=10 --block boxing=15 --block wod=25 --block cooldown=10 \\
      [--interval boxing=4x3/1] [--wod drafts/<date>.json] [--require boxing] [--data-dir DIR] [--json]

블록 내부 인터벌(선택): --interval KIND=라운드x운동분[/휴식분][+]
  예) boxing=4x3/1  → 3분 × 4라운드 + 1분 × 3회 휴식 = 15분 (마지막 라운드 뒤 휴식 없음)
      boxing=4x3/1+ → 마지막 라운드 뒤에도 휴식 1분 (= 16분)
  인터벌 합계 ≠ 블록 시간이면 오류. 분은 소수 가능(0.5 = 30초). 지정한 종류의 블록은 1개여야 한다.
  복싱 블록에 --interval이 없으면 경고(boxing_intervals_unspecified) — 기존 입력은 그대로 동작.

블록: KIND=분[:이름]. KIND = warmup, briefing, boxing, strength, accessory, wod, cooldown, transition.
수업안은 응답에만 표시한다. WOD 초안 JSON 스키마는 바꾸지 않는다 (블록은 CLI 인자로만 받음).

오류 (종료 코드 1)
  - 블록 시간 합계 ≠ --total
  - 필수 블록 없음 (기본 warmup, wod, cooldown + --require로 추가)
  - --wod 초안이 본운동 시간 검증 실패 (simulate와 같은 기준: 30분·코치 요청 상한)
  - wod 블록 시간 < 본운동 시간 (AMRAP/EMOM 설정 시간, For Time TC)
  - 인터벌 합계 ≠ 블록 시간 (interval_total_mismatch), 인터벌 대상 블록 없음 (interval_block_missing)
경고: wod 블록 = 본운동 시간 (설명·세팅·전환 여유 없음), --wod 없이 wod 블록 사용, 복싱 인터벌 미지정
종료 코드 2: 인자 형식 오류, 초안·데이터 오류
"""

import argparse
import json
import re
import sys

from common import (
    DEFAULT_DATA_DIR,
    EXIT_INPUT,
    InputError,
    fmt_num,
    input_error_report,
    is_number,
    issue,
    load_data,
    load_draft,
    make_report,
    render_issues,
    render_verdict,
)
from simulate import verify_workout_time

SCRIPT = "check_class"
KINDS = {
    "warmup": "준비운동",
    "briefing": "설명",
    "boxing": "복싱",
    "strength": "스트렝스",
    "accessory": "악세서리",
    "wod": "WOD",
    "cooldown": "마무리",
    "transition": "전환",
}
DEFAULT_REQUIRED = ("warmup", "wod", "cooldown")
INTERVAL_EXPECTED = ("boxing",)   # 이 블록은 내부 인터벌을 명시해야 한다 (없으면 경고)
EPS = 1e-9
INTERVAL_RE = re.compile(r"^(?P<rounds>\d+)x(?P<work>\d+(?:\.\d+)?)(?:/(?P<rest>\d+(?:\.\d+)?))?(?P<last>\+)?$")


def _num(x):
    x = float(x)
    return int(x) if x.is_integer() else x


def parse_interval(text):
    """"boxing=4x3/1" → {"kind", "rounds", "work_min", "rest_min", "rest_after_last"}"""
    if "=" not in text:
        raise InputError(f"--interval '{text}': KIND=라운드x운동분[/휴식분][+] 형식이어야 합니다")
    kind, spec = (t.strip() for t in text.split("=", 1))
    if kind not in KINDS:
        raise InputError(f"--interval '{text}': 알 수 없는 블록 종류 '{kind}'")
    m = INTERVAL_RE.match(spec.replace(" ", ""))
    if not m:
        raise InputError(f"--interval '{text}': 라운드x운동분[/휴식분][+] 형식이어야 합니다 (예: 4x3/1)")
    rounds, work = int(m["rounds"]), _num(m["work"])
    rest = _num(m["rest"]) if m["rest"] is not None else 0
    if rounds < 1 or work <= 0:
        raise InputError(f"--interval '{text}': 라운드는 1 이상, 운동 시간은 0보다 커야 합니다")
    return {"kind": kind, "rounds": rounds, "work_min": work, "rest_min": rest,
            "rest_after_last": bool(m["last"])}


def interval_total(iv):
    """운동 × 라운드 + 휴식 × (라운드 - 1), 마지막 뒤 휴식 지정 시 + 휴식 1회."""
    rests = iv["rounds"] - 1 + (1 if iv["rest_after_last"] else 0)
    return iv["rounds"] * iv["work_min"] + rests * iv["rest_min"], rests


def interval_text(iv):
    total, rests = interval_total(iv)
    parts = [f"{fmt_num(iv['work_min'])}분 × {iv['rounds']}라운드"]
    if rests and iv["rest_min"]:
        parts.append(f"휴식 {fmt_num(iv['rest_min'])}분 × {rests}회")
    tail = " (마지막 라운드 뒤 휴식 포함)" if iv["rest_after_last"] else ""
    return " + ".join(parts) + f" = {fmt_num(total)}분{tail}"


def _interval_timeline(iv, start):
    out, t = [], start
    for r in range(1, iv["rounds"] + 1):
        out.append({"type": "work", "round": r, "start_min": t, "end_min": t + iv["work_min"]})
        t += iv["work_min"]
        if iv["rest_min"] and (r < iv["rounds"] or iv["rest_after_last"]):
            out.append({"type": "rest", "after_round": r, "start_min": t, "end_min": t + iv["rest_min"]})
            t += iv["rest_min"]
    return out


def parse_block(text):
    """"boxing=15:Boxing Drills" → {"kind", "minutes", "label"}"""
    if "=" not in text:
        raise InputError(f"--block '{text}': KIND=분[:이름] 형식이어야 합니다")
    kind, rest = text.split("=", 1)
    kind = kind.strip()
    minutes_text, _, label = rest.partition(":")
    if kind not in KINDS:
        raise InputError(f"--block '{text}': 알 수 없는 블록 종류 '{kind}' (허용: {', '.join(KINDS)})")
    try:
        minutes = float(minutes_text)
    except ValueError:
        raise InputError(f"--block '{text}': 분은 숫자여야 합니다")
    if minutes <= 0:
        raise InputError(f"--block '{text}': 분은 0보다 커야 합니다")
    if minutes.is_integer():
        minutes = int(minutes)
    return {"kind": kind, "minutes": minutes, "label": label.strip() or KINDS[kind]}


def check_class(total, blocks, required=DEFAULT_REQUIRED, draft=None, data=None, intervals=()):
    """→ (errors, warnings, result)"""
    errors, warnings = [], []
    if not is_number(total) or total <= 0:
        raise InputError("--total: 0보다 큰 숫자여야 합니다")
    if not blocks:
        raise InputError("--block을 1개 이상 지정해야 합니다")

    timeline, t = [], 0
    for b in blocks:
        timeline.append({**b, "start_min": t, "end_min": t + b["minutes"]})
        t += b["minutes"]
    block_sum = t
    if abs(block_sum - total) > EPS:
        diff = block_sum - total
        errors.append(issue("class_total_mismatch",
                            f"블록 합계 {fmt_num(block_sum)}분 ≠ 수업 시간 {fmt_num(total)}분 "
                            f"({'초과' if diff > 0 else '부족'} {fmt_num(abs(diff))}분)",
                            block_sum=block_sum, total=total, diff=diff))

    kinds = {b["kind"] for b in blocks}
    by_kind = {}
    for b in timeline:
        by_kind.setdefault(b["kind"], []).append(b)
    seen_iv = set()
    for iv in intervals:
        k = iv["kind"]
        if k in seen_iv:
            raise InputError(f"--interval: '{k}'를 두 번 지정했습니다")
        seen_iv.add(k)
        targets = by_kind.get(k, [])
        if not targets:
            errors.append(issue("interval_block_missing",
                                f"인터벌을 지정한 '{k}'({KINDS[k]}) 블록이 수업안에 없습니다.", kind=k))
            continue
        if len(targets) > 1:
            raise InputError(f"--interval: '{k}' 블록이 {len(targets)}개라 어느 블록인지 알 수 없습니다")
        b = targets[0]
        iv_total, rests = interval_total(iv)
        b["intervals"] = {**iv, "rests": rests, "total_min": iv_total, "text": interval_text(iv),
                          "timeline": _interval_timeline(iv, b["start_min"])}
        if abs(iv_total - b["minutes"]) > EPS:
            diff = iv_total - b["minutes"]
            errors.append(issue("interval_total_mismatch",
                                f"{b['label']} 내부 시간 {interval_text(iv)} ≠ 블록 {fmt_num(b['minutes'])}분 "
                                f"({'초과' if diff > 0 else '부족'} {fmt_num(abs(diff))}분)",
                                kind=k, interval_total_min=iv_total, block_min=b["minutes"], diff=diff))
    for k in INTERVAL_EXPECTED:
        if k in by_kind and k not in seen_iv:
            warnings.append(issue(f"{k}_intervals_unspecified",
                                  f"{KINDS[k]} 블록의 라운드·운동·휴식 시간이 지정되지 않아 내부 시간을 검증하지 않았습니다 "
                                  f"(--interval {k}=라운드x운동분/휴식분).", kind=k))

    for k in required:
        if k not in kinds:
            errors.append(issue("class_block_missing", f"필수 블록 '{k}'({KINDS[k]})이 없습니다", kind=k))

    wod_block = sum(b["minutes"] for b in blocks if b["kind"] == "wod")
    workout = None
    if draft is not None:
        v_errors, v_warnings, workout = verify_workout_time(draft, data["rules"])
        for e in v_errors:
            errors.append(dict(e, source="simulate"))
        warnings += [dict(w, source="simulate") for w in v_warnings]
        minutes = workout.get("minutes")
        if wod_block and minutes is not None:
            if wod_block + EPS < minutes:
                errors.append(issue("wod_block_too_short",
                                    f"WOD 블록 {fmt_num(wod_block)}분 < 본운동 {fmt_num(minutes)}분",
                                    wod_block_min=wod_block, workout_min=minutes))
            elif abs(wod_block - minutes) <= EPS:
                warnings.append(issue("wod_block_no_buffer",
                                      f"WOD 블록 {fmt_num(wod_block)}분 = 본운동 {fmt_num(minutes)}분 — "
                                      f"설명·세팅·전환 시간이 블록 안에 없습니다. 다른 블록에 포함했는지 확인.",
                                      wod_block_min=wod_block, workout_min=minutes))
    elif wod_block:
        warnings.append(issue("wod_not_checked",
                              "--wod 초안이 없어 WOD 블록과 본운동 시간을 비교하지 않았습니다."))

    result = {"total_min": total, "block_sum_min": block_sum, "wod_block_min": wod_block,
              "workout": workout, "blocks": timeline}
    return errors, warnings, result


def _clock(minutes):
    """분 → "h:mm" (소수 분은 "h:mm:ss")."""
    sec = int(round(minutes * 60))
    h, m, s = sec // 3600, sec % 3600 // 60, sec % 60
    return f"{h}:{m:02d}" if s == 0 else f"{h}:{m:02d}:{s:02d}"


def render_text(report):
    r = report["result"]
    lines = [f"[수업 구성 검증] 수업 {fmt_num(r['total_min'])}분 / 블록 합계 {fmt_num(r['block_sum_min'])}분"]
    for b in r["blocks"]:
        lines.append(f"  {_clock(b['start_min'])}–{_clock(b['end_min'])}  {b['label']} ({fmt_num(b['minutes'])}분)")
        iv = b.get("intervals")
        if iv:
            lines.append(f"      내부: {iv['text']}")
    w = r.get("workout")
    if w and w.get("minutes") is not None:
        lines.append(f"  WOD 블록 {fmt_num(r['wod_block_min'])}분 중 본운동 {fmt_num(w['minutes'])}분 "
                     f"(상한 {fmt_num(w['max_minutes'])}분)")
    lines += render_issues(report, "이대로는 수업안을 쓸 수 없음")
    lines.append(render_verdict(report))
    return "\n".join(lines)


def add_class_arguments(parser, total_required=True):
    """수업 구성 인자 (render_wod.py도 같은 인자를 쓴다)."""
    parser.add_argument("--total", type=float, required=total_required, help="수업 시간(분), 예: 60")
    parser.add_argument("--block", action="append", default=[], help="KIND=분[:이름] (순서대로, 여러 번)")
    parser.add_argument("--require", action="append", default=[], help="추가 필수 블록 종류 (예: boxing)")
    parser.add_argument("--interval", action="append", default=[],
                        help="블록 내부 인터벌 KIND=라운드x운동분[/휴식분][+] (예: boxing=4x3/1)")


def class_report_from_args(args, draft=None, data=None):
    """파싱된 인자로 check_class를 실행해 공통 형식 보고서를 돌려준다. 인자 오류는 InputError."""
    total = int(args.total) if float(args.total).is_integer() else args.total
    blocks = [parse_block(b) for b in args.block]
    intervals = [parse_interval(i) for i in args.interval]
    for k in args.require:
        if k not in KINDS:
            raise InputError(f"--require: 알 수 없는 블록 종류 '{k}'")
    required = tuple(dict.fromkeys(list(DEFAULT_REQUIRED) + args.require))
    return make_report(SCRIPT, *check_class(total, blocks, required, draft, data, intervals))


def main(argv=None):
    parser = argparse.ArgumentParser(prog="check_class.py", description="수업 전체 시간 배분을 검증한다.")
    add_class_arguments(parser)
    parser.add_argument("--wod", default=None, help="WOD 초안 JSON (본운동 시간과 WOD 블록 비교)")
    parser.add_argument("--data-dir", default=None, help=f"데이터 디렉터리 (기본: {DEFAULT_DATA_DIR})")
    parser.add_argument("--json", action="store_true", help="JSON으로 출력")
    args = parser.parse_args(argv)

    try:
        draft = data = None
        if args.wod:
            data = load_data(args.data_dir)
            draft = load_draft(args.wod)
        report = class_report_from_args(args, draft, data)
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


if __name__ == "__main__":
    sys.exit(main())
