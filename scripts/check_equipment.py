"""WOD 초안의 장비·공간 제약 검증.

  python3 scripts/check_equipment.py <draft.json> [--data-dir DIR] [--json]

오류 (종료 코드 1): 미등록 동작, 미보유 장비, 금지 동작, 층고 제한, 보유하지 않은 무게
경고 (종료 코드 0): 보유 여부 미확인, 추정·미확인 수량, 수량 부족(가능성), 월볼 타깃 높이

초안에 scales(A/B/C)가 있으면 스케일 동작도 같은 기준으로 사용 가능 여부를 검사한다(수량 비교는 안 함).
모든 issue에는 위치 index(동작 배열 순번)와 스케일이면 scale 필드가 붙는다 (autofix.py가 사용).

수량 부족은 실행 불가로 판정하지 않는다. 파트너·교대 운영이 가능할 수 있으므로
필요 수량과 보유 수량을 보여 주고 운영 선택지를 제안만 한다.
"""

import sys

from common import (
    PRECISION_LABEL,
    draft_label,
    fmt_num,
    issue,
    render_issues,
    render_verdict,
    run_cli,
    weight_key,
)

SCRIPT = "check_equipment"
SHORTAGE_OPTIONS = ["파트너(2인 1조) 교대", "시차 출발(웨이브)",
                    "스테이션별 시작 동작 분산(단독으로는 동시 사용 감소를 보장하지 않음)"]
PRECISION_RANK = {"exact": 0, "approx": 1, "unknown": 2}
WEIGHT_UNIT = {"by_weight_kg": "kg", "by_weight_lb": "lb"}


def _have_text(have):
    if have["precision"] == "unknown":
        return "보유(수량 미확인)"
    prefix = "약 " if have["precision"] == "approx" else ""
    return f"{prefix}{fmt_num(have['value'])}"


def _resolve_have(e, eq_id, m, display, errors, warnings):
    """장비의 비교 가능한 보유량을 구한다. → (have, kind, detail) 또는 (None, None, detail)"""
    for field, unit in WEIGHT_UNIT.items():
        by_weight = e.get(field)
        if by_weight is None:
            continue
        requested = (m.get("weights") or {}).get(eq_id)
        if not requested:
            warnings.append(issue(
                "weight_unspecified",
                f"{display}: {eq_id} 무게가 지정되지 않아 무게별 수량을 비교할 수 없습니다 "
                f"(초안 movements[].weights.{eq_id}에 {unit} 단위로 지정). 확인 필요.",
                movement=m["id"], equipment=eq_id))
            return None, None, "무게 미지정"
        parts, missing = [], []
        for w in requested:
            q = by_weight.get(weight_key(w))
            if q is None:
                missing.append(f"{weight_key(w)}{unit}")
            else:
                parts.append((weight_key(w), q))
        if missing:
            errors.append(issue(
                "weight_not_owned",
                f"{display}: 보유하지 않은 {eq_id} 무게 {', '.join(missing)} "
                f"(보유: {', '.join(k + unit for k in by_weight)})",
                movement=m["id"], equipment=eq_id, weights=missing))
            return None, None, "보유하지 않은 무게"
        worst = max((q["precision"] for _, q in parts), key=PRECISION_RANK.get)
        total = None if worst == "unknown" else sum(q["value"] for _, q in parts)
        detail = ", ".join(f"{k}{unit}: {_have_text(q)}" for k, q in parts)
        return {"value": total, "precision": worst}, "units", detail

    if m.get("weights", {}).get(eq_id):
        warnings.append(issue(
            "weight_inventory_unknown",
            f"{display}: {eq_id}의 무게별 보유 정보가 없어 지정 무게를 확인할 수 없습니다. 확인 필요.",
            movement=m["id"], equipment=eq_id))
    if e.get("count") is not None:
        return e["count"], "units", None
    if e.get("capacity_athletes") is not None:
        return e["capacity_athletes"], "athletes", None
    return None, None, "수량 정보 없음"


def _compare(target, display, needed, have, kind, warnings, movement_id):
    """필요 수량 vs 보유 수량. 부족해도 오류가 아니라 경고 + 운영 선택지."""
    unit = "명 동시" if kind == "athletes" else "개"
    entry = {"target": target, "needed": needed, "have": have, "kind": kind, "status": None, "options": []}
    if needed is None:
        entry["status"] = "not_compared"
        return entry
    p = have["precision"]
    if p == "unknown":
        entry["status"] = "unknown"
        warnings.append(issue(
            "quantity_unknown",
            f"{display}: {target} 수량 미확인 — 보유는 확인됐지만 필요 {needed}{unit}에 충분한지 코치 확인 필요.",
            movement=movement_id, target=target, needed=needed))
        return entry
    value = have["value"]
    if p == "approx":
        if needed > value:
            entry["status"] = "possibly_short"
            entry["options"] = SHORTAGE_OPTIONS
            warnings.append(issue(
                "possibly_short",
                f"{display}: {target} 부족 가능성 — 필요 {needed}{unit} / 보유 약 {fmt_num(value)}(추정). "
                f"실행 불가는 아님. 운영 선택지: {', '.join(SHORTAGE_OPTIONS)}",
                movement=movement_id, target=target, needed=needed, have=have))
        else:
            entry["status"] = "enough_approx"
            warnings.append(issue(
                "quantity_approx",
                f"{display}: {target} 보유 약 {fmt_num(value)}(추정 수량) — 필요 {needed}{unit}. 실제 수량 확인 권장.",
                movement=movement_id, target=target, needed=needed, have=have))
        return entry
    if needed > value:
        entry["status"] = "short"
        entry["options"] = SHORTAGE_OPTIONS
        warnings.append(issue(
            "short",
            f"{display}: {target} 부족 — 필요 {needed}{unit} / 보유 {fmt_num(value)}. "
            f"실행 불가는 아님. 운영 선택지: {', '.join(SHORTAGE_OPTIONS)}",
            movement=movement_id, target=target, needed=needed, have=have))
    else:
        entry["status"] = "enough"
    return entry


def _blocked_reasons(info, mid, group, data):
    """동작을 WOD에 넣을 수 없는 이유 목록 (대체 동작 후보 거르기에도 사용)."""
    eq = data["equipment"]["equipment"]
    restricted = set((data["equipment"]["space"].get("ceiling") or {}).get("restricted_space_tags") or [])
    reasons = []
    for b in data["equipment"].get("banned_movements") or []:
        if b.get("movement") == mid and group in (b.get("groups") or []):
            reasons.append(("banned", b))
    hits = sorted(set(info.get("space_tags") or []) & restricted)
    if hits:
        reasons.append(("space_restricted", hits))
    for eq_id in info.get("equipment") or []:
        if eq[eq_id].get("available") is False:
            reasons.append(("equipment_not_owned", eq_id))
    return reasons


def _substitutes(info, group, data):
    movements = data["movements"]["movements"]
    out = []
    for s in info.get("substitutes") or []:
        sub = movements[s["id"]]
        if not _blocked_reasons(sub, s["id"], group, data):
            out.append({"id": s["id"], "display": sub["display"], "context": s.get("context")})
    return out


def _append_substitute_text(error, substitutes):
    if substitutes:
        names = ", ".join(f"{s['display']} ({s['context']})" if s["context"] else s["display"]
                          for s in substitutes)
        error["message"] += f" → 대체 후보: {names}"
    else:
        error["message"] += " → 등록된 대체 동작 없음 (에이전트·코치가 선택)"
    error["substitutes"] = substitutes


def _tag(issues, since, index, scale):
    """이번 동작에서 생긴 issue에 위치(index, scale)를 붙이고, 스케일이면 메시지 앞에 레벨을 표시한다."""
    for it in issues[since:]:
        it.setdefault("index", index)
        if scale is not None:
            it.setdefault("scale", scale)
            if not it["message"].startswith("[Scale"):
                it["message"] = f"[Scale {scale}] " + it["message"]


def _check_movement(m, index, data, group, concurrent_default, errors, warnings, scale=None):
    """동작 1개 검사 → item. concurrent_default가 None이면 수량 비교를 하지 않는다."""
    eq = data["equipment"]["equipment"]
    space = data["equipment"]["space"]
    movements = data["movements"]["movements"]
    e0, w0 = len(errors), len(warnings)
    mid = m["id"]
    info = movements.get(mid)
    try:
        if info is None:
            errors.append(issue(
                "unregistered_movement",
                f"미등록 동작 '{mid}' — data/movements.json에 없어 장비·공간을 검증할 수 없습니다. "
                f"등록된 동작으로 바꾸거나 코치 확인 후 등록하세요.",
                movement=mid))
            return {"id": mid, "display": None, "status": "error", "equipment": [], "substitutes": []}

        display = info["display"]
        item = {"id": mid, "display": display, "status": "ok", "equipment": [], "substitutes": []}

        for kind, detail in _blocked_reasons(info, mid, group, data):
            if kind == "banned":
                reason = detail.get("reason") or "사유 미기록"
                errors.append(issue("banned_movement", f"{display}: {group} 수업 금지 동작 ({reason})",
                                    movement=mid))
            elif kind == "space_restricted":
                errors.append(issue(
                    "space_restricted",
                    f"{display}: 층고 제한으로 사용할 수 없습니다 (공간 조건: {', '.join(detail)})",
                    movement=mid, space_tags=detail))
            else:
                errors.append(issue("equipment_not_owned", f"{display}: 미보유 장비 '{detail}'가 필요합니다",
                                    movement=mid, equipment=detail))
            item["status"] = "error"

        if "wall_target" in (info.get("space_tags") or []):
            wt = space.get("wall_target") or {}
            h = wt.get("height_m") or {}
            h_text = _have_text(h) + "m" if h else "높이 미확인"
            std = "" if wt.get("standard_target_available") else ", 표준 높이 타깃 사용 불가"
            warnings.append(issue(
                "wall_target",
                f"{display}: 월볼 타깃은 벽면 {h_text}{std}. 화이트보드에 타깃 높이를 함께 표기하세요.",
                movement=mid, height_m=h or None))

        if item["status"] == "error":
            # 쓸 수 없는 동작은 수량 비교를 하지 않고 대체 동작만 제안한다
            item["substitutes"] = _substitutes(info, group, data)
            _append_substitute_text(errors[-1], item["substitutes"])
            return item

        concurrent = m.get("concurrent_athletes", concurrent_default) if concurrent_default is not None else None
        units = m.get("units_per_athlete", 1)

        for eq_id in info.get("equipment") or []:
            e = eq[eq_id]
            if e.get("available") is False:
                continue  # 위에서 오류 처리
            if e.get("available") is None:
                warnings.append(issue(
                    "availability_unknown",
                    f"{display}: '{eq_id}' 보유 여부 미확인. 확인 필요.", movement=mid, equipment=eq_id))
                item["equipment"].append({"target": eq_id, "status": "availability_unknown"})
                continue
            have, kind, detail = _resolve_have(e, eq_id, m, display, errors, warnings)
            if have is None:
                if detail == "보유하지 않은 무게":
                    item["status"] = "error"
                elif detail == "수량 정보 없음":
                    warnings.append(issue("quantity_unknown",
                                          f"{display}: '{eq_id}' 수량 정보 없음. 확인 필요.",
                                          movement=mid, target=eq_id))
                item["equipment"].append({"target": eq_id, "status": "not_compared", "detail": detail})
                continue
            needed = None if concurrent is None else (concurrent if kind == "athletes" else concurrent * units)
            entry = _compare(eq_id, display, needed, have, kind, warnings, mid)
            entry["detail"] = detail
            item["equipment"].append(entry)

        # 장비가 아닌 공간 수용 인원: space.<동작 id>.capacity_athletes (현재 shuttle_run)
        sp = space.get(mid)
        if isinstance(sp, dict) and sp.get("capacity_athletes") is not None:
            entry = _compare(f"space.{mid}", display, concurrent, sp["capacity_athletes"], "athletes",
                             warnings, mid)
            item["equipment"].append(entry)

        if item["status"] == "error":  # 보유하지 않은 무게
            item["substitutes"] = _substitutes(info, group, data)
            _append_substitute_text(errors[-1], item["substitutes"])
        return item
    finally:
        _tag(errors, e0, index, scale)
        _tag(warnings, w0, index, scale)


def check_equipment(draft, data):
    """→ (errors, warnings, result)"""
    group = draft.get("group", "adult")
    athletes = draft.get("expected_athletes")
    errors, warnings, items = [], [], []

    if athletes is None:
        warnings.append(issue(
            "athletes_unknown",
            "예상 인원(expected_athletes)이 없어 동시 사용 수량을 비교하지 못했습니다. 확인 필요."))

    for i, m in enumerate(draft["movements"]):
        items.append(_check_movement(m, i, data, group, athletes, errors, warnings))

    result = {"group": group, "expected_athletes": athletes, "movements": items}

    scales = draft.get("scales")
    if scales:
        # 스케일 동작도 쓸 수 있는지(미등록·미보유·금지·층고·무게)는 같은 기준으로 검사한다.
        # 스케일별 인원 배분은 알 수 없으므로 수량 비교는 하지 않는다 (지어내지 않음).
        result["scales"] = {}
        for level in sorted(scales):
            result["scales"][level] = [
                _check_movement(m, i, data, group, None, errors, warnings, scale=level)
                for i, m in enumerate(scales[level])]
        warnings.append(issue(
            "scale_quantity_not_compared",
            "스케일별 인원 배분을 알 수 없어 스케일 동작의 장비 수량은 비교하지 않았습니다 "
            "(사용 가능 여부만 검사). Rx와 장비를 나눠 쓰면 코치 확인 필요."))
    return errors, warnings, result


STATUS_TEXT = {
    "enough": "충분",
    "enough_approx": "충분(추정 수량)",
    "short": "부족 — 운영 선택지 필요",
    "possibly_short": "부족 가능성 — 운영 선택지 필요",
    "unknown": "수량 미확인",
    "not_compared": "비교 안 함",
    "availability_unknown": "보유 여부 미확인",
}


def render_text(report, draft):
    r = report["result"]
    athletes = r["expected_athletes"]
    lines = [f"[장비 검증] {draft_label(draft)} / {r['group']} / 예상 인원 "
             f"{str(athletes) + '명' if athletes else '미입력'}"]
    lines.append("동작별 장비 (필요 = 동시 사용 인원 × 1인당 개수, 전원 동시 출발 가정)")
    for it in r["movements"]:
        name = it["display"] or f"{it['id']} (미등록)"
        if it["status"] == "error":
            lines.append(f"  ✗ {name}")
        elif not it["equipment"]:
            lines.append(f"  ✓ {name}: 장비 없음")
        else:
            lines.append(f"  ✓ {name}")
        for e in it["equipment"]:
            if "needed" in e and e.get("have"):
                unit = "명" if e["kind"] == "athletes" else "개"
                needed = f"{e['needed']}{unit}" if e["needed"] is not None else "?"
                detail = f" [{e['detail']}]" if e.get("detail") else ""
                if e["have"]["precision"] == "unknown":
                    have = "보유 수량 미확인"
                else:
                    have = f"보유 {_have_text(e['have'])}{unit}({PRECISION_LABEL[e['have']['precision']]})"
                lines.append(f"      {e['target']}: 필요 {needed} / {have}{detail} → {STATUS_TEXT[e['status']]}")
            else:
                detail = f" ({e['detail']})" if e.get("detail") else ""
                lines.append(f"      {e['target']}: {STATUS_TEXT[e['status']]}{detail}")
    for level, scale_items in (r.get("scales") or {}).items():
        lines.append(f"Scale {level} (사용 가능 여부만 검사, 수량 비교 안 함)")
        for it in scale_items:
            name = it["display"] or f"{it['id']} (미등록)"
            lines.append(f"  {'✗' if it['status'] == 'error' else '✓'} {name}")
    lines += render_issues(report)
    lines.append(render_verdict(report))
    return "\n".join(lines)


def main(argv=None):
    return run_cli(SCRIPT, "WOD 초안의 장비·공간 제약을 검증한다.", check_equipment, render_text, argv)


if __name__ == "__main__":
    sys.exit(main())
