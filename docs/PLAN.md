# PLAN — WOD Planner 설계

- 기획서: https://gist.github.com/nsdictionary/36fa6d76c435011389a925ed4012ef3c
- 작성일: 2026-11-07 (초기 설계) / 갱신: 2026-11-07 (시간 기준: 본운동 최대 30분, 시간 추정 모델, 장비 규칙 정정)

## 1. 핵심 요구사항 (기획서 정리)

### 1.1 사용자와 업무
- **사용자:** 직원 없이 성인·키즈 수업을 혼자 지도하는 크로스핏 박스 코치. 15:00–22:00 수업 후 다음 날 WOD를 설계한다.
- **대신할 업무:** 다음 날 WOD(성인 + 키즈) 초안 작성과 본운동 시간(최대 30분) 검증·라운드 시간 추정.
- **현재 비용:** 주 5–6회, 하루 30–40분. 가장 번거로운 단계는 **장비 가능 여부 확인**과 **라운드 시간·TC 계산**.
- **기존 도구의 한계:** 범용 AI는 박스의 장비·공간·수업 시간을 몰라 매번 설명해야 하고, 없는 기구가 들어간 WOD를 준다.

### 1.2 기능 요구사항
| ID | 요구사항 | 기획서 근거 |
|----|---------|-------------|
| R1 | 코치 입력(오늘 WOD, 주간 플랜, 내일 요일·타임·예상 인원, 특이 회원)을 받는다 | 워크플로 1 |
| R2 | 최근 7일 WOD 기록을 읽고 동작 패턴(당기기·밀기·하체·유산소) 중복을 확인한다 | 워크플로 2 |
| R3 | 보유 장비·공간 제약에 맞는 WOD 초안을 만든다 | 워크플로 3 |
| R4 | 본운동 시간(AMRAP/EMOM 설정 시간, For Time TC)이 30분 이하인지 검증하고, 근거가 있으면 라운드 시간을 추정 범위로 보여 준다 | 워크플로 4, 검증 1 |
| R5 | 인원 대비 장비 회전·동선을 계산한다 | 워크플로 4 |
| R6 | 스케일 A/B/C와 키즈 버전(한국어)을 만든다 | 워크플로 5 |
| R7 | 코치 확인 후에만 날짜별 텍스트 파일로 저장한다 | 워크플로 6, 확인 단계 |
| R8 | 잘못된 입력 처리: 없는 기구 → 대체 제안, 불가능 동작 → 경고·교체, 주간 플랜 없음 → 최근 기록만 사용, 무관한 요청 → "WOD 요청이 아닙니다" | 검증 3 |
| R9 | 실제 완료 라운드·시간 입력 시 예상과의 차이를 기록하고 시간표를 보정한다 | 검증 1 |

### 1.3 박스 제약
**확정 (코치 확인 2026-11-07)**
- 로잉머신 5대
- 셔틀런 1rep = 7.5m 왕복 = 15m
- 월볼은 성인 수업에서 사용 가능 (기획서의 "성인 월볼 불가"는 **정정됨**)

- 점프 박스 9개(20/24 in), 풀업바 약 8명, 셔틀런 약 8명 동시
- 덤벨(kg) 1–20, 바벨(lb) 45×9·35×5, 원판(lb) 10–45 각 약 10장·55×2, 월볼 약 20개, 줄넘기·케틀벨 보유
- 링 보유, 단 **층고가 낮아** 링 머슬업 등 높은 공간이 필요한 동작은 제한 (기획서의 "링 없음"은 **정정됨**)
- 월볼 타깃은 벽면 약 2.3m, **표준 높이 타깃 사용 불가**
- 정확한 값은 `data/equipment.json`이 기준. "약", "여러 개"는 `approx`/`unknown`으로 구분 기록한다.

**미확인 수량:** 덤벨 1/1.5/2/10/15/20kg, 월볼 무게별 구성, 링·줄넘기 개수, 케틀벨 무게·개수, 정확한 층고

**규칙 아님 (기획서 예시):** 셔틀런 6명 이상 2레인, 장비 부족 시 2인 1조 교대.
운영 방식은 WOD 구성과 인원에 따라 달라지므로 에이전트는 선택지만 제안한다.

### 1.3.1 시간 기준 (코치 확정, 2026-11-07)
| 용어 | 정의 | MVP |
|------|------|-----|
| 수업 | 일반적으로 **60분**. 본운동 + 웜업·설명·쿨다운 + 복싱·스트렝스·악세서리 운동 등 | 전체 구성은 Post-MVP |
| WOD 본운동 | **최대 30분**. AMRAP/EMOM = 설정 진행 시간, For Time = TC. 웜업·설명·쿨다운 **불포함** | 30분 이하 검증 대상 |

- 기획서의 "웜업 7 / 설명 4 / WOD 12 / 쿨다운 5 = 28분"은 예시일 뿐 고정 규칙이 아니다.
- For Time은 TC가 있어야 30분 검증이 가능하므로 초안에 TC를 필수로 둔다.

### 1.3.2 동작 시간 원칙 (코치 확정, 2026-11-07)
- 1rep 평균 시간을 근거 없이 고정하지 않는다. 회원 수준·반복 수·피로도·전환 시간에 따라 달라지는 **추정치(범위)**로 설계한다.
- 시간 데이터가 없어도 WOD 생성과 본운동 30분 검증은 가능해야 한다.
- 검증할 수 없는 시간은 "추정 불가" 또는 "확인 필요"로 표시한다. 상세: `data/rules.md` §2–3.

### 1.4 작성 규칙
- 화이트보드용 plain text
- 성인 WOD는 영어, 키즈 WOD는 한국어
- 바벨 lb, 덤벨 kg

### 1.5 성공 기준
- 10일 중 8일 이상, 동작 1개 이하만 고쳐 그대로 화이트보드에 쓸 수 있다.
- 실제 수업에서 WOD가 예상 시간 ±20% 안에 끝난다.

### 1.6 범위 밖 (하지 않는 것)
회원별 기록·PR 관리, TV 화면 송출, 노션 연동, **복싱 파트 구성**, 개인 PT 프로그램.
**60분 전체 수업 구성**(본운동 외 웜업·설명·쿨다운·복싱·스트렝스 등의 시간 배분)은 범위 밖이 아니라 Post-MVP로 미룬다. 단, 복싱 프로그램 내용 생성은 계속 범위 밖이다.
추가로 이번 과제에서는 외부 API, 데이터베이스, 웹 UI, 새 프레임워크를 도입하지 않는다.

> **확인 필요:** 과제 요청문에는 "복싱·크로스핏 코치"로 되어 있으나 기획서는 복싱 파트 구성을 범위 밖으로 둔다.
> 이 설계는 기획서를 따라 **복싱 코치이기도 한 크로스핏 박스 코치**를 사용자로 보되, 복싱 프로그램 생성은 MVP에서 제외한다.

## 2. MVP 범위

기획서 "최소 기능" 3가지에, 과제 목표인 **장비 제약 검증**과 **코치 승인 후 저장**을 명시적으로 포함한다.

| MVP | 내용 | 요구사항 |
|-----|------|---------|
| M1 | `data/`의 장비 목록과 `wods/`의 최근 7일 기록을 읽고 성인 WOD 1개(Rx)를 만든다 | R1, R2(조회만), R3 |
| M2 | WOD에 쓰인 동작이 미보유 장비·금지 목록에 걸리는지, 미확인 장비를 쓰는지 스크립트로 검증하고, 걸리면 대체를 제안하거나 확인을 요청한다 | R3, R8 |
| M3 | 본운동 시간 30분 이하를 스크립트로 검증하고, 시간 데이터가 있으면 라운드 시간·예상 라운드/완료를 추정 범위로, 없으면 "추정 불가"로 출력한다 | R4 |
| M4 | 화이트보드 형식 텍스트를 보여 주고, 코치 승인 후 `wods/YYYY-MM-DD.txt`로 저장한다 | R7 |
| M5 | 위 흐름을 Claude Code Skill 하나로 묶는다 | 전체 |

**MVP 이후(Post-MVP):** 스케일 A/B/C(R6), 키즈 버전(R6), 장비 회전·동선 계산(R5), 패턴 중복 자동 판정(R2), 실제 결과 기록·보정(R9), 60분 전체 수업 구성.
기획서도 "스케일·키즈 버전·장비 회전 계산은 이 세 가지가 된 뒤에 붙인다"고 명시한다.

## 3. 아키텍처

```
코치 ──입력──▶ Claude Code + wod-planner Skill
                 │  ① data/*.json, data/rules.md 읽기
                 │  ② scripts/recent_wods.py      → 최근 7일 기록
                 │  ③ (LLM) WOD 초안 → drafts/<date>.json
                 │  ④ scripts/check_equipment.py  → 장비/금지 검증
                 │  ⑤ scripts/simulate.py         → 본운동 30분 검증·라운드 추정
                 │  ⑥ (LLM) 화이트보드 텍스트 + 시뮬레이션 요약 제시
                 │  ⑦ 코치 수정 요청 → ③으로
                 └  ⑧ 코치 승인 → scripts/save_wod.py → wods/<date>.txt
```

### 주요 설계 결정
1. **판단은 LLM, 계산은 스크립트.** 기획서의 핵심 고통이 "피곤해서 계산을 건너뜀"이므로, 숫자는 항상 결정적 스크립트가 낸다. LLM 암산은 근거로 쓰지 않는다.
2. **Skill + 파일 데이터.** 박스 고유 정보는 Skill 본문이 아니라 `data/`에 둔다. CLAUDE.md는 항상 로드되므로 짧게 유지하고, WOD 워크플로는 요청 시에만 로드되는 Skill로 분리한다(기획서의 "CLAUDE.md vs skill" 질문에 대한 답).
3. **초안은 구조화된 JSON.** LLM이 만든 초안을 JSON(`drafts/`)으로 써야 스크립트가 검증·계산할 수 있다. 화이트보드 텍스트는 이 JSON에서 만든다.
4. **승인 게이트를 이중으로.** Skill 절차상 승인 확인 + `save_wod.py`가 `--approved` 플래그 없이는 저장 거부, 같은 날짜 파일이 있으면 거부.
5. **저장 형식은 plain text.** 화이트보드에 그대로 옮길 수 있고, `recent_wods.py`가 다시 읽을 수 있도록 상단에 간단한 메타데이터 헤더를 둔다.
6. **표준 라이브러리만.** 설치 없이 Claude Code와 Codex CLI 어디서든 바로 실행·테스트 가능.
7. **모르는 시간은 모른다고 표시.** 동작 시간은 근거 있는 범위만 쓰고, 없으면 "추정 불가". 본운동 30분 검증은 형식·시간만으로 결정되므로 시간 데이터 없이도 항상 동작한다.

## 4. 데이터 형식 (Phase 1 확정 — 실제 파일이 기준, 아래는 발췌)

공통: `null` = 코치 미확인. 항목마다 `source`를 둔다.
`코치 확정` = 코치가 확인한 운영 사실 / `기획서` = 기획서 본문 명시(재확인 전) / `기획서 예시` = 예시 WOD에만 등장, **규칙 아님**.

### 4.1 `data/equipment.json`
```json
{
  "equipment": {
    "rower":      {"available": true, "count": {"value": 5, "precision": "exact"}},
    "box":        {"available": true, "count": {"value": 9, "precision": "exact"}, "heights_in": [20, 24]},
    "pullup_bar": {"available": true, "capacity_athletes": {"value": 8, "precision": "approx"}},
    "dumbbell":   {"available": true, "by_weight_kg": {"3": {"value": 2, "precision": "exact"}, "10": {"value": null, "precision": "unknown"}}},
    "barbell":    {"available": true, "by_weight_lb": {"45": {"value": 9, "precision": "exact"}}},
    "rings":      {"available": true, "count": {"value": null, "precision": "unknown"}}
  },
  "banned_movements": [],
  "space": {
    "ceiling":     {"height_m": null, "is_low": true, "restricted_space_tags": ["high_ceiling"]},
    "wall_target": {"height_m": {"value": 2.3, "precision": "approx"}, "standard_target_available": false},
    "shuttle_run": {"one_way_m": 7.5, "rep_distance_m": 15, "capacity_athletes": {"value": 8, "precision": "approx"}}
  },
  "operational_examples": [
    {"example": "셔틀런 6명 이상 동시 출발 시 2개 레인", "source": "기획서 예시", "is_rule": false},
    {"example": "박스 부족 시 2인 1조 교대", "source": "기획서 예시", "is_rule": false}
  ]
}
```
- `available`: `true` 보유 / `false` 미보유(사용 불가) / `null` 미확인("확인 필요").
- 수량: `{"value", "precision"}`. `exact` 정확 / `approx` "약 N"(추정 수량 경고) / `unknown` 보유·수량 미확인(수량 미확인 경고, `value: null`).
- 단위: 바벨·원판 `by_weight_lb`, 덤벨·케틀벨 `by_weight_kg`.
- 공간 제약: 동작의 `space_tags`가 `space.ceiling.restricted_space_tags`에 걸리면 사용 불가, `wall_target`이면 타깃 높이 경고.
- `banned_movements`: 구조는 유지, 현재 비어 있음(성인 월볼 금지 제거).
- `operational_examples`: 참고 사례. 스크립트는 규칙으로 적용하지 않는다.

### 4.2 `data/movements.json`
```json
{
  "movements": {
    "toes_to_bar": {
      "display": "Toes-to-Bar", "unit": "rep", "time_estimate": null,
      "patterns": ["pull"], "equipment": ["pullup_bar"], "space_tags": [], "rx_standard": null,
      "substitutes": [{"id": "hanging_knee_raise", "context": "Scale A"}, {"id": "v_up", "context": "Scale B, 손목 통증 회원"}]
    },
    "row": {"display": "Row", "unit": "m", "time_estimate": null, "patterns": ["cardio"], "equipment": ["rower"]}
  }
}
```
- `time_estimate`: 근거가 생기면 `{"sec_per_unit": {"low": 초, "high": 초}, "basis": "근거", "updated": "YYYY-MM-DD"}`. 범위는 회원 수준 차이를 반영한다. 지금은 전부 `null`.
- `unit`: `rep` 또는 `m`(로잉은 1m당 초).
- `patterns`: 4분류(pull/push/legs/cardio). 현재 값은 에이전트 분류 초안(코치 확인 필요).
- 등록 동작: 기획서 등장분(Toes-to-Bar, Hanging Knee Raise, V-up, Box Jump, Step-up, Shuttle Run, Row, Burpee, Wall Ball) + 코치가 언급한 제한 동작 Ring Muscle-up.

### 4.2.1 `data/rules.md`
사람이 읽는 규칙 + 스크립트가 읽는 **첫 번째 `json` 코드 블록**(기계 판독 설정).
```json
{
  "class_total_min": 60,
  "workout_max_min": 30,
  "workout_time_basis": {"AMRAP": "duration_min", "EMOM": "duration_min", "FOR_TIME": "time_cap_min"},
  "estimation": {"transition_sec_range": null, "fatigue_slowdown_per_round": null},
  "recent_days": 7,
  "patterns": ["pull", "push", "legs", "cardio"],
  "supported_formats": ["AMRAP", "EMOM", "FOR_TIME"]
}
```
시간 출력 상태(검증됨 / 추정 / 추정 불가 / 확인 필요)와 추정 모델은 `rules.md` §2–3에 정의한다.

### 4.3 WOD 초안 `drafts/<date>.json`
```json
{
  "date": "2026-11-10",
  "class_time": "18:30",
  "expected_athletes": 12,
  "format": "AMRAP",
  "duration_min": 12,
  "time_cap_min": null,
  "rounds": null,
  "movements": [
    {"id": "toes_to_bar", "reps": 10},
    {"id": "box_jump", "reps": 15, "load": "24/20 in"},
    {"id": "shuttle_run", "reps": 20}
  ],
  "notes": ["손목 아픈 회원: Toes-to-Bar → V-ups"]
}
```
선택 필드 (Phase 2에서 추가, 없으면 기본값):
- `group`: `adult`(기본) / `kids` — `banned_movements`의 그룹 판정에 사용
- `movements[].weights`: `{"dumbbell": [15, 10]}`처럼 장비별 무게 목록. 단위는 데이터 키를 따른다(덤벨·케틀벨 kg, 바벨 lb)
- `movements[].units_per_athlete`: 1인당 장비 개수 (기본 1, 예: 덤벨 2개)
- `movements[].concurrent_athletes`: 이 동작을 동시에 하는 인원 (기본 `expected_athletes`, 파트너 WOD 등)
- `unit`이 `m`인 동작은 `reps`가 미터다 (예: Row 250)

구조 오류(타입·필수 필드)는 `scripts/common.py`가 모두 모아 종료 코드 2로 알린다.

MVP 지원 형식: `AMRAP`(`duration_min`), `EMOM`(`duration_min`), `FOR_TIME`(`rounds` + `time_cap_min` 필수).
EMOM은 본운동 시간 검증만 하고, 분당 작업량 추정은 Post-MVP.

### 4.4 저장 파일 `wods/YYYY-MM-DD.txt`
```
# date: 2026-11-10
# format: AMRAP 12
# patterns: pull, legs, cardio
# approved_by: coach

WOD - AMRAP 12
10 Toes-to-Bar
...

[시뮬레이션]
...
```

## 5. 스크립트 명세 (Phase 2·4에서 구현)

| 스크립트 | 입력 | 출력 | 실패 조건 |
|---------|------|------|----------|
| `recent_wods.py` | `--date`, `--days 7` | 기간 내 WOD 파일 목록·본문·패턴 | — |
| `check_equipment.py` | 초안 JSON | 동작별 필요 장비, 미보유/금지 항목, 보유 여부·수량 미확인 "확인 필요", 필요 수량 vs 보유 수량 | 미보유·금지 동작 포함 시 종료 코드 1 |
| `simulate.py` | 초안 JSON | ① 본운동 시간 30분 이하 여부(검증됨) ② 라운드 시간·예상 라운드/완료(추정 범위+근거, 또는 추정 불가+없는 데이터 목록) | 본운동 30분 초과, For Time인데 TC 없음, 미지원 형식이면 종료 코드 1. 시간 데이터 누락은 실패가 아님("추정 불가") |
| `save_wod.py` | 초안 JSON 또는 텍스트, `--approved` | `wods/<date>.txt` 생성 | `--approved` 없음, 파일 이미 존재 |

공통: `--json` 옵션으로 기계 판독 출력, 기본은 한국어 사람용 출력. `--data-dir`로 데이터 디렉터리 교체.

**종료 코드 (Phase 2 확정):** `0` 통과(경고 가능) / `1` 규칙 위반 / `2` 입력·데이터 오류(파일 없음, JSON 파싱, 스키마).

**JSON 출력 형식 (Phase 2 확정):**
```json
{"script": "simulate", "ok": true, "exit_code": 0,
 "errors": [{"code": "...", "message": "..."}], "warnings": [], "result": {}}
```

**`check_equipment.py` 판정 (Phase 2 확정):**
- 오류: 미등록 동작, 미보유 장비, 금지 동작(그룹별), 층고 제한, 보유하지 않은 무게 → 대체 동작 제안(대체 후보도 같은 검사를 통과한 것만)
- 경고: 보유 여부 미확인, `approx`/`unknown` 수량, 무게 미지정, 월볼 타깃 높이
- 수량: 필요 = 동시 인원 × 1인당 개수(전원 동시 출발 가정). 부족해도 **오류가 아님** — 경고 + 운영 선택지(파트너 교대, 시차 출발, 시작 동작 분산)
- 공간 수용 인원: `space.<동작 id>.capacity_athletes`가 있으면 비교 (현재 `shuttle_run`)
- 오류로 쓸 수 없는 동작은 수량 비교를 생략

### 시간 계산 모델 (MVP)
1. **본운동 검증 (항상 수행, 검증됨):** 본운동 시간 = AMRAP/EMOM `duration_min`, For Time `time_cap_min`. `workout_max_min`(30) 초과 시 실패.
2. **라운드 시간 추정 (데이터가 있을 때만, 추정):**
   - 라운드 시간 범위 = Σ(reps × `sec_per_unit.low`~`high`) + 전환(`transition_sec_range` × 동작 수)
   - AMRAP: 예상 라운드 범위 = 본운동 시간 ÷ 라운드 시간 범위
   - For Time: 예상 완료 범위 = rounds × 라운드 시간 범위, TC 초과 가능성 경고
   - 피로도 값이 `null`이면 "피로도 미반영" 표시
3. **추정 불가:** 해당 WOD 동작 중 하나라도 `time_estimate`가 없거나 `transition_sec_range`가 없으면 2를 건너뛰고 없는 항목을 나열한다.
4. 웜업·설명·쿨다운과 60분 수업 전체 타임라인은 계산하지 않는다 (Post-MVP).

## 6. Skill 설계 (Phase 3 — 구현됨)

`.claude/skills/wod-planner/SKILL.md` (실제 절차는 이 파일이 기준)
- **frontmatter description:** 코치가 다음 날 WOD 작성·수정·저장을 요청할 때 사용. 무관한 요청에는 사용하지 않음.
- **본문 절차:** §3의 ①–⑧. 각 단계에서 실행할 명령과 실패 시 행동(대체 동작 제안, 코치에게 질문)을 명시.
- **출력 템플릿:** 기획서 "결과물 예시" 형식 (WOD / Scale / [시뮬레이션]).
- **금지:** 승인 없는 저장, 스크립트 결과 없이 숫자 제시, 추정 불가인 시간을 지어내기, `data/`에 없는 장비 사용.

구현 결정 (Phase 3):
- `allowed-tools`: Read, Glob, `python3 scripts/simulate.py`, `python3 scripts/check_equipment.py` (Skill 실행 중 확인 없이 허용)
- 초안은 Write로 `drafts/<date>.json`에 쓴다. 검증은 두 스크립트를 `--json`으로 실행하고 `exit_code`별로 처리(1 → 수정 표대로 고쳐 재검증, 최대 3회 / 2 → 초안 구조 수정).
- `recent_wods.py`가 없는 동안은 `wods/*.txt`를 직접 읽는다. `save_wod.py`가 없는 동안은 승인을 받아도 저장하지 않고 "저장 기능 미구현"을 알린다. 두 스크립트가 생기면 Skill이 그것을 쓰도록 이미 적어 두었다.
- 프로젝트 설정 `.claude/settings.json`: 두 검증 스크립트·단위 테스트 실행과 `drafts/**` 편집 허용, `wods/**` 직접 편집 금지(deny). 저장은 Bash로 실행하는 `save_wod.py`만 가능.

## 7. 구현 단계

| Phase | 내용 | 완료 조건 |
|-------|------|----------|
| 0 | 설계 문서 | AGENTS/CLAUDE/PLAN/PROGRESS/README 작성 |
| 1 | 데이터 파일: `equipment.json`, `movements.json`, `rules.md` 스키마 확정 + 기획서에 있는 값만 입력 | 미확인 값 목록이 PROGRESS에 정리됨, 코치 확인 |
| 2 | `simulate.py`, `check_equipment.py` + 단위 테스트 | 기획서 예시 WOD로 테스트 통과 (시간 데이터 있음/없음 두 경우 모두) |
| 3 | `wod-planner` Skill 작성 + 최소 설정 (`.claude/settings.json`) | Skill 발견, 자연어 요청 1건으로 초안→두 검증→보고→승인 대기, `wods/` 미생성 확인 |
| 4 | `recent_wods.py`, `save_wod.py` + 테스트 (승인 플래그, 덮어쓰기 거부) + §8.2 시나리오 S1–S6 | 테스트 통과, 시나리오 기록 |
| 5 | Post-MVP: 스케일 A/B/C, 키즈 버전, 장비 회전, 패턴 중복 판정, 실제 결과 보정, 60분 전체 수업 구성 | 항목별 별도 정의 |

## 8. 테스트 방법

### 8.1 단위 테스트 (`python3 -m unittest discover -s tests -v`)
- `simulate`: 기획서 예시(AMRAP 12: T2B 10 / Box Jump 15 / Shuttle 20)로
  - 시간 데이터 없음 → 본운동 12분 ≤ 30분 "검증됨", 라운드 시간 "추정 불가" + 없는 동작 목록, 종료 코드 0
  - 픽스처의 테스트용 범위 값 → 라운드 시간·예상 라운드 범위 계산, 피로도 `null`이면 "피로도 미반영" 표시
  - AMRAP 35 → 실패, For Time인데 TC 없음 → 실패, EMOM 20 → 검증됨
- `check_equipment`: 링 머슬업 → 층고 제한으로 불가, 성인 월볼 → 허용 + 타깃 높이 경고, 풀업바 12명 vs 약 8명 → 추정 수량 경고, 덤벨 10kg → 수량 미확인 경고, 로잉 5대 vs 12명 → 필요/보유 수량 표시(운영 방식은 강제하지 않음), 보유 여부·수량 `null` → 확인 필요, 픽스처의 `banned_movements` 항목 → 금지.
- `save_wod`: `--approved` 없으면 거부, 같은 날짜 파일 존재 시 거부, 임시 디렉터리에 정상 저장.
- `recent_wods`: 임시 디렉터리 픽스처로 7일 경계·날짜 정렬·헤더 파싱 검증.

테스트는 실제 `data/`·`wods/` 대신 `tests/fixtures/`와 임시 디렉터리를 사용한다.

### 8.2 에이전트 시나리오 테스트 (Phase 3에서 S1 확인, 전체는 Phase 4 — 결과를 PROGRESS에 기록)
| ID | 입력 | 기대 결과 |
|----|------|----------|
| S1 | 기획서 "입력 예시" 그대로 | 짐내스틱 위주 WOD, 로잉·버피와 패턴 겹침 언급, 본운동 30분 검증, 시간 데이터 없으면 "추정 불가"로 표시, 손목 회원 대체 제시, 저장 전 승인 요청 |
| S2 | "링 머슬업 넣어줘" | 층고 제한을 이유로 만들지 않고 대체 동작 제안 |
| S3 | "AMRAP 40분으로 짜줘" | 본운동 30분 초과로 거부하고 30분 이하로 조정 제안 |
| S4 | 주간 플랜 없이 요청 | 최근 기록만으로 생성 |
| S5 | "오늘 저녁 메뉴 추천해줘" | "WOD 요청이 아닙니다" |
| S6 | 승인 없이 "좋네" 정도의 반응 | 저장하지 않고 명시적 승인 재확인 |

## 9. 미결정 사항 / 코치 확인 필요
상세 목록과 체크 상태는 `docs/PROGRESS.md` "코치 확인 필요"가 기준이다.
- 장비 미확인 수량: 덤벨 1/1.5/2/10/15/20kg, 월볼 무게별 구성, 링·줄넘기 개수, 케틀벨 무게·개수, 정확한 층고 (Phase 1 완료에는 영향 없음, 검증 시 경고로 처리)
- 동작별 시간 추정 범위와 근거, 전환 시간 범위, 피로도 반영 방식
- 동작 패턴 분류 초안
- 복싱 관련 요구사항 범위 (§1.6 참고)
