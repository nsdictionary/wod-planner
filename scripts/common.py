"""공통 유틸: data/ 로딩·무결성 검사, WOD 초안 JSON 검증, CLI 출력 형식.

종료 코드 (모든 스크립트 공통)
  0  통과 (경고가 있을 수 있음)
  1  검증 실패 — 입력은 읽었지만 규칙 위반 (WOD를 그대로 쓸 수 없음)
  2  입력 오류 — 파일 없음, JSON 파싱 실패, 스키마 위반, data/ 파일 오류

JSON 출력 형식 (--json, 모든 스크립트 공통)
  {"script": str, "ok": bool, "exit_code": int,
   "errors": [issue], "warnings": [issue], "result": object | null}
  issue = {"code": str, "message": str, ...추가 필드}
"""

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = ROOT / "data"
DEFAULT_DRAFTS_DIR = ROOT / "drafts"
DEFAULT_WODS_DIR = ROOT / "wods"
CODE_LEN = 12        # 화면에 보여 주는 해시 접두사 길이 (초안 코드·경고 코드·기록 코드 — 무결성 확인용)

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_INPUT = 2

PRECISIONS = ("exact", "approx", "unknown")
PRECISION_LABEL = {"exact": "정확", "approx": "추정", "unknown": "미확인"}
GROUPS = ("adult", "kids")
UNITS = ("rep", "m")
SCALE_LEVELS = ("A", "B", "C")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
RULES_BLOCK_RE = re.compile(r"```json[ \t]*\n(.*?)```", re.S)


class InputError(Exception):
    """입력이나 데이터를 읽을 수 없음 (종료 코드 2)."""

    def __init__(self, messages):
        if isinstance(messages, str):
            messages = [messages]
        self.messages = list(messages)
        super().__init__("\n".join(self.messages))


def issue(code, message, **extra):
    return {"code": code, "message": message, **extra}


def is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def is_positive_int(value):
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def weight_key(weight):
    """15 → "15", 1.5 → "1.5" (equipment.json의 by_weight_* 키 형식)."""
    return f"{weight:g}"


def fmt_sec(sec):
    """초 → "m:ss"."""
    total = int(round(sec))
    return f"{total // 60}:{total % 60:02d}"


def fmt_num(value):
    return f"{value:g}"


# ---------------------------------------------------------------- 파일 로딩

def load_json(path):
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise InputError(f"파일을 찾을 수 없습니다: {path}")
    except OSError as e:
        raise InputError(f"파일을 읽을 수 없습니다: {path} ({e})")
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise InputError(f"JSON 형식 오류: {path} {e.lineno}행 {e.colno}열 — {e.msg}")


def load_rules(path):
    """rules.md의 첫 번째 ```json 코드 블록을 읽는다."""
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise InputError(f"파일을 찾을 수 없습니다: {path}")
    match = RULES_BLOCK_RE.search(text)
    if not match:
        raise InputError(f"{path}에 ```json 기계 판독 설정 블록이 없습니다.")
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError as e:
        raise InputError(f"{path}의 json 블록 형식 오류: {e.lineno}행 {e.colno}열 — {e.msg}")


def load_data(data_dir=None):
    """data/의 equipment.json, movements.json, rules.md를 읽고 무결성을 검사한다."""
    base = Path(data_dir) if data_dir else DEFAULT_DATA_DIR
    if not base.is_dir():
        raise InputError(f"데이터 디렉터리가 없습니다: {base}")
    data = {
        "dir": str(base),
        "equipment": load_json(base / "equipment.json"),
        "movements": load_json(base / "movements.json"),
        "rules": load_rules(base / "rules.md"),
    }
    errors = validate_data(data)
    if errors:
        raise InputError([f"데이터 파일 오류 ({base}):"] + [f"  - {e}" for e in errors])
    return data


# ---------------------------------------------------------------- 데이터 무결성

def _check_quantity(path, q, errors):
    if q is None:
        return
    if not isinstance(q, dict) or set(q) != {"value", "precision"}:
        errors.append(f"{path}: 수량은 {{\"value\", \"precision\"}} 형식이어야 합니다")
        return
    if q["precision"] not in PRECISIONS:
        errors.append(f"{path}.precision: {PRECISIONS} 중 하나여야 합니다")
    elif q["precision"] == "unknown":
        if q["value"] is not None:
            errors.append(f"{path}: precision이 unknown이면 value는 null이어야 합니다")
    elif not is_number(q["value"]) or q["value"] < 0:
        errors.append(f"{path}.value: 0 이상의 숫자여야 합니다")


def _check_range(path, r, errors):
    """{"low": n, "high": n}, 0 <= low <= high."""
    if not isinstance(r, dict) or not is_number(r.get("low")) or not is_number(r.get("high")):
        errors.append(f"{path}: {{\"low\": 숫자, \"high\": 숫자}} 형식이어야 합니다")
    elif not 0 <= r["low"] <= r["high"]:
        errors.append(f"{path}: 0 <= low <= high 여야 합니다")


def validate_data(data):
    errors = []
    eq_doc, mv_doc, rules = data["equipment"], data["movements"], data["rules"]

    equipment = eq_doc.get("equipment") if isinstance(eq_doc, dict) else None
    space = eq_doc.get("space") if isinstance(eq_doc, dict) else None
    if not isinstance(equipment, dict):
        errors.append("equipment.json: 'equipment' 객체가 없습니다")
        equipment = {}
    if not isinstance(space, dict):
        errors.append("equipment.json: 'space' 객체가 없습니다")
        space = {}
    if not isinstance(eq_doc.get("banned_movements", []), list):
        errors.append("equipment.json: 'banned_movements'는 배열이어야 합니다")

    for name, e in equipment.items():
        p = f"equipment.json equipment.{name}"
        if not isinstance(e, dict):
            errors.append(f"{p}: 객체여야 합니다")
            continue
        if e.get("available") not in (True, False, None):
            errors.append(f"{p}.available: true/false/null 이어야 합니다")
        for f in ("count", "capacity_athletes"):
            _check_quantity(f"{p}.{f}", e.get(f), errors)
        for f in ("by_weight_kg", "by_weight_lb"):
            weights = e.get(f)
            if weights is None:
                continue
            if not isinstance(weights, dict):
                errors.append(f"{p}.{f}: 객체 또는 null 이어야 합니다")
                continue
            for w, q in weights.items():
                try:
                    float(w)
                except ValueError:
                    errors.append(f"{p}.{f}: 무게 키 '{w}'가 숫자가 아닙니다")
                _check_quantity(f"{p}.{f}.{w}", q, errors)

    for name, s in space.items():
        if isinstance(s, dict):
            for f in ("capacity_athletes", "height_m"):
                if isinstance(s.get(f), dict):
                    _check_quantity(f"equipment.json space.{name}.{f}", s[f], errors)

    movements = mv_doc.get("movements") if isinstance(mv_doc, dict) else None
    if not isinstance(movements, dict):
        errors.append("movements.json: 'movements' 객체가 없습니다")
        movements = {}

    space_tag_targets = {"wall_target"} | set((space.get("ceiling") or {}).get("restricted_space_tags") or [])
    patterns = set(rules.get("patterns") or [])
    for mid, m in movements.items():
        p = f"movements.json movements.{mid}"
        if not isinstance(m, dict):
            errors.append(f"{p}: 객체여야 합니다")
            continue
        if not isinstance(m.get("display"), str):
            errors.append(f"{p}.display: 문자열이어야 합니다")
        if m.get("unit") not in UNITS:
            errors.append(f"{p}.unit: {UNITS} 중 하나여야 합니다")
        for e in m.get("equipment", []):
            if e not in equipment:
                errors.append(f"{p}.equipment: '{e}'가 equipment.json에 없습니다")
        for t in m.get("space_tags", []):
            if t not in space_tag_targets:
                errors.append(f"{p}.space_tags: 알 수 없는 공간 태그 '{t}'")
        for s in m.get("substitutes", []):
            if s.get("id") not in movements:
                errors.append(f"{p}.substitutes: '{s.get('id')}'가 movements.json에 없습니다")
        for pt in m.get("patterns", []):
            if pt not in patterns:
                errors.append(f"{p}.patterns: '{pt}'가 rules.md patterns에 없습니다")
        te = m.get("time_estimate")
        if te is not None:
            if not isinstance(te, dict):
                errors.append(f"{p}.time_estimate: 객체 또는 null 이어야 합니다")
            else:
                _check_range(f"{p}.time_estimate.sec_per_unit", te.get("sec_per_unit"), errors)
                if not te.get("basis"):
                    errors.append(f"{p}.time_estimate.basis: 근거가 없는 시간 추정치는 쓸 수 없습니다")

    for b in eq_doc.get("banned_movements", []) or []:
        if b.get("movement") not in movements:
            errors.append(f"equipment.json banned_movements: '{b.get('movement')}'가 movements.json에 없습니다")

    for key in ("workout_max_min", "workout_time_basis", "supported_formats", "estimation"):
        if key not in rules:
            errors.append(f"rules.md json 블록: '{key}'가 없습니다")
    if "workout_max_min" in rules and (not is_number(rules["workout_max_min"]) or rules["workout_max_min"] <= 0):
        errors.append("rules.md json 블록: workout_max_min은 양수여야 합니다")
    est = rules.get("estimation") or {}
    for key in ("transition_sec_range", "fatigue_slowdown_per_round"):
        if est.get(key) is not None:
            _check_range(f"rules.md estimation.{key}", est[key], errors)
    return errors


# ---------------------------------------------------------------- WOD 초안 검증

def _validate_movement_list(prefix, movements, errors):
    for i, m in enumerate(movements):
        p = f"{prefix}[{i}]"
        if not isinstance(m, dict):
            errors.append(f"{p}: 객체여야 합니다")
            continue
        if not isinstance(m.get("id"), str) or not m.get("id"):
            errors.append(f"{p}.id: 필수 문자열입니다")
        reps = m.get("reps")
        if not is_number(reps) or reps <= 0:
            errors.append(f"{p}.reps: 양수여야 합니다 (unit이 m인 동작은 미터)")
        for f in ("units_per_athlete", "concurrent_athletes"):
            if f in m and not is_positive_int(m[f]):
                errors.append(f"{p}.{f}: 1 이상의 정수여야 합니다")
        if "load" in m and not isinstance(m["load"], str):
            errors.append(f"{p}.load: 문자열이어야 합니다")
        if "weights" in m:
            w = m["weights"]
            if not isinstance(w, dict):
                errors.append(f"{p}.weights: {{장비 id: [무게, ...]}} 형식이어야 합니다")
            else:
                for eq_id, lst in w.items():
                    if not isinstance(lst, list) or not lst or not all(is_number(x) and x > 0 for x in lst):
                        errors.append(f"{p}.weights.{eq_id}: 양수 무게 배열이어야 합니다")


def validate_draft(draft):
    """초안 JSON의 구조를 검사한다. 문제가 있으면 모두 모아 InputError로 알린다.

    형식별 규칙(TC 필수, 30분 상한, 지원 형식)은 구조가 아니라 규칙이므로 simulate.py가 검사한다.
    """
    errors = []
    if not isinstance(draft, dict):
        raise InputError("초안 JSON의 최상위는 객체여야 합니다.")

    date = draft.get("date")
    if date is not None and (not isinstance(date, str) or not DATE_RE.match(date)):
        errors.append("date: 'YYYY-MM-DD' 형식 문자열이어야 합니다")
    if not isinstance(draft.get("format"), str) or not draft.get("format"):
        errors.append("format: 필수 문자열입니다 (예: AMRAP, EMOM, FOR_TIME)")
    for f in ("duration_min", "time_cap_min"):
        v = draft.get(f)
        if v is not None and (not is_number(v) or v <= 0):
            errors.append(f"{f}: 양수 또는 null 이어야 합니다")
    for f in ("rounds", "expected_athletes"):
        v = draft.get(f)
        if v is not None and not is_positive_int(v):
            errors.append(f"{f}: 1 이상의 정수 또는 null 이어야 합니다")
    group = draft.get("group", "adult")
    if group not in GROUPS:
        errors.append(f"group: {GROUPS} 중 하나여야 합니다")

    mt = draft.get("max_workout_min")
    if mt is not None and (not is_number(mt) or mt <= 0):
        errors.append("max_workout_min: 양수 또는 null 이어야 합니다 (코치가 요청한 본운동 상한, 분)")

    movements = draft.get("movements")
    if not isinstance(movements, list) or not movements:
        errors.append("movements: 동작이 1개 이상 있는 배열이어야 합니다")
        movements = []
    _validate_movement_list("movements", movements, errors)

    scales = draft.get("scales")
    if scales is not None:
        if not isinstance(scales, dict) or not scales:
            errors.append(f"scales: {{\"A\": [동작...], ...}} 형식의 객체여야 합니다 (레벨: {', '.join(SCALE_LEVELS)})")
        else:
            for level, lst in scales.items():
                if level not in SCALE_LEVELS:
                    errors.append(f"scales.{level}: 알 수 없는 스케일 레벨 (허용: {', '.join(SCALE_LEVELS)})")
                    continue
                if not isinstance(lst, list) or not lst:
                    errors.append(f"scales.{level}: 동작이 1개 이상 있는 배열이어야 합니다")
                    continue
                _validate_movement_list(f"scales.{level}", lst, errors)
    if errors:
        raise InputError(["초안 JSON 오류:"] + [f"  - {e}" for e in errors])
    return draft


def load_draft(path):
    return validate_draft(load_json(path))


def draft_label(draft):
    parts = [draft.get("date") or "날짜 없음", draft.get("format", "?")]
    minutes = draft.get("duration_min") or draft.get("time_cap_min")
    if minutes:
        parts.append(fmt_num(minutes))
    return " ".join(parts)


# ---------------------------------------------------------------- CLI

# ---------------------------------------------------------------- 해시·시각·원자적 쓰기

def canonical_json(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_json(obj):
    """JSON 값의 내용 해시 (키 순서·공백과 무관)."""
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def now_iso():
    """실제 시스템 시각 (로컬 시간대 포함, 초 단위)."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def dump_json(obj):
    return json.dumps(obj, ensure_ascii=False, indent=2) + "\n"


def atomic_write_text(path, text, overwrite=False):
    """같은 디렉터리의 임시 파일에 쓰고 fsync 후 한 번에 반영한다.

    overwrite=False면 대상이 이미 있을 때 FileExistsError (os.link는 기존 파일을 덮지 않는다).
    중간에 실패해도 대상 파일은 이전 상태 그대로 남는다.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        if overwrite:
            os.replace(tmp, path)
        else:
            os.link(tmp, path)          # 대상이 있으면 FileExistsError — 경쟁 상황에서도 덮어쓰지 않음
            os.unlink(tmp)
        tmp = None
        try:
            dfd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(dfd)
            finally:
                os.close(dfd)
        except OSError:
            pass
    finally:
        if tmp is not None and os.path.exists(tmp):
            os.unlink(tmp)
    return path


def make_report(script, errors, warnings, result):
    exit_code = EXIT_FAIL if errors else EXIT_OK
    return {"script": script, "ok": not errors, "exit_code": exit_code,
            "errors": errors, "warnings": warnings, "result": result}


def input_error_report(script, err):
    return {"script": script, "ok": False, "exit_code": EXIT_INPUT,
            "errors": [issue("input_error", m) for m in err.messages],
            "warnings": [], "result": None}


def run_cli(script, description, handler, render_text, argv=None):
    """공통 CLI: <draft.json> [--data-dir DIR] [--json]. 종료 코드를 반환한다."""
    parser = argparse.ArgumentParser(prog=f"{script}.py", description=description)
    parser.add_argument("draft", help="WOD 초안 JSON 파일 경로")
    parser.add_argument("--data-dir", default=None, help=f"데이터 디렉터리 (기본: {DEFAULT_DATA_DIR})")
    parser.add_argument("--json", action="store_true", help="JSON으로 출력")
    args = parser.parse_args(argv)

    try:
        data = load_data(args.data_dir)
        draft = load_draft(args.draft)
        errors, warnings, result = handler(draft, data)
        report = make_report(script, errors, warnings, result)
    except InputError as e:
        report = input_error_report(script, e)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif report["exit_code"] == EXIT_INPUT:
        print("입력 오류 — 처리하지 않았습니다.", file=sys.stderr)
        for e in report["errors"]:
            print(e["message"], file=sys.stderr)
    else:
        print(render_text(report, draft))
    return report["exit_code"]


def render_issues(report, blocking="이대로는 WOD에 쓸 수 없음"):
    lines = []
    if report["errors"]:
        lines.append(f"오류 {len(report['errors'])}건 ({blocking})")
        lines += [f"  ✗ {e['message']}" for e in report["errors"]]
    if report["warnings"]:
        lines.append(f"경고 {len(report['warnings'])}건")
        lines += [f"  ! {w['message']}" for w in report["warnings"]]
    return lines


def render_verdict(report):
    if report["ok"]:
        extra = f" (경고 {len(report['warnings'])}건)" if report["warnings"] else ""
        return f"결과: 통과{extra} — 종료 코드 0"
    return f"결과: 실패 (오류 {len(report['errors'])}건) — 종료 코드 1"
