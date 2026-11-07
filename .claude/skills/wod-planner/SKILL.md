---
name: wod-planner
description: 크로스핏 박스 코치의 WOD 작성·수정·검증 요청을 처리한다 ("내일 WOD 짜줘", "12명 AMRAP 15분 만들어줘", "이 WOD 30분 안에 되는지 봐줘", "T2B 빼고 다시"). 박스 데이터(data/)로 WOD 초안 JSON을 만들어 drafts/에 두고, scripts/simulate.py와 scripts/check_equipment.py로 검증한 뒤 결과를 보고하고 코치 승인을 기다린다. 운동과 무관한 요청에는 사용하지 않는다.
allowed-tools: Read, Glob, Bash(python3 scripts/simulate.py:*), Bash(python3 scripts/check_equipment.py:*)
---

# WOD Planner

코치의 자연어 요청으로 **다음 WOD 초안**을 만들고, 기존 스크립트로 검증해 결과를 보여 준 뒤 **승인을 기다리며 멈춘다.**

역할 분담 (AGENTS.md §2):
- **너(LLM):** 요청 해석, 동작 선택·조합, 대체 동작 제안, 화이트보드 문장 작성, 코치와 대화
- **스크립트:** 본운동 시간 검증, 완주 가능성 추정, 장비·공간 검증 — 시간·수량 숫자는 전부 여기서 나온다
- **코치:** 최종 판단과 저장 승인

## 절대 규칙

1. **`wods/`에 직접 쓰지 않는다.** Write·Edit·Bash 어떤 방법으로도. 저장은 승인 후 `scripts/save_wod.py`로만 한다 (§7).
2. **초안과 최종본을 구분한다.** 초안은 `drafts/<date>.json`(임시, git 제외)에만 쓴다. 초안 작성은 저장이 아니다.
3. **시간·수량을 지어내지 않는다.** 라운드 시간, 예상 라운드, 1rep 시간, 전환 시간, 장비 수량을 직접 계산하거나 추정해서 쓰지 않는다. 스크립트 JSON에 있는 값만 인용한다. 스크립트가 "추정 불가"라고 하면 그대로 "추정 불가"라고 보고한다.
4. **`data/` 파일을 수정하지 않는다.** 등록되지 않은 동작이나 장비가 필요하면 코치에게 알리고 지시를 받는다.
5. **쓸 수 없는 동작은 넣지 않는다.** 미보유 장비(`available: false`), 금지 동작(`banned_movements`, 그룹별), 층고 제한(`space_tags`에 `high_ceiling` — 링 머슬업 등)이 걸린 동작. 코치가 직접 요청해도 이유를 설명하고 대체 동작을 제안한다.
6. **경고를 숨기지 않는다.** 스크립트 경고는 모두 코치에게 전달한다.

## 0. 요청 범위 판단

- 운동과 무관한 요청 → "WOD 요청이 아닙니다"라고만 답하고 끝낸다.
- 범위 밖(회원별 기록·PR 관리, TV 송출, 노션 연동, 복싱 파트 구성, 개인 PT, 60분 전체 수업 구성) → 지원하지 않는다고 짧게 알린다. 요청에 WOD 부분이 있으면 그 부분만 진행한다.
- 키즈 WOD·Scale A/B/C는 MVP 범위 밖이다. 성인 Rx WOD를 만들고, 특이 회원 대체 동작만 `notes`로 제시한다.

## 1. 데이터 읽기

매번 실제 파일을 읽는다 (내용을 기억에 의존하지 않는다).

1. `data/rules.md` — 시간 기준(본운동 최대 30분), 시간 표시 4상태, 작성 규칙, 기계 판독 설정
2. `data/equipment.json` — 보유 장비·수량 정확도(`exact`/`approx`/`unknown`), 공간 제약(층고, 월볼 타깃, 셔틀런)
3. `data/movements.json` — 등록 동작 id, `display`, `unit`, `equipment`, `space_tags`, `patterns`, `substitutes`, `rx_standard`
4. 최근 기록: Glob `wods/*.txt` → 목표 날짜 이전 `recent_days`(rules.md, 7일) 안의 파일만 Read.
   - 파일 상단 `# patterns:` 헤더나 본문 동작으로 패턴(pull/push/legs/cardio)을 파악한다.
   - `scripts/recent_wods.py`가 생기면 그것을 우선 사용한다. 지금은 없다.
   - 기록이 없으면 "최근 기록 없음"으로 보고하고 계속 진행한다. 코치가 말한 "오늘 WOD"도 최근 기록으로 취급한다.

## 2. 요청 해석

| 항목 | 초안 필드 | 필수 | 없을 때 |
|------|-----------|------|---------|
| 날짜 | `date` (YYYY-MM-DD) | ✓ | "내일" 등 상대 표현은 오늘 날짜 기준으로 변환. 단서가 전혀 없으면 질문 |
| 예상 인원 | `expected_athletes` | ✓ | 질문. 코치가 "모름"이면 `null`로 진행(장비 수량 비교 생략 경고가 나옴) |
| 형식 | `format`: `AMRAP` / `EMOM` / `FOR_TIME` | | 네가 선택하고 이유를 한 줄로 밝힌다 |
| 시간 | AMRAP·EMOM `duration_min`, For Time `time_cap_min` + `rounds` | | 네가 정한다. 30분 이하. For Time은 TC·rounds 필수 |
| 수업 시간 | `class_time` | | 생략 가능 |
| 그룹 | `group`: `adult`(기본) / `kids` | | adult |
| 선호·회피 동작, 주간 플랜, 특이 회원 | 동작 선택과 `notes`에 반영 | | 없으면 최근 기록만으로 판단 |

- **빠진 필수 항목만 한 번에 묻는다.** 형식·시간·동작처럼 네가 정할 수 있는 것은 묻지 않는다.
- 코치가 30분을 넘는 시간을 요청하면 만들지 않고 30분 이하로 조정하자고 제안한다.

## 3. 동작 선택

- `data/movements.json`에 **등록된 id만** 쓴다. 미등록 동작을 요청받으면 등록된 비슷한 동작을 제안하고, 등록이 필요하면 코치에게 맡긴다.
- 절대 규칙 5의 동작은 제외한다. 보유 여부가 `null`인 장비가 필요한 동작은 가능하면 피하고, 쓰면 "확인 필요"로 보고한다.
- 최근 기록·오늘 WOD와 패턴(`patterns`)이 겹치지 않게 고르고, 겹치면 이유를 보고한다.
- 반복 수와 라운드 구성은 코치 의도와 일반적인 WOD 구성으로 판단한다. 단, "이 구성이면 몇 분 걸린다"는 주장은 하지 않는다 (스크립트 추정만 인용).
- 무게를 쓰는 동작은 `movements[].weights`로 무게를 지정한다 (덤벨·케틀벨 kg, 바벨 lb — 데이터 키 단위).
- 파트너·교대 운영을 의도하면 `concurrent_athletes`(동시에 하는 인원)를 지정한다. 1인당 장비가 2개면 `units_per_athlete: 2`.
- 특이 회원(예: 손목 통증)은 해당 동작의 `substitutes`에서 대체를 골라 `notes`에 적는다.

## 4. 초안 JSON 작성 → `drafts/<date>.json`

Write 도구로 `drafts/<date>.json`에 쓴다 (`drafts/`는 git 제외 임시 폴더, 같은 날짜 초안은 수정본으로 덮어써도 된다).

```json
{
  "date": "2026-11-10",
  "class_time": "18:30",
  "expected_athletes": 12,
  "group": "adult",
  "format": "AMRAP",
  "duration_min": 12,
  "time_cap_min": null,
  "rounds": null,
  "movements": [
    {"id": "toes_to_bar", "reps": 10},
    {"id": "box_jump", "reps": 15, "load": "24/20 in"},
    {"id": "shuttle_run", "reps": 20}
  ],
  "notes": ["손목 통증 회원: Toes-to-Bar → V-ups"]
}
```

- `unit`이 `m`인 동작(Row)은 `reps`가 미터다.
- 선택 필드: `movements[].load`(표기용 문자열), `weights`, `units_per_athlete`, `concurrent_athletes`. 상세는 `docs/PLAN.md` §4.3.

## 5. 검증

두 스크립트를 **항상 `--json`으로** 실행한다.

```bash
python3 scripts/simulate.py drafts/<date>.json --json
python3 scripts/check_equipment.py drafts/<date>.json --json
```

출력 형식: `{"script", "ok", "exit_code", "errors": [{code, message, ...}], "warnings": [...], "result": {...}}`

| exit_code | 뜻 | 할 일 |
|-----------|----|-------|
| 0 | 통과 (경고 가능) | 보고 단계로 |
| 1 | 규칙 위반 | 아래 수정 표대로 초안을 고치고 **두 스크립트 모두** 다시 실행 |
| 2 | 입력 오류 (초안 구조·JSON) | 네 초안 작성 실수다. `errors`의 필드 경로를 보고 고쳐서 다시 실행 |

수정 표 (exit 1):
| code | 수정 |
|------|------|
| `workout_too_long` | 시간을 30분 이하로 줄인다 |
| `time_cap_missing` / `rounds_missing` / `duration_missing` | 빠진 필드를 채운다 |
| `unsupported_format` | AMRAP / EMOM / FOR_TIME 중 하나로 |
| `unregistered_movement` | 등록된 동작으로 교체 |
| `equipment_not_owned` / `banned_movement` / `space_restricted` / `weight_not_owned` | 오류의 `substitutes`가 있으면 그중에서, 없으면 같은 패턴의 쓸 수 있는 등록 동작으로 교체 |

- 재검증은 **최대 3회**. 그래도 오류가 남으면 멈추고 남은 오류와 시도한 수정을 코치에게 보고한다.
- 자동 수정한 내용(무엇을 왜 바꿨는지)은 반드시 보고에 포함한다. 코치가 직접 요청한 동작을 바꿨다면 특히 분명히 알린다.

결과 해석:
- `simulate` `result.workout_time.status`: `verified`(검증됨) / `failed`
- `simulate` `result.estimate.status`:
  - `estimated` → `round_sec`, `expected_rounds` 또는 `expected_finish_sec`, `breakdown[].text`(근거), `notes`를 인용
  - `not_estimable` → `reason`과 `missing[]`을 그대로 보고. 숫자를 채우지 않는다
  - `skipped` → 시간 검증 실패로 추정 안 함
- `check_equipment` `result.movements[].equipment[]`: `status` = `enough` / `enough_approx` / `short` / `possibly_short` / `unknown` / `not_compared` / `availability_unknown`. 부족은 **실행 불가가 아니다** — 경고의 운영 선택지(`options`)를 코치에게 제시하고 고르게 한다.

## 6. 코치에게 보고 (그리고 멈춘다)

아래 형식으로 한국어로 보고한다. WOD 본문은 영어(성인), 화이트보드에 옮길 수 있는 plain text.

````
## WOD 초안 — <date> <class_time> / <expected_athletes>명

```
WOD - AMRAP 12
10 Toes-to-Bar
15 Box Jumps (24/20 in)
20 Shuttle Runs (15m = 1 rep)
```

### 본운동 시간 검증 — 검증됨
AMRAP 설정 시간 12분 ≤ 상한 30분

### 완주 가능성 — 추정 불가
(reason) / 누락: (missing[] 나열)
— 추정이면: 라운드당 a~b, 예상 라운드 c~d, 근거(breakdown), 주의(notes)

### 장비·운영
- (경고 하나당 한 줄, 스크립트 메시지 요지 + 필요/보유 수량)
- 운영 선택지: (options) — 코치가 선택

### 최근 기록
(최근 7일 패턴과 겹침 여부, 기록 없으면 "최근 기록 없음")

### 자동 수정 내역
(있을 때만)

### 특이 회원
(notes)

---
초안은 `drafts/<date>.json`에 있습니다 (아직 저장 전).
이대로 확정해 저장할까요? **"저장"** 또는 **"승인"**이라고 답해 주세요. 수정할 점이 있으면 말씀해 주세요.
````

- 시간·장비 섹션의 숫자는 모두 스크립트 JSON에서 온 것이어야 한다.
- 월볼을 넣었다면 화이트보드 줄에 타깃 높이를 함께 적는다 (예: `20 Wall Balls (target ~2.3m)`, 높이는 `equipment.json` `space.wall_target` 값).
- **보고 후 멈추고 코치 답을 기다린다.** 승인 없이 다음 단계로 가지 않는다.

## 7. 코치 응답 처리

- **수정 요청** ("T2B 빼줘", "15분으로") → §3부터 다시. 초안 덮어쓰기 → 재검증 → 재보고.
- **애매한 반응** ("좋네", "괜찮은 듯", "음") → 승인으로 보지 않는다. "저장할까요?"라고 다시 묻는다.
- **명시적 승인** ("저장", "승인", "확정", "이대로 저장해"):
  1. 마지막 검증 이후 초안이 바뀌지 않았고 두 스크립트 모두 exit 0인지 확인한다. 아니면 재검증부터.
  2. `scripts/save_wod.py`가 있으면: 그 스크립트의 사용법(`--help`)대로 `--approved`를 붙여 실행한다. 같은 날짜 파일이 이미 있어 거부되면 덮어쓰지 말고 코치에게 알리고 지시를 받는다.
  3. `scripts/save_wod.py`가 **없으면 (현재 상태):** 저장하지 않는다. "승인은 확인했지만 저장 기능(`save_wod.py`)이 아직 구현되지 않아 `wods/`에 저장하지 않았습니다. 초안은 `drafts/<date>.json`에 남아 있습니다."라고 알린다. 다른 방법으로 `wods/`에 쓰지 않는다.
