"""승인·저장된 최근 WOD 기록 조회.

  python3 scripts/recent_wods.py --date YYYY-MM-DD [--days N] [--draft PATH]
                                 [--wods-dir DIR] [--data-dir DIR] [--json]

  --date   기준 날짜 (만들 WOD의 날짜). 기준일 이전 N일(기본 rules.md recent_days = 7)의 기록만 본다.
           기간: [기준일 − N일, 기준일). 기준일 당일 기록은 same_day로 따로 알리고, 이후 날짜는 미래 기록으로 제외한다.
  --draft  계획 중인 초안. 최근 기록과 동작·패턴이 겹치면 참고 경고를 낸다 (금지가 아님).

읽는 파일: wods/YYYY-MM-DD.json (save_wod.py가 쓴 승인 기록)만. wods/archive/ 등 하위 폴더는 보지 않는다.
손상된 JSON, 필수 필드 누락, 파일명과 내용 날짜 불일치, 형식을 알 수 없는 파일(.txt 등)은 조용히 넘기지 않고 경고한다.

반복 경고 기준 (규칙이 아닌 참고용 휴리스틱, 금지 아님)
  - 같은 Rx 동작이 기간 안 기록 2개 이상에 나옴 → movement_repeated
  - 같은 패턴이 기간 안 기록 3개 이상에 나옴 → pattern_repeated
  - --draft의 동작이 기간 안 기록에 있음 → draft_movement_recent
  - --draft의 패턴이 가장 최근 기록에도 있음 → draft_pattern_recent

종료 코드: 0 = 조회됨(기록 없음·경고 포함), 2 = 입력 오류.
"""

import argparse
import json
import sys
from collections import Counter
from datetime import date as Date, timedelta
from pathlib import Path

from common import (
    DATE_RE,
    DEFAULT_DATA_DIR,
    DEFAULT_WODS_DIR,
    EXIT_INPUT,
    ROOT,
    InputError,
    fmt_num,
    input_error_report,
    issue,
    load_data,
    load_draft,
    make_report,
)

SCRIPT = "recent_wods"
MOVEMENT_REPEAT_MIN = 2
PATTERN_REPEAT_MIN = 3


def _parse_date(s, label):
    if not isinstance(s, str) or not DATE_RE.match(s):
        raise ValueError(f"{label}: YYYY-MM-DD 형식이 아닙니다 ({s!r})")
    return Date.fromisoformat(s)


def _rel(path):
    p = Path(path).resolve()
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        return str(p)


def summarize_record(rec, data):
    """기록 → 요약. 필수 정보가 없으면 ValueError(이유)."""
    if not isinstance(rec, dict):
        raise ValueError("최상위가 객체가 아닙니다")
    wod = rec.get("wod")
    if not isinstance(wod, dict):
        raise ValueError("wod(저장된 초안)가 없습니다")
    movs = wod.get("movements")
    if not isinstance(movs, list) or not movs or not all(isinstance(m, dict) and m.get("id") for m in movs):
        raise ValueError("wod.movements가 비었거나 형식이 잘못됐습니다")
    fmt = wod.get("format")
    if not fmt:
        raise ValueError("wod.format이 없습니다")
    info = data["movements"]["movements"]
    items, unknown = [], []
    for m in movs:
        mi = info.get(m["id"])
        if mi is None:
            unknown.append(m["id"])
        items.append({"id": m["id"], "display": (mi or {}).get("display", m["id"]),
                      "patterns": (mi or {}).get("patterns") or []})
    minutes = wod.get("time_cap_min") if fmt == "FOR_TIME" else wod.get("duration_min")
    return {"format": fmt, "workout_min": minutes, "movements": items,
            "patterns": sorted({p for it in items for p in it["patterns"]}),
            "approved_at": rec.get("approved_at"), "unknown_movements": unknown}


def recent(wods_dir, ref, days, data, draft=None):
    errors, warnings = [], []
    start = ref - timedelta(days=days)
    result = {"reference_date": ref.isoformat(), "days": days,
              "window": {"from": start.isoformat(), "to_exclusive": ref.isoformat()},
              "wods_dir": _rel(wods_dir), "records": [], "same_day": None, "excluded_future": [],
              "older_count": 0, "movement_counts": {}, "pattern_counts": {}, "no_records": True, "draft_overlap": None}
    wods_dir = Path(wods_dir)
    if not wods_dir.exists():
        return errors, warnings, result

    for f in sorted(wods_dir.iterdir()):
        if f.is_dir() or f.name.startswith("."):
            continue
        if f.suffix != ".json" or not DATE_RE.match(f.stem):
            warnings.append(issue("unrecognized_file",
                                  f"{_rel(f)}: 승인 기록 형식(YYYY-MM-DD.json)이 아니라 읽지 않았습니다.", path=_rel(f)))
            continue
        try:
            fdate = _parse_date(f.stem, "파일명")
        except ValueError as e:
            warnings.append(issue("unrecognized_file", f"{_rel(f)}: {e}", path=_rel(f)))
            continue
        if fdate > ref:
            result["excluded_future"].append(fdate.isoformat())
            continue
        if fdate < start:
            result["older_count"] += 1
            continue
        try:
            rec = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            warnings.append(issue("record_unreadable", f"{_rel(f)}: 기록을 읽을 수 없습니다 ({e}). 최근 기록에서 빠졌습니다.",
                                  path=_rel(f)))
            continue
        try:
            s = summarize_record(rec, data)
        except ValueError as e:
            warnings.append(issue("record_incomplete", f"{_rel(f)}: 기록이 불완전합니다 — {e}. 최근 기록에서 빠졌습니다.",
                                  path=_rel(f)))
            continue
        if rec.get("date") != f.stem:
            warnings.append(issue("record_date_mismatch",
                                  f"{_rel(f)}: 파일명 날짜와 기록 date({rec.get('date')!r})가 다릅니다. 파일명 날짜로 취급합니다.",
                                  path=_rel(f)))
        if s["unknown_movements"]:
            warnings.append(issue("record_unknown_movement",
                                  f"{_rel(f)}: 지금 movements.json에 없는 동작 {s['unknown_movements']} — 패턴을 알 수 없습니다.",
                                  path=_rel(f)))
        entry = dict(s, date=fdate.isoformat(), path=_rel(f))
        if fdate == ref:
            result["same_day"] = entry
        else:
            result["records"].append(entry)

    recs = sorted(result["records"], key=lambda r: r["date"], reverse=True)
    result["records"] = recs
    result["no_records"] = not recs
    mc = Counter(m["id"] for r in recs for m in {x["id"]: x for x in r["movements"]}.values())
    pc = Counter(p for r in recs for p in r["patterns"])
    result["movement_counts"] = dict(mc)
    result["pattern_counts"] = dict(pc)
    names = {m["id"]: m["display"] for r in recs for m in r["movements"]}
    for mid, n in sorted(mc.items()):
        if n >= MOVEMENT_REPEAT_MIN:
            dates = [r["date"] for r in recs if any(m["id"] == mid for m in r["movements"])]
            warnings.append(issue("movement_repeated",
                                  f"{names[mid]}가 최근 {days}일 기록 {n}개에 나왔습니다 ({', '.join(dates)}). 참고용이며 금지는 아닙니다.",
                                  movement=mid, count=n, dates=dates))
    for pat, n in sorted(pc.items()):
        if n >= PATTERN_REPEAT_MIN:
            warnings.append(issue("pattern_repeated",
                                  f"{pat} 패턴이 최근 {days}일 기록 {n}개에 나왔습니다. 참고용이며 금지는 아닙니다.",
                                  pattern=pat, count=n))
    if result["same_day"]:
        warnings.append(issue("same_day_record_exists",
                              f"{ref.isoformat()} 날짜로 이미 저장된 기록이 있습니다 ({result['same_day']['path']}). "
                              "새로 저장하려면 기존 기록 교체 확인이 따로 필요합니다."))
    if result["excluded_future"]:
        warnings.append(issue("future_records_excluded",
                              f"기준일 이후 기록 {len(result['excluded_future'])}개({', '.join(result['excluded_future'])})는 최근 기록에서 제외했습니다."))

    if draft is not None:
        info = data["movements"]["movements"]
        d_ids = list(dict.fromkeys(m["id"] for m in draft["movements"]))
        d_pats = sorted({p for i in d_ids for p in (info.get(i) or {}).get("patterns") or []})
        overlap_m = {i: [r["date"] for r in recs if any(m["id"] == i for m in r["movements"])] for i in d_ids}
        overlap_m = {i: ds for i, ds in overlap_m.items() if ds}
        latest = recs[0] if recs else None
        overlap_p = sorted(set(d_pats) & set(latest["patterns"])) if latest else []
        result["draft_overlap"] = {"movements": overlap_m, "patterns_with_latest": overlap_p,
                                   "latest_date": latest["date"] if latest else None}
        for i, ds in overlap_m.items():
            warnings.append(issue("draft_movement_recent",
                                  f"초안의 {(info.get(i) or {}).get('display', i)}가 최근 기록({', '.join(ds)})에도 있습니다. "
                                  "의도한 반복인지 코치에게 알리세요 (금지 아님).", movement=i, dates=ds))
        if overlap_p:
            warnings.append(issue("draft_pattern_recent",
                                  f"초안 패턴 {', '.join(overlap_p)}가 가장 최근 기록({latest['date']})과 겹칩니다 (참고).",
                                  patterns=overlap_p))
    return errors, warnings, result


def render_text(report):
    r = report["result"]
    out = [f"[최근 기록] 기준일 {r['reference_date']} — {r['window']['from']} ~ 기준일 전날 ({r['days']}일)"]
    if r["no_records"]:
        out.append("최근 기록 없음 (wods/에 기간 안 승인 기록이 없습니다)")
    for rec in r["records"]:
        mins = f" {fmt_num(rec['workout_min'])}" if rec["workout_min"] is not None else ""
        out.append(f"{rec['date']}  {rec['format']}{mins}  — {', '.join(m['display'] for m in rec['movements'])}"
                   f"  [패턴: {', '.join(rec['patterns']) or '없음'}]")
    if r["pattern_counts"]:
        out.append("패턴 횟수: " + ", ".join(f"{k} {v}" for k, v in sorted(r["pattern_counts"].items())))
    for w in report["warnings"]:
        out.append(f"! {w['message']}")
    out.append(f"결과: 종료 코드 {report['exit_code']}")
    return "\n".join(out)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="recent_wods.py", description="승인·저장된 최근 WOD 기록을 요약한다.")
    parser.add_argument("--date", default=None, help="기준 날짜 YYYY-MM-DD (기본: 오늘 시스템 날짜)")
    parser.add_argument("--days", type=int, default=None, help="조회 기간 일수 (기본: rules.md recent_days)")
    parser.add_argument("--draft", default=None, help="계획 중인 초안 JSON (겹침 참고 경고)")
    parser.add_argument("--wods-dir", default=None, help=f"기록 디렉터리 (기본: {DEFAULT_WODS_DIR})")
    parser.add_argument("--data-dir", default=None, help=f"데이터 디렉터리 (기본: {DEFAULT_DATA_DIR})")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        data = load_data(args.data_dir)
        try:
            ref = _parse_date(args.date, "--date") if args.date else Date.today()
        except ValueError as e:
            raise InputError(str(e))
        days = args.days if args.days is not None else data["rules"].get("recent_days")
        if not isinstance(days, int) or days <= 0:
            raise InputError("--days 또는 rules.md recent_days가 1 이상의 정수여야 합니다.")
        draft = load_draft(args.draft) if args.draft else None
        wods_dir = Path(args.wods_dir) if args.wods_dir else DEFAULT_WODS_DIR
        report = make_report(SCRIPT, *recent(wods_dir, ref, days, data, draft))
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
