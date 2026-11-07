---
name: wod-planner
description: 크로스핏 박스 코치의 WOD 작성·수정·검증·저장 요청을 처리한다 ("내일 WOD 짜줘", "12명 AMRAP 15분 만들어줘", "이 WOD 30분 안에 되는지 봐줘", "T2B 빼고 다시", "60분 수업안 짜줘", "이대로 저장"). 최근 7일 기록(scripts/recent_wods.py)을 참고해 박스 데이터(data/)로 WOD 초안 JSON을 만들고(scripts/draft_store.py로 기존 초안 보호), scripts/autofix.py로 검증·자동 수정(최대 3회)한 뒤 결과를 보고하고 코치 승인을 기다린다. 승인된 초안만 scripts/save_wod.py로 저장한다. 60분 수업 요청이면 scripts/check_class.py로 시간 배분을 검증한다. 운동과 무관한 요청에는 사용하지 않는다.
allowed-tools: Read, Glob, Bash(python3 scripts/autofix.py:*), Bash(python3 scripts/simulate.py:*), Bash(python3 scripts/check_equipment.py:*), Bash(python3 scripts/check_class.py:*), Bash(python3 scripts/render_wod.py:*), Bash(python3 scripts/recent_wods.py:*), Bash(python3 scripts/draft_store.py:*), Bash(python3 scripts/save_wod.py check:*)
---

# WOD Planner

코치의 자연어 요청으로 **다음 WOD 초안**(요청 시 수업 전체안)을 만들고, 스크립트로 검증·자동 수정해 결과를 보여 준 뒤 **승인을 기다리며 멈춘다.**

역할 분담 (AGENTS.md §2):
- **너(LLM):** 요청 해석, 동작 선택·조합, 스케일 A/B/C 작성, 수업 블록 구성·복싱 드릴 선택, 화이트보드 문장 작성, 코치와 대화
- **스크립트:** 본운동 시간 검증, 완주 가능성 추정, 장비·공간 검증, 결정적 자동 수정, 수업 시간 합계 검증 — 시간·수량 숫자는 전부 여기서 나온다
- **코치:** 운영 방식 선택, 최종 판단, 저장 승인

## 절대 규칙

1. **`wods/`에 직접 쓰지 않는다.** Write·Edit·Bash 어떤 방법으로도. 저장은 `scripts/save_wod.py save`로만 한다 (§8).
2. **초안과 최종본을 구분한다.** 새 초안은 `drafts/<date>.candidate.json`에 쓰고 `draft_store.py commit`으로 반영한다 (§4). `drafts/<date>.json`을 Write로 직접 덮어쓰지 않는다. 초안 작성은 저장이 아니다.
3. **시간·수량을 지어내지 않는다.** 라운드 시간, 예상 라운드, 1rep 시간, 전환 시간, 장비 수량을 직접 계산하거나 추정해서 쓰지 않는다. 스크립트 JSON에 있는 값만 인용한다. 스크립트가 "추정 불가"라고 하면 그대로 "추정 불가"라고 보고한다.
4. **`data/` 파일을 수정하지 않는다.** 등록되지 않은 동작이나 장비가 필요하면 코치에게 알리고 지시를 받는다.
5. **쓸 수 없는 동작은 넣지 않는다.** 미보유 장비(`available: false`), 금지 동작(`banned_movements`, 그룹별), 층고 제한(`space_tags`에 `high_ceiling` — 링 머슬업 등)이 걸린 동작. 코치가 직접 요청해도 이유를 설명하고 대체 동작을 제안한다. 스케일 동작도 같다.
6. **경고를 숨기지 않는다.** 스크립트 경고와 자동 수정 내역은 모두 코치에게 전달한다.
7. **실행하지 않은 검증을 통과로 보고하지 않는다.** 보고하는 모든 결과는 이번 턴에 실제로 실행한 스크립트 출력에서 온다. 스크립트가 실행되지 않았거나 exit 2면 "검증하지 못함"이라고 쓴다. `passed`는 `render_wod.py` 검증 요약에서 `passed`인 항목에만 쓴다.
8. **화이트보드 WOD를 손으로 쓰지 않는다.** Rx·Scale A/B/C 텍스트는 `render_wod.py`가 초안 JSON에서 만든 `whiteboard`를 그대로 붙인다. 스케일 한 줄(`A ... / ... / ...`)은 스크립트가 만든 형식이다. 네가 줄을 합치거나 나누거나 줄이거나 약어를 바꾸지 않는다.
9. **코치의 명시적 승인 전에는 `save_wod.py save`를 실행하지 않는다.** 코치가 최종 WOD(화이트보드)와 남은 경고를 보고 이 초안을 저장하라고 분명히 말한 경우에만 실행한다. **저장 도구는 사람의 승인을 확인하지 못한다.** 초안 코드·경고 코드는 `check` 출력에서 누구나 얻을 수 있는 해시이므로, 승인 판단은 전적으로 네 책임이다. 코드를 맞췄다는 것, Claude Code 권한 창에서 "Yes"를 받았다는 것은 WOD 승인이 아니다. 저장을 시도하기 위해 다른 형태의 명령(`./scripts/...`, `python3 -c`, `cp` 등)을 쓰지 않는다.
10. **스크립트 명령은 하나씩 독립적으로 실행한다.** 이 문서에 적힌 형태(`python3 scripts/<name>.py ...`) 그대로 Bash 호출 한 번에 명령 하나를 실행한다. `;`·`&&`로 잇거나, `echo "exit=$?"`를 붙이거나, `| python3 -c ...`·`| grep` 같은 파이프로 가공하지 않는다. 종료 코드와 값은 `--json` 출력의 `exit_code`·`result`에서 읽는다. 이런 복합 명령은 프로젝트 권한 규칙에 맞지 않아 거부되기 쉽고, 다시 실행하느라 시간이 든다. 파일 내용은 `cat` 대신 Read를 쓴다. 단, §5.1의 `> drafts/<date>.autofix.json` 저장처럼 이 문서가 지정한 리다이렉션은 그대로 쓴다.
11. **확인하지 않은 사실을 단정하지 않는다.** 최근 기록의 동작 개수, "모든 동작을 썼다/한 번도 안 썼다" 같은 전체 사용 여부, 등록 동작 수, 장비 보유 여부·수량, 패턴 겹침은 이번 턴에 실제로 실행한 스크립트 출력(`recent_wods.py`의 `movement_counts`·`records`, `check_equipment.py` 결과)이나 실제로 읽은 `data/` 파일에서 확인한 경우에만 단정한다. 확인하지 않았으면 "확인하지 않음"이라고 쓰거나, 근거가 된 출력 항목을 함께 적는다. 근거 없이 수를 세거나 일반화하지 않는다.

## 0. 요청 범위 판단

- 운동과 무관한 요청 → "WOD 요청이 아닙니다"라고만 답하고 끝낸다.
- 범위 밖(회원별 기록·PR 관리, TV 송출, 노션 연동, 개인 PT, 키즈 WOD) → 지원하지 않는다고 짧게 알린다. 요청에 WOD 부분이 있으면 그 부분만 진행한다.
- **수업 전체 구성(예: 60분)**을 요청하면 §7의 수업안을 함께 만든다. 복싱 드릴은 수업안의 한 블록으로만 다룬다(복싱 프로그램 설계는 하지 않음).
- 성인 WOD에는 항상 **Scale A/B/C**를 붙인다 (§3).

## 1. 데이터 읽기

매번 실제 파일을 읽는다 (내용을 기억에 의존하지 않는다).

1. `data/rules.md` — 시간 기준(본운동 최대 30분), 시간 표시 4상태, 작성 규칙, 기계 판독 설정
2. `data/equipment.json` — 보유 장비·수량 정확도(`exact`/`approx`/`unknown`), 공간 제약(층고, 월볼 타깃, 셔틀런)
3. `data/movements.json` — 등록 동작 id, `display`, `unit`, `equipment`, `space_tags`, `patterns`, `substitutes`, `rx_standard`
4. 최근 기록 — **WOD를 만들기 전에** 실행한다:
   ```bash
   python3 scripts/recent_wods.py --date <목표 날짜> --json
   ```
   - 승인·저장된 `wods/YYYY-MM-DD.json`만 읽는다. 기간은 목표 날짜 이전 7일(`rules.md` `recent_days`)이고, 목표 날짜 이후 기록은 제외된다.
   - `result.records[]`(날짜·형식·시간·동작·패턴), `pattern_counts`, `movement_counts`로 겹침을 판단한다. 기록이 없으면(`no_records`) "최근 기록 없음"으로 보고하고 계속 진행한다.
   - `movement_repeated`·`pattern_repeated`는 **참고 경고이지 금지가 아니다.** 반복을 택하면 이유를 보고한다.
   - `record_unreadable`·`record_incomplete`·`record_date_mismatch`·`unrecognized_file` 경고는 숨기지 않고 보고한다(손상된 기록은 최근 기록에서 빠진 상태).
   - `same_day_record_exists`: 목표 날짜에 이미 저장된 기록이 있다. 코치에게 먼저 알린다.
   - 초안을 만든 뒤 `--draft drafts/<date>.json`을 붙여 다시 실행하면 초안과 최근 기록의 겹침(`draft_movement_recent`, `draft_pattern_recent`)을 확인할 수 있다.
   - 코치가 말한 "오늘 WOD"(저장되지 않은 것)도 최근 기록으로 취급한다.

## 2. 요청 해석

| 항목 | 초안 필드 | 필수 | 없을 때 |
|------|-----------|------|---------|
| 날짜 | `date` (YYYY-MM-DD) | ✓ | "내일" 등 상대 표현은 오늘 날짜 기준으로 변환. 단서가 전혀 없으면 질문 |
| 예상 인원 | `expected_athletes` | ✓ | 질문. 코치가 "모름"이면 `null`로 진행(장비 수량 비교 생략 경고가 나옴) |
| 형식 | `format`: `AMRAP` / `EMOM` / `FOR_TIME` | | 네가 선택하고 이유를 한 줄로 밝힌다 |
| 시간 | AMRAP·EMOM `duration_min`, For Time `time_cap_min` + `rounds` | | 네가 정한다. 30분 이하. For Time은 TC·rounds 필수 |
| 본운동 상한 요청 | `max_workout_min` | | 코치가 "18분 이내"처럼 말하면 그 값. 스크립트가 30분과 둘 중 작은 값으로 검증 |
| 수업 시간 | 초안에 넣지 않음 → `check_class.py --total` | | 수업 전체안을 요청했을 때만 |
| 그룹 | `group`: `adult`(기본) / `kids` | | adult |
| 선호·회피 동작, 주간 플랜, 특이 회원 | 동작 선택과 `notes`에 반영 | | 없으면 최근 기록만으로 판단 |

- **빠진 필수 항목만 한 번에 묻는다.** 형식·시간·동작·스케일·수업 블록처럼 네가 정할 수 있는 것은 묻지 않는다.
- 코치가 30분을 넘는 본운동을 요청하면 만들지 않고 30분 이하로 조정하자고 제안한다.

## 3. 동작 선택과 스케일

- `data/movements.json`에 **등록된 id만** 쓴다. 미등록 동작을 요청받으면 등록된 비슷한 동작을 제안하고, 등록이 필요하면 코치에게 맡긴다.
- 절대 규칙 5의 동작은 제외한다. 보유 여부가 `null`인 장비가 필요한 동작은 가능하면 피하고, 쓰면 "확인 필요"로 보고한다.
- 각 동작의 **목적**(예: 심폐 유지, 당기기 근지구력, 하체 파워)과 `patterns`를 정하고, 최근 기록·오늘 WOD와 패턴이 겹치지 않게 고른다. 겹치면 이유를 보고한다.
- 반복 수와 라운드 구성은 코치 의도와 일반적인 WOD 구성으로 판단한다. 단, "이 구성이면 몇 분 걸린다"는 주장은 하지 않는다 (스크립트 추정만 인용).
- 무게를 쓰는 동작은 `movements[].weights`로 무게를 지정한다 (덤벨·케틀벨 kg, 바벨 lb — 데이터 키 단위).
- 파트너·교대 운영을 **코치가 정했을 때만** `concurrent_athletes`(동시에 하는 인원)를 지정한다. 1인당 장비가 2개면 `units_per_athlete: 2`.
- **Scale A/B/C (성인):** `scales`에 레벨별 동작 배열을 쓴다. Rx와 같은 순서·같은 목적을 유지한다.
  - A = Rx에 가까운 조정(반복 수·무게·높이 축소), B = 동작 난도 낮춤(`substitutes`의 Scale A/B 문맥 우선), C = 입문자용 가장 쉬운 버전.
  - 스케일 동작도 등록 id만 쓰고, check_equipment가 사용 가능 여부를 검사한다(수량은 인원 배분을 몰라 비교하지 않음 — 경고로 보고).
  - 무게·높이 같은 표기는 `load`, 무게 검사가 필요하면 `weights`.
- 특이 회원(예: 손목 통증)은 해당 동작의 `substitutes`에서 대체를 골라 `notes`에 적는다.

## 4. 초안 JSON 작성 → `drafts/<date>.candidate.json` → `draft_store.py commit`

1. Write 도구로 **후보** `drafts/<date>.candidate.json`에 쓴다 (`drafts/`는 git 제외 임시 폴더).
2. 반영한다:
   ```bash
   python3 scripts/draft_store.py commit <date> --json
   ```
   - `created` / `unchanged`: 그대로 진행. `result.approval_code`가 지금 초안의 초안 코드다.
   - exit 1 `draft_exists`: 같은 날짜 초안이 이미 있다. **덮어쓰지 말고 코치에게 묻는다:** 기존 초안을 계속 쓸지(`--keep-existing`), 새 버전을 만들지(`--new-version` — 기존 초안과 수정 이력은 `drafts/versions/<date>.v<N>.json`에 보존). 두 초안 코드(`existing_code`, `candidate_code`)를 함께 보여 준다.
   - 코치가 이번 대화에서 직접 수정을 요청한 경우(§8 "수정 요청")는 새 버전 생성 의사로 보고 `--new-version`을 쓴다.
3. 상태 확인: `python3 scripts/draft_store.py status <date>` (현재 초안 코드, 보존된 버전 목록).

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
  "max_workout_min": 18,
  "movements": [
    {"id": "toes_to_bar", "reps": 10},
    {"id": "box_jump", "reps": 15, "load": "24/20 in"},
    {"id": "shuttle_run", "reps": 20}
  ],
  "scales": {
    "A": [{"id": "toes_to_bar", "reps": 6}, {"id": "box_jump", "reps": 12, "load": "20 in"}, {"id": "shuttle_run", "reps": 16}],
    "B": [{"id": "hanging_knee_raise", "reps": 10}, {"id": "step_up", "reps": 12, "load": "20 in"}, {"id": "shuttle_run", "reps": 12}],
    "C": [{"id": "v_up", "reps": 8}, {"id": "step_up", "reps": 10, "load": "20 in"}, {"id": "shuttle_run", "reps": 8}]
  },
  "notes": ["손목 통증 회원: Toes-to-Bar → V-ups"]
}
```

- `unit`이 `m`인 동작(Row)은 `reps`가 미터다.
- 선택 필드: `max_workout_min`, `scales`, `movements[].load`(표기용 문자열), `weights`, `units_per_athlete`, `concurrent_athletes`. 상세는 `docs/PLAN.md` §4.3.

## 5. 검증 + 자동 수정 (`autofix.py`)

```bash
python3 scripts/autofix.py drafts/<date>.json --out drafts/<date>.json --json
```

- 내부에서 `simulate`와 `check_equipment`를 실행하고, 고칠 수 있는 문제를 **한 번에 하나씩, 최대 3회** 고친 뒤 매번 두 검증을 다시 실행한다. 수정된 초안은 `--out` 경로에 쓴다(`wods/`는 거부).
- 자동 수정 대상: 사용 불가 동작(미보유·금지·층고·없는 무게), 시간 상한 초과(`workout_too_long` 30분 / `workout_over_request` 코치 요청 상한), 장비 수량 부족(`short` / `possibly_short`).
- 대체 동작은 등록 `substitutes` → 같은 패턴 → 패턴 겹침 순으로 찾고, **후보를 따로 검사해 장비가 충분한 것만** 쓴다. 정확한 수량으로 충분한 후보가 추정 수량 후보보다 우선. 단위가 다르면(Row m → Shuttle rep) 1단위 거리가 데이터에 있을 때만 거리로 환산한다.
- **운영 방식(파트너 교대·시차 출발·스테이션 분산)은 자동 적용하지 않는다.** 동작 변경으로 못 고치면 `operation_options`에 방식별 동시 사용 인원 계산(근거)을 붙여 돌려준다. 스테이션별 시작 위치만 바꾸는 것은 해결로 보지 않는다.

출력: 공통 형식 + `result.status`

| status | exit | 뜻 | 할 일 |
|--------|------|----|-------|
| `passed` | 0 | 두 검증 exit 0, 수량 부족 없음 (자동 수정 있었을 수 있음) | 보고 |
| `needs_coach` | 1 | 자동으로 고칠 방법이 없는 문제가 남음 | `errors[].unresolved_reason`·`candidates`·`operation_options`를 그대로 보고하고 코치 판단 요청 |
| `unresolved` | 1 | 3회 수정 후에도 문제 남음 | 남은 문제와 3회의 수정 내역을 보고하고 코치 판단 요청 |
| `input_error` | 2 | 초안 구조 오류 — 검증 안 됨 | 네 초안 작성 실수. `errors`의 필드 경로를 보고 고친 뒤 다시 실행 |

- `unregistered_movement`, `duration_missing`, `time_cap_missing`, `rounds_missing`, `unsupported_format`은 자동 수정하지 않는다. 네가 의도를 판단해 초안을 고치고 autofix를 다시 실행한다(이것도 3회 안에서 센다). 의도를 판단할 수 없으면 코치에게 묻는다.
- `warnings`의 `scaling_missing`이 있으면 `scales`를 채워 다시 실행한다.
- 자동 수정이 코치가 직접 요청한 동작을 바꿨다면 특히 분명히 알린다.

결과 인용 위치:
- 시간: `result.final_reports.simulate.result.workout_time` (`minutes`, `max_minutes`, `limit_source`), `...estimate` (`status`, `reason`, `missing[]`, 추정이면 `round_sec`·`expected_rounds`·`breakdown[].text`·`notes`)
- 장비: `result.final_reports.check_equipment.result.movements[].equipment[]`, 스케일은 `...result.scales`
- 수정 내역: `result.changes[]` (`reason`, `reps_note`, `note`, `candidates`), 검증 이력: `result.history[]`

필요하면 확인용으로 `simulate.py` / `check_equipment.py`를 최종 초안에 직접 실행해도 된다(같은 결과가 나와야 한다).

### 5.1 최종 출력 생성 (`render_wod.py`)

autofix 결과를 파일로 남긴 뒤, 최종 초안으로 출력과 검증 요약을 만든다.

```bash
python3 scripts/autofix.py drafts/<date>.json --out drafts/<date>.json --json > drafts/<date>.autofix.json
python3 scripts/render_wod.py drafts/<date>.json --autofix-report drafts/<date>.autofix.json \
    [수업안이면 --total 60 --block ... --interval boxing=4x3/1 --require boxing] --json
```

- `result.whiteboard`: 화이트보드 텍스트(간결 형식). **Rx는 한 번만, 동작 한 줄씩** 쓴다. **Scale A/B/C는 레벨마다 한 줄**로 `A 10 Shuttle Runs / 8 T2B / 10 Box Jumps (20")`처럼 모든 동작을 ` / `로 잇는다. 모든 동작에 횟수·거리·load·무게·월볼 타깃이 붙는다. `N in` load는 `N"`로 표기한다. 약어는 `data/movements.json`의 `whiteboard.abbr`에 등록된 것만 스케일 줄에 쓴다(현재 T2B). 거리 단위 rep 동작은 끝에 각주(`*1 Shuttle Run = 7.5m x 2`)가 붙는다. 형식 예:
  ```
  WOD - AMRAP 15

  13 Shuttle Runs
  12 Toes-to-Bar
  12 Box Jumps (24/20")

  Scale

  A 10 Shuttle Runs / 8 T2B / 10 Box Jumps (20")
  B 10 Shuttle Runs / 10 Hanging Knee Raises / 12 Step-ups (20")
  C 7 Shuttle Runs / 10 V-ups / 10 Step-ups (20")

  *1 Shuttle Run = 7.5m x 2
  ```
  스케일 동작 수가 Rx와 다르거나 스케일이 없으면 오류(`scale_movement_count_mismatch` / `scale_missing`)이고, 빠진 동작을 채우지 않는다. 스케일 한 줄을 다시 나눠 동작 수가 초안과 다르면 `render_scale_incomplete` 오류다 → 네가 초안 `scales`를 고치고 autofix부터 다시.
- `result.checks[]`: `{item, status, source, detail}`. status = `passed` / `passed_with_warnings` / `estimated` / `failed` / `shortage` / `not_checked` / `not_estimable`. 보고서의 "검증 요약"은 이 목록만으로 쓴다.
- `result.coach_review[]`: 자동 검증하지 않는 항목(운동 자극, 스케일 난도, 준비운동·마무리 내용, 복싱 드릴 품질, 거리 환산 적절성). "코치 확인 필요"로 따로 보여 준다. 여기 항목을 passed라고 쓰지 않는다.
- `result.autofix`: 수정 전/후 상태(`before`/`after`의 exit 코드·문제)와 `changes`. `--out`을 쓰면 autofix가 수정 이력 원장 `drafts/<date>.history.json`에 실행을 **추가**하므로, 이미 고친 초안을 다시 검증해도 `before`는 최초 수정 전 상태, `changes`는 누적 수정 내역, `cumulative`는 실행 수·누적 수정 횟수다. `attempts_used`는 이번 실행분이다. 보고서의 final_draft가 지금 초안과 다르면 `autofix_report_mismatch` 경고가 나오고 전후 비교가 빠진다 → autofix를 다시 실행. 실행 사이에 초안이 손으로 바뀌었으면 `autofix_history_manual_edit` 경고가 나온다.
- `result.class_blocks`: 수업 시간표와 복싱 인터벌 타임라인.
- 응답에 옮긴 WOD 텍스트가 의심되면 `--check-text <파일>`로 모든 줄이 들어 있는지 검사할 수 있다.
- `drafts/<date>.autofix.json`은 임시 파일이다(drafts/는 git 제외).

## 6. 코치에게 보고 (그리고 멈춘다)

아래 형식으로 한국어로 보고한다. WOD 본문은 영어(성인), 화이트보드에 옮길 수 있는 plain text.

````
## WOD 초안 — <date> <class_time> / <expected_athletes>명

```
(render_wod.py result.whiteboard를 그대로 — 손으로 쓰거나 줄이지 않는다)
```

### 동작 목적
(동작별 목적·패턴 한 줄씩 — 네 판단이며 자동 검증 대상이 아님)

### 자동 수정 — 수정 전 / 수정 내용 / 수정 후
- 수정 전: (result.autofix.before — exit 코드, 문제 코드)
- 수정 내용: (changes[]마다 reason, reps_note, 스케일 반영. 없으면 "없음")
- 수정 후: (result.autofix.after) — autofix status, 누적 수정 n회(실행 k회), 이번 실행 수정 n/3회, 검증 실행 m회

### 검증 요약 (코드로 검사한 항목)
(result.checks[]를 한 항목당 한 줄: status · item — detail. detail을 줄이지 말고 그대로)

### 남은 경고
(warnings 하나당 한 줄. 미해결 부족이 있으면 operation_options 근거를 그대로 — 코치가 선택)

### 코치 확인 필요 (자동 검증하지 않음)
(result.coach_review[] 그대로 + 이번 요청 특유의 확인 사항, 예: 복싱 장비 보유 여부)

### 최근 기록
(recent_wods.py 결과: 최근 7일 기록·패턴과 겹침 여부, 반복 경고, 손상 기록 경고. 기록 없으면 "최근 기록 없음")

### 특이 회원
(notes)

### 저장 전 확인 (save_wod.py check)
- 초안 코드: (result.draft_code — 보여 준 초안과 저장할 초안이 같은지 확인하는 무결성 코드)
- 남은 경고 n건 · 경고 코드: (result.warnings_code, 없으면 "경고 없음")
- 같은 날짜 저장 기록: (result.existing_record — 있으면 경로와 기록 코드, 없으면 "없음")
- 저장 가능 여부: (exit 0 = 가능 / exit 1 = 불가 — errors 그대로)

---
초안은 `drafts/<date>.json`에 있습니다 (초안 코드 <code>, 아직 저장 전).
위 WOD와 남은 경고를 검토하신 뒤 이 초안으로 확정해 저장할까요? **"저장"** 또는 **"승인"**이라고 답해 주세요. 남은 경고가 있으면 그 경고를 수용한다는 뜻도 함께 말씀해 주세요. 수정할 점이 있으면 말씀해 주세요.
````

보고 직전에 저장 가능 여부를 확인한다 (파일을 쓰지 않음):
```bash
python3 scripts/save_wod.py check drafts/<date>.json --json
```

- 시간·장비 섹션의 숫자는 모두 스크립트 JSON에서 온 것이어야 한다.
- 월볼 타깃 높이·셔틀런 각주는 render_wod가 화이트보드에 자동으로 붙인다.
- 응답 문장은 한 항목에 한 문장씩 끝까지 쓴다. 긴 목록을 한 줄에 `/`로 잇지 않는다(터미널에서 줄바꿈·잘림이 생기기 쉽다). 예외: `whiteboard` 블록 안의 스케일 한 줄은 스크립트 출력 그대로 둔다.
- 수업 전체안을 요청받았으면 §7의 수업안을 WOD 보고 앞에 붙인다.
- **보고 후 멈추고 코치 답을 기다린다.** 승인 없이 다음 단계로 가지 않는다.

## 7. 수업 전체안 (요청했을 때만)

수업안은 **응답에만** 표시하고 파일로 저장하지 않는다. WOD 초안 JSON에 수업 블록을 넣지 않는다.

1. 블록을 정한다: `warmup`(준비운동), `boxing`(복싱 핵심 드릴 — 요청 시), `briefing`(설명), `wod`, `cooldown`(마무리). 필요하면 `strength`/`accessory`/`transition`.
   - **WOD 블록 ≥ 본운동 시간.** 본운동(AMRAP/EMOM 설정 시간, For Time TC)과 별개로 세팅·설명 여유를 둘지 정한다.
   - 블록 분 배분은 네가 정하지만 **합계는 스크립트로 확인**한다.
2. 검증:
   ```bash
   python3 scripts/check_class.py --total 60 --block warmup=12 --block boxing=15 --block briefing=5 \
       --block wod=18 --block cooldown=10 --require boxing --interval boxing=4x3/1 --wod drafts/<date>.json --json
   ```
   - **복싱 블록은 항상 `--interval boxing=라운드x운동분/휴식분`을 준다.** 예: `4x3/1` = 3분 × 4라운드 + 휴식 1분 × 3회 = 15분. 마지막 라운드 뒤 휴식은 넣지 않는다(넣으려면 끝에 `+`, 예: `4x3/1+` = 16분). 인터벌 합계 ≠ 블록 시간이면 `interval_total_mismatch`로 실패.
   - exit 1이면 `errors`(`class_total_mismatch`, `class_block_missing`, `wod_block_too_short`, `interval_total_mismatch`, 본운동 시간 오류)에 맞춰 분 배분을 고치고 다시 실행. 같은 인자를 `render_wod.py`에도 넘겨 시간표·복싱 라운드 타임라인(`result.class_blocks`)을 인용한다.
3. 블록 내용:
   - 준비운동: 그날 WOD 동작 패턴을 준비시키는 동작.
   - 복싱 드릴: **장비 데이터에 글러브·미트·샌드백이 없다.** 장비 없이 하는 섀도복싱·풋워크·방어 드릴로 구성하고, "복싱 장비 보유 여부 확인 필요"를 적는다. 등록 동작이 아니므로 장비 검증 대상이 아님을 밝힌다. 라운드별 드릴 내용은 `--interval`의 라운드 수와 맞춘다(라운드 4개면 드릴 4개).
   - 마무리: 쿨다운·스트레칭.
4. 표시 예 (시간 숫자는 `result.class_blocks`에서 그대로):
   ```
   0:00–0:12  Warm-up (12)
   0:12–0:27  Boxing Drills (15) — 3분 × 4라운드 + 휴식 1분 × 3회 = 15분
              R1 0:12–0:15  스탠스·풋워크
              R2 0:16–0:19  잽-크로스
              R3 0:20–0:23  슬립·롤 + 카운터
              R4 0:24–0:27  콤비네이션
   0:27–0:32  Briefing (5)
   0:32–0:50  WOD block (18) — AMRAP 15
   0:50–1:00  Cool-down (10)
   ```

## 8. 코치 응답 처리

- **수정 요청** ("T2B 빼줘", "15분으로") → §3부터 다시. 후보 작성 → `draft_store.py commit <date> --new-version`(이전 버전 보존) → autofix 재실행 → 재보고. 초안 코드가 바뀌므로 이전 승인은 효력이 없다.
- **운영 방식 선택** ("파트너로 하자") → 해당 동작에 `concurrent_athletes`를 반영하고 autofix 재실행 (스크립트가 근거 있는 수량으로 다시 비교).
- **애매한 반응** ("좋네", "괜찮은 듯", "음") → 승인으로 보지 않는다. "저장할까요?"라고 다시 묻는다.
- **명시적 승인** ("저장", "승인", "확정", "이대로 저장해"): 아래를 모두 만족할 때만 승인으로 본다.
  - 코치의 **바로 직전 보고(최종 화이트보드·남은 경고·초안 코드를 보여 준 보고)에 대한 답**이다. 다른 날짜·다른 버전·가정형("저장해도 될까?")·조건부("T2B만 빼면 저장")는 승인이 아니다.
  - 그 보고 이후 초안이 바뀌지 않았다. 바뀌었으면 다시 보고하고 다시 승인받는다.
  - 남은 경고가 있었다면 코치가 그 경고를 보고 수용한다는 뜻이 있다. 없으면 경고를 다시 짚고 확인을 받는다.

  절차:
  1. `python3 scripts/save_wod.py check drafts/<date>.json --json`을 다시 실행한다. `draft_code`나 `warnings_code`가 보고 때와 다르면 저장하지 말고 바뀐 내용을 재보고한다. exit 1이면 errors를 그대로 보고하고 저장하지 않는다.
  2. 저장 (한 줄로 실행):
     ```bash
     python3 scripts/save_wod.py save drafts/<date>.json --draft-code <보고한 초안 코드> --coach-message "<코치 승인 발화 원문>" [--accept-warnings <보고한 경고 코드>] --json
     ```
     - `--draft-code`·`--accept-warnings`는 **코치에게 보고한 값**만 쓴다. 보고하지 않은 새 값을 넣지 않는다.
     - `--accept-warnings`는 코치가 남은 경고를 수용했을 때만 붙인다. 네가 대신 수용하지 않는다.
     - `--coach-message`에는 코치 발화를 그대로 옮긴다. 지어내지 않는다 (스크립트는 이 값을 검증하지 않는다).
     - 이 명령은 프로젝트 설정에서 `ask`라서 권한 창이 뜬다. 거부되면 저장하지 않은 것이다. 권한 허가는 명령 실행 허가일 뿐 WOD 승인이 아니다.
  3. **결과는 실제 출력으로만 보고한다.** exit 0이고 `result.saved`가 true일 때만 "저장됨"이라고 쓰고 `saved_path`, `approved_at`, `record_code`를 인용한다. 그 밖(exit 1·2, 권한 거부, 실행 안 함)은 "저장하지 않았습니다"와 errors를 그대로 보고한다.
  4. `record_exists`(같은 날짜 기록 있음): 덮어쓰지 않는다. 코치에게 기존 기록 교체 여부를 **별도로** 묻고, 명시적으로 교체를 지시받은 경우에만 `--replace-existing <기록 코드>`를 붙여 다시 실행한다(기존 기록은 `wods/archive/`에 보존).
  5. `draft_code_mismatch`: 코치에게 보여 준 뒤 초안이 바뀌었다. 바뀐 초안을 다시 보고하고 새로 승인받는다.
