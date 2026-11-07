# PROGRESS — 진행 상황

> 모든 에이전트는 작업 시작 전 이 파일을 읽고, 작업 후 갱신한다.
> 상태 표기: ✅ 완료(코드·테스트로 확인됨) / 🚧 진행 중 / ⬜ 미착수

## 현재 단계: Phase 4 완료 (2026-11-08) — 다음: 코치 확인 항목·Phase 5 범위 결정

Phase 순서 변경(2026-11-07, 사용자 지시): Skill을 먼저 구현(Phase 3)하고, `recent_wods.py`·`save_wod.py`는 Phase 4로 미뤘다.
`wod-planner` Skill이 새 Claude Code 세션에서 발견되고, 자연어 요청 1건으로 초안 작성 → 두 검증 스크립트 → 보고 → 승인 대기까지 동작함을 확인했다.

## 단계별 상태

| Phase | 내용 | 상태 |
|-------|------|------|
| 0 | 설계 문서 (AGENTS.md, CLAUDE.md, docs/PLAN.md, docs/PROGRESS.md, README.md) | ✅ |
| 1 | 데이터 파일 (`data/equipment.json`, `data/movements.json`, `data/rules.md`) | ✅ 코치 확정 값 입력, 파싱·참조 검증 완료 (미확인 수량은 경고 대상으로 기록) |
| 2 | `scripts/simulate.py`, `scripts/check_equipment.py` + 테스트 | ✅ 테스트 67개 통과, 실제 데이터로 예시 WOD 실행 확인 |
| 3 | `.claude/skills/wod-planner/SKILL.md` + `.claude/settings.json` | ✅ Skill 발견·자연어 1건 E2E 확인 (시나리오 S1). S2–S6 미실행 |
| 3.5 | `scripts/autofix.py`, `scripts/check_class.py`, 스케일 A/B/C·`max_workout_min` 검증 + Skill 절차 갱신 (사용자 지시로 Post-MVP 일부를 앞당김) | ✅ 테스트 108개 통과(기존 67 + 신규 41), 실제 data/로 자동 수정 1건 확인. 새 Skill 절차 E2E는 미실행 |
| 3.6 | `check_class.py --interval`(복싱 라운드·휴식 시간), `scripts/render_wod.py`(초안 → 화이트보드·검증 요약·코치 확인 항목), autofix `final_text` | ✅ 테스트 131개 통과(기존 108 + 신규 23), 실제 초안 출력 완전성 테스트 포함. 실행 권한은 settings.json·Skill `allowed-tools` 양쪽에 반영됨(사용자 추가) |
| 3.7 | 화이트보드 간결 형식(Rx 1회, Scale A/B/C 레벨별 한 줄, 등록 약어만, 셔틀런 각주) + 한 줄 스케일 완전성 검사 | ✅ 테스트 138개 통과(기존 131 + 신규 7) |
| 4 | `save_wod.py`(승인 후 저장), `recent_wods.py`(최근 7일), `draft_store.py`(초안 보호), autofix 이력 원장 + 테스트 + Skill·문서 | ✅ 테스트 173개 통과(기존 138 + 신규 35). PLAN §8.2 시나리오 S1–S6 모두 PASS, 사용자 지정 통합 E2E 6개 PASS (2026-11-08, 샌드박스·헤드리스). 아래 "Phase 4 E2E" 참고 |
| 5 | Post-MVP (키즈, 장비 회전, 패턴 판정, 결과 보정) | ⬜ |

## 코치 확정 사항 (2026-11-07)
- **시간:** 그룹 수업은 일반적으로 60분. **WOD 본운동은 최대 30분**이며 웜업·설명·쿨다운은 포함하지 않는다.
  AMRAP/EMOM은 설정 시간, For Time은 TC 기준. 웜업 7 / 설명 4 / 쿨다운 5분은 기획서 예시일 뿐 규칙이 아니다.
- **MVP 시간 범위:** 본운동 30분 이하 검증. 60분 전체 수업 구성은 Post-MVP.
- **동작 시간:** 고정값을 쓰지 않는다. 회원 수준·반복 수·피로도·전환 시간에 따른 추정 범위로 설계하고,
  데이터가 없으면 "추정 불가"로 표시한다. 시간 데이터 없이도 WOD 생성은 가능해야 한다.
- **장비:** 로잉머신 5대, 점프 박스 9개(20/24 in), 풀업바 약 8명, 셔틀런 1rep = 7.5m 왕복 = 15m·약 8명 동시,
  덤벨 1–20kg, 바벨 45lb×9·35lb×5, 원판 10–45lb 각 약 10장·55lb×2, 월볼 약 20개, 줄넘기·케틀벨 보유.
- **공간:** 층고가 낮아 링 머슬업 등 높은 공간이 필요한 동작은 제한(링 자체는 보유). 월볼 타깃은 벽면 약 2.3m, 표준 높이 타깃 사용 불가. 월볼은 성인 수업 사용 가능.
- **운영:** 셔틀런 6명 이상 2레인, 2인 1조 교대는 고정 규칙이 아니다(WOD 구성에 따라 결정, 에이전트는 선택지만 제안).
- **미확인 장비:** 수량·규격을 추측하지 않는다.

## Phase 2 구현 결과
- **`scripts/common.py`**: data/ 로딩·무결성 검사(참조, 수량 형식, 근거 없는 시간값 거부), 초안 구조 검증(오류 전부 수집), 공통 CLI(`--data-dir`, `--json`), 종료 코드 0/1/2, 공통 JSON 형식.
- **`scripts/check_equipment.py`**: 미등록·미보유·금지·층고 제한·보유하지 않은 무게 → 오류(대체 제안). 보유 미확인·추정/미확인 수량·무게 미지정·월볼 타깃 → 경고. 인원 대비 수량 부족은 경고 + 운영 선택지(실행 불가 판정 안 함).
- **`scripts/simulate.py`**: ① 본운동 시간 검증(AMRAP/EMOM `duration_min`, For Time `time_cap_min`+`rounds` 필수, 30분 상한) ② 추정(모든 동작 시간 범위 + 전환 범위가 있을 때만, 범위·근거 출력). 없으면 "추정 불가" + 누락 목록(종료 코드 0).
- **테스트**: `tests/test_common.py`, `tests/test_check_equipment.py`, `tests/test_simulate.py`. 가상 시간 값은 `tests/fixtures/data/`에만 있음. 실제 `data/`는 읽기만 하며, 시간 값이 null로 유지되는지 테스트로 확인.
- 실행 예시: `python3 scripts/check_equipment.py tests/fixtures/drafts/plan_example_amrap.json`, `python3 scripts/simulate.py tests/fixtures/drafts/plan_example_amrap.json`

### 알려진 한계 (Phase 2)
- 실제 데이터에 동작 시간·전환 시간이 없어 실제 WOD는 항상 "추정 불가"다 (의도된 동작, 코치 데이터 필요).
- EMOM은 설정 시간 검증만 한다. 분당 작업량 추정은 Post-MVP.
- 필요 수량은 "전원 동시 출발" 최악 가정이다. 실제 AMRAP은 곧 분산되므로 부족 경고가 과하게 나올 수 있다. `concurrent_athletes`로 조정 가능.
- 무게별 수량은 지정 무게들의 합계로만 비교한다. 남녀·스케일별 인원 배분은 모른다.
- 바벨 무게 → 원판 조합·원판 수량 검증은 하지 않는다.
- 셔틀런 공간 수용 인원은 `space.<동작 id>`가 동작 id와 같을 때만 연결된다(현재 `shuttle_run`). 데이터 구조는 바꾸지 않았다.
- 추정 모델은 선형(reps × 1단위 시간 + 전환)이며, 반복 수가 많을 때 세트 분할 효과는 없다.
- 박스 높이(20/24 in) 등 규격과 `load` 문자열은 검증하지 않는다.

## Phase 3 구현 결과 (Skill)
- **`.claude/skills/wod-planner/SKILL.md`**: frontmatter(`name`, `description`, `allowed-tools`). 절차 = 범위 판단 → data/·최근 기록 읽기 → 요청 해석(필수: 날짜·예상 인원만 질문) → 등록 동작만으로 선택 → `drafts/<date>.json` 작성 → 두 스크립트 `--json` 실행·`exit_code`별 처리(오류 시 최대 3회 수정·재검증) → 보고 템플릿 → 승인 대기.
- **`.claude/settings.json`**: 검증 스크립트·단위 테스트 실행, `drafts/**` 편집 허용 / `wods/**` 직접 편집 deny.
- 저장: `save_wod.py`가 없으므로 승인을 받아도 저장하지 않고 "저장 기능 미구현"을 알린다. `wods/`에 쓰는 다른 경로는 Skill에서 금지.

### Phase 3 테스트 기록 (2026-11-07)
- **Skill 발견:** 새 헤드리스 세션(`claude -p`, Claude Code 2.1.319) 초기화 정보의 skills 목록에 `wod-planner` 포함, 슬래시 명령 `/wod-planner` 등록.
- **E2E (시나리오 S1 유사):** 요청 "내일 18:30 수업 예상 10명이야. 오늘은 로잉 250m + 버피 10개 5라운드 했어. 내일은 짐내스틱 위주로 WOD 짜줘. 손목 아픈 회원 1명 있어."
  - Skill 자동 호출 → data/ 읽기 → `drafts/2026-11-08.json` 작성(AMRAP 12: 10 T2B / 15 Box Jumps) → `simulate.py`·`check_equipment.py` 실행(둘 다 exit 0)
  - 보고: 본운동 12분 ≤ 30분 검증됨 / 완주 가능성 추정 불가(T2B·Box Jumps 시간 데이터, 전환 시간 누락) / 풀업바 10명 vs 약 8명 부족 가능성, 박스 10 vs 9 부족 + 운영 선택지 / 오늘 WOD(cardio·push)와 패턴 비겹침 / 손목 회원 T2B → V-ups / 저장 기능 미구현 안내 후 승인 질문에서 멈춤
  - 숫자는 모두 스크립트 결과와 일치, 지어낸 시간 없음. 권한 거부 0건.
  - `wods/` 디렉터리 생성 안 됨 (확인).
- **미검증:** `wods/**` deny 규칙의 실제 차단 동작 — 의도적으로 쓰기를 시도하는 테스트가 자동 모드 분류기에 막혀 실행하지 못함. 코치가 직접 확인 가능.

### 알려진 한계 (Phase 3)
- 등록된 짐내스틱 동작이 4개(T2B, Hanging Knee Raise, V-up, Box Jump 포함)뿐이라 E2E에서 2동작 WOD가 나왔다. 동작 추가(코치 확인 C3)가 필요하다.
- 최근 기록은 `wods/*.txt`를 LLM이 직접 읽어 판단한다(결정적 스크립트 아님). Phase 4 `recent_wods.py`로 대체 예정.
- 시나리오 S2–S6(링 머슬업 요청, 30분 초과 요청, 주간 플랜 없음, 무관한 요청, 애매한 승인)은 아직 실행하지 않았다.
- E2E는 헤드리스 1회 실행 기록이다. LLM 출력이라 실행마다 동작 선택·문장이 달라질 수 있다.

## Phase 3.5 구현 결과 (2026-11-07)
사용자 지시: 자동 수정·재검증 루프, 장비 부족 해결, 성인 스케일 A/B/C, 60분 수업안(복싱 드릴 포함). 범위 변경은 AGENTS.md §1·§3.7, PLAN §1.6·§2·§5·§7, rules.md §1·§8에 반영.

- **`scripts/autofix.py`**: simulate + check_equipment 실행 → 문제 1개 수정 → 재검증, 최대 3회(`--max-attempts`). 결과 `status` = passed / needs_coach / unresolved / input_error, `changes[]`(무엇을 왜, 반복 수 환산 근거, 스케일 반영), `history[]`(매 검증의 두 스크립트 exit 코드·문제), 남은 문제마다 `unresolved_reason`·후보 검토(`candidates`)·운영 선택지 근거(`operation_options`). `--out`으로 수정본 저장(`wods/` 경로 거부).
  - 대체 후보: 등록 substitutes → 같은 패턴 집합 → 패턴 겹침. 후보를 단독으로 check_equipment에 넣어 오류 없고 장비 충분인 것만, 정확 수량 > 추정 수량. 수량 미확인·부족 가능성·무게 미지정·보유 미확인 후보 제외.
  - 단위가 다르면 1단위 거리(m 동작 = 1m, `space.<id>.rep_distance_m`) 근거가 있을 때만 거리 환산.
  - 운영 방식은 자동 적용하지 않음. 파트너 교대 동시 인원, 히트 수·히트당 인원·WOD 블록 필요 시간을 계산해 근거로 제시. 시작 위치 분산은 해결로 보지 않음(`fits: null`).
  - Rx 동작을 바꾸면 스케일의 같은 동작도 함께 바꾼다(스케일은 수량 비교를 안 하므로 그대로 두면 부족한 장비를 계속 씀).
- **`scripts/simulate.py`**: 초안 `max_workout_min`(코치 요청 상한) 지원 — 30분과 둘 중 작은 값 적용, 초과 시 `workout_over_request`. 시간 오류에 `field` 추가.
- **`scripts/check_equipment.py`**: 동작별 검사를 함수로 분리. 모든 issue에 `index`(스케일이면 `scale`) 추가. `scales` 동작의 사용 가능 여부 검사(수량 비교 안 함, `scale_quantity_not_compared` 경고). 운영 선택지 문구에 "시작 동작 분산은 동시 사용 감소를 보장하지 않음" 명시.
- **`scripts/common.py`**: 초안 선택 필드 `max_workout_min`, `scales`(A/B/C) 구조 검증.
- **`scripts/check_class.py`**: `--total`, `--block KIND=분[:이름]`, `--require`, `--wod`. 블록 합계 = 수업 시간, 필수 블록(warmup·wod·cooldown + 요청), WOD 블록 ≥ 본운동, 본운동 시간 검증. 수업안은 WOD JSON에 넣지 않음.
- **Skill**: §5를 autofix 중심으로, §3에 동작 목적·스케일 작성 규칙, §7에 수업안 절차(복싱 장비 미등록 → 장비 없는 드릴 + 확인 필요) 추가. `allowed-tools`에 두 스크립트 추가.
- **테스트**: `tests/test_autofix.py`(24), `tests/test_check_class.py`(9), test_check_equipment +4(스케일·index), test_simulate +4(요청 상한).

### 실제 자동 수정 사례 (실제 data/, `drafts/2026-11-09.json`)
- 요청: 11/9 성인 6명, WOD 18분 이내, 60분 수업 + 복싱 드릴. 초안 AMRAP 15: Row 250m / 12 T2B / 15 Box Jumps + Scale A/B/C.
- 검증 #0: 두 스크립트 exit 0, 문제 `short`(로잉 6 / 5대 정확) → 수정 1: Row → Shuttle Runs 17회(250m ÷ 15m = 16.67 → 17, 같은 cardio 패턴, 셔틀런 약 8명이라 추정 수량으로 충분). 스케일 A/B Row 200 → 13회, C Row 150 → 10회.
- 검증 #1: 두 스크립트 exit 0, 수량 부족 없음 → passed. 남은 경고: 셔틀런·풀업바 추정 수량, 스케일 수량 비교 안 함.
- check_class: 12/15/5/18/10 = 60분, WOD 블록 18 ≥ 본운동 15, 상한 18분(코치 요청) → 통과.

### 알려진 한계 (Phase 3.5)
- `.claude/settings.json`의 `autofix.py`·`check_class.py` 실행 허용은 에이전트가 추가하지 못했고(분류기 거부), 이후 작업 트리에 반영된 상태로 확인됨(2026-11-07). Skill `allowed-tools`에는 추가됨.
- 새 Skill 절차(autofix·수업안)를 새 Claude Code 세션에서 E2E로 실행하지 않았다. 스크립트 단위 테스트와 CLI 실행만 확인.
- 수정은 한 번에 1개라 문제가 4개 이상이면 3회 후 `unresolved`로 코치에게 돌아간다(의도된 동작).
- 거리 환산은 거리만 맞춘다. 셔틀런의 방향 전환 부담 등 자극 차이는 반영하지 않는다. 짧은 거리는 1회로 반올림될 수 있다(예: 20m → 1회).
- 스케일별 인원 배분을 몰라 스케일 동작의 장비 수량은 비교하지 않는다. Rx와 스케일이 같은 장비를 나눠 쓰는 총량도 검증하지 않는다.
- 필요 수량은 여전히 "전원 동시 출발" 최악 가정이다. 히트·파트너는 계산 근거만 제시하고 코치가 정한다.
- 수업안 내용(준비운동·복싱 드릴·마무리)은 LLM이 쓰며 검증 대상은 시간 합계뿐이다. 복싱 장비(글러브·미트·샌드백)는 데이터에 없다.
- 스케일 A/B/C의 적절성(난도 단계)은 스크립트가 판단하지 않는다.

## Phase 3.6 구현 결과 (2026-11-07)
- **출력 누락 원인 확인:** 사용자가 받은 `10 Shuttle Runs / 10 V-ups / 10`은 JSON 문제가 아니었다. `drafts/2026-11-09.json`의 Scale C는 3동작이 모두 있었고, 직전 에이전트 응답 원문에도 `10 Step-ups (20 in)`까지 있었다. 따라서 터미널 표시·복사 단계에서 잘린 것으로 보인다(재현 확인은 못 함). 다만 스케일 줄을 LLM이 손으로 `/`로 이어 쓰던 구조 자체가 위험하므로, 출력을 코드 생성으로 바꿨다.
- **`scripts/check_class.py`:** `--interval KIND=라운드x운동분[/휴식분][+]`. 합계 = 운동 × 라운드 + 휴식 × (라운드 − 1), `+`일 때만 마지막 뒤 휴식 추가. 블록 시간과 다르면 `interval_total_mismatch`(exit 1). 라운드·휴식 타임라인 출력. 복싱 블록에 인터벌이 없으면 `boxing_intervals_unspecified` 경고(기존 입력 호환). 소수 분 허용. 인자 파싱을 `add_class_arguments`·`class_report_from_args`로 분리.
- **`scripts/render_wod.py`:** 초안 → 화이트보드(헤더, Rx, Scale A/B/C 각 동작 한 줄: 횟수·m·display·load·무게 단위·월볼 타깃). 스케일 동작 수 ≠ Rx, 성인인데 스케일 없음, 미등록 동작 → 오류(보충하지 않음). 생성 텍스트를 다시 줄 단위로 검사. `checks[]`는 simulate·check_equipment·check_class를 이번 실행에서 돌린 결과로만 만들고, 자동 검증하지 않는 항목은 `coach_review[]`로 분리. `--autofix-report`의 final_draft가 현재 초안과 다르면 전후 비교 생략 + 경고. `--check-text`로 옮겨 쓴 텍스트의 빠진 줄 검출.
- **`scripts/autofix.py`:** 결과에 `final_text`(최종 초안에서 생성한 화이트보드) 추가.
- **`scripts/common.py`:** `render_issues`의 실패 문구를 호출자가 지정(수업안은 "이대로는 수업안을 쓸 수 없음").
- **Skill:** 규칙 8(화이트보드 손으로 쓰지 않음), §5.1 render_wod 절차, 보고 템플릿(수정 전/내용/후, 검증 요약, 코치 확인 분리), §7 `--interval` 필수·라운드별 드릴 줄 단위 표시.
- **테스트:** test_check_class +9(인터벌 일치·마지막 휴식·불일치·소수·미지정 경고·CLI), `tests/test_render_wod.py` 14(줄 형식, 스케일 누락 미보충, 잘린 텍스트 검출, autofix 후 출력 일치, 오래된 autofix 보고서, 검증 요약, CLI, 실제 초안 — drafts/ 파일이 없으면 skip).

### 알려진 한계 (Phase 3.6)
- `render_wod.py` 실행 권한은 에이전트가 추가하지 못했고(분류기 거부), 사용자가 `.claude/settings.json`과 Skill `allowed-tools`에 직접 추가했다(2026-11-07 확인).
- 실제 초안 테스트(`RealDraftTest`)는 git 제외 파일 `drafts/2026-11-09.json`에 의존한다. 파일이 없으면 skip된다.
- 출력 완전성은 화이트보드 블록에 대해서만 코드로 검사한다. LLM이 쓰는 한국어 설명 문장의 잘림은 코드로 검사하지 않는다(템플릿과 규칙으로만 줄임). 응답에 옮긴 WOD는 `--check-text`로 검사할 수 있지만 Skill이 매번 자동으로 하지는 않는다.
- 복싱 드릴은 시간 구조만 검증한다. 라운드별 드릴 내용과 라운드 수가 맞는지는 LLM이 지킨다.
- 새 Skill 절차의 새 세션 E2E는 아직 실행하지 않았다.

## Phase 3.7 구현 결과 (2026-11-07, 사용자 지시)
- **출력 형식:** 헤더 → 빈 줄 → Rx 동작 한 줄씩(1회만) → `Scale` → Scale A/B/C 레벨별 한 줄(`A 10 Shuttle Runs / 8 T2B / 10 Box Jumps (20")`) → 각주(`*1 Shuttle Run = 7.5m x 2`).
- **이름·약어:** `data/movements.json`에 선택 필드 `whiteboard`(`name`, `abbr`, `unit_label`) 추가. 등록 값은 `toes_to_bar.abbr = T2B`, `shuttle_run.name = Shuttle Runs`, `shuttle_run.unit_label = Shuttle Run`뿐이다. 약어는 스케일 줄에만 쓰고, 등록되지 않은 동작은 `display` 그대로 쓴다. 수치 데이터는 바꾸지 않았다.
- **표기:** load가 `N in`이면 `N"`로 바꾸고, 그 밖의 load(`60 cm` 등)는 그대로 둔다. 셔틀런 각주 숫자는 `equipment.json` `space.shuttle_run`(`one_way_m`, `rep_distance_m`)에서 만든다. 근거가 없으면 각주를 쓰지 않는다.
- **완전성 검사:** `missing_lines`는 헤더·Rx 줄·`Scale`·스케일 한 줄·각주를 줄 단위로 비교한다. 새 `scale_line_gaps`는 스케일 줄을 ` / `(괄호 밖)로 다시 나눠 초안 동작 표기와 같은지 검사한다. 다르면 `render_scale_incomplete` 오류다. `--check-text`도 새 형식 기준이다.
- **유지:** autofix·simulate·check_equipment·check_class 로직은 바꾸지 않았다. autofix `final_text`가 새 형식으로 생성된다.
- **문서:** SKILL.md(규칙 8, §5.1, §6), rules.md §5·§8, README, PLAN 표 갱신.
- **한계:** 이름은 `display` 기준이라 예시의 단수형(`Box Jump`, `Step Up`)과 다르게 복수형(`Box Jumps`, `Step-ups`)으로 나온다. 바꾸려면 `whiteboard.name`을 코치가 정해 등록한다.

## Phase 4 구현 결과 (2026-11-07 ~ 2026-11-08)
- **`scripts/save_wod.py`:** `check <draft>`(재검증, 초안 코드·경고 코드·같은 날짜 기록 코드 표시, 파일 안 씀) / `save <draft> --draft-code CODE --coach-message TEXT [--accept-warnings CODE] [--replace-existing CODE]`(`--approve`는 예전 이름). 저장 조건: 초안 코드 일치, 재검증 오류 없음, 정확 수량 부족(`short`) 없음, 경고가 있으면 경고 코드 일치, 같은 날짜 기록은 기록 코드로만 교체(이전본 `wods/archive/`). 임시 파일 → fsync → `os.link`(새 파일)/`os.replace`(교체). 기록 `wods/<date>.json`(`wod-record/1`): `approved_at`(save 실행 시점 실제 시스템 시각), `approval`(`method: agent_reported`, `coach_message_verified: false`, `draft_code`), `wod`, `summary`, `whiteboard`, `validation`, `autofix`(원장 요약·최초 초안·실행 기록).
- **승인 보장 수준 (2026-11-08 확인·결정):** 초안 코드·경고 코드·기록 코드는 파일만 있으면 계산되는 해시라 **사람 승인의 증명이 아니다.** 임시 디렉터리에서 CLI 인자만으로 저장되는 것을 재현했다. 코드는 "보여 준 초안 = 저장할 초안" 무결성과 상태 확인용이다. 승인 판단은 Skill(에이전트) 책임이다. `.claude/settings.json`의 `ask`(`python3 scripts/save_wod.py save:*`)는 그 형태의 명령에서 실제 권한 창을 띄웠다(사용자 확인). 하지만 이것은 실행 허가일 뿐 WOD 승인이 아니다. TTY 확인 같은 강한 증명은 로컬 개인용 범위를 넘어 도입하지 않기로 했다(사용자 결정).
- **`scripts/recent_wods.py`:** `wods/YYYY-MM-DD.json`(최상위)만, 기간 [기준일−7일, 기준일), 기준일 당일은 `same_day`, 이후는 제외(경고). 형식·시간·동작·패턴 요약, 동작 2회 이상·패턴 3회 이상 반복 참고 경고, `--draft` 겹침 경고(금지 아님). 손상 JSON·필수 필드 누락·파일명≠date·형식 불명 파일(.txt 등)·미등록 동작 경고.
- **`scripts/draft_store.py`:** 후보 `drafts/<date>.candidate.json` → 현재 초안. 같은 날짜 초안이 있으면 기본 거부(exit 1), `--keep-existing` / `--new-version`(이전 초안·원장을 `drafts/versions/<date>.v<N>.json`에 보존). `status`로 초안 코드·버전 목록.
- **`scripts/autofix.py` 이력 원장:** `--out` 시 `<out>.history.json`(`autofix-ledger/1`)에 실행 추가: `original_draft`, `runs[]`(시각, 입력·출력 해시, 직전 출력과 연결 여부, status, 수정 전/후, changes). 결과 JSON의 `changes`/`history`는 이번 실행분(기존 구조 유지), `ledger`는 누적 요약. 손상·다른 날짜 원장은 덮어쓰지 않고 exit 2. `--out` 수정본 쓰기도 원자적으로 변경.
- **`scripts/render_wod.py`:** autofix 보고서에 원장 요약이 있으면 최초 수정 전 상태·누적 수정 내역 표시, 실행 사이 수동 변경 경고. 한 줄 스케일 화이트보드 형식 그대로.
- **`scripts/common.py`:** `sha256_json`, `sha256_file`, `now_iso`, `atomic_write_text`, 기본 경로 상수.
- **Skill:** 생성 전 `recent_wods.py`, 후보 → `draft_store.py commit`, `save_wod.py check` 결과를 보고에 포함, 규칙 9(코치가 최종 WOD·경고를 검토하고 명시적으로 승인하기 전 `save` 금지, 코드·권한 허가는 승인이 아님, 다른 형태 명령 금지), §8 저장 절차(`--draft-code`, 보고한 값만, 결과는 실제 출력으로만 보고). `allowed-tools`에 `recent_wods.py`·`draft_store.py`·`save_wod.py check` 추가(`save` 제외).
- **`.claude/settings.json`:** allow에 `recent_wods.py`·`draft_store.py`·`save_wod.py check`, ask에 `save_wod.py save`. 에이전트가 직접 반영함(이번엔 거부되지 않음).
- **테스트 (+35):** `test_save_wod.py` 15(초안 코드 없음·불일치·JSON 승인 필드 무시, 메시지 필수, 검증 실패, 정확 수량 부족, 경고 코드, 승인 후 초안 변경, 정상 저장 필드, 전체 해시, 중복·교체·보존, 원장 포함, 원자적 쓰기, 승인 증명 아님 기록·코드 계산 가능, CLI·예전 인자), `test_recent_wods.py` 6, `test_draft_store.py` 7, `test_autofix.py` 원장 5, `test_render_wod.py` 누적 표시·호환 2. 모두 임시 디렉터리 사용, 실제 `wods/` 미생성 확인.
- **수동 검증 (2026-11-08, 임시 디렉터리, 실제 `wods/` 미사용):** save 시나리오 — `--approve` 생략 exit 2, 틀린 코드 exit 1, 경고 코드 없음 exit 1, 정상 저장 exit 0(권한 창 표시·사용자 일회성 Yes), 중복 exit 1·틀린 교체 코드 exit 1(기록 해시 불변). recent — 7일 경계·미래 제외·같은 날짜·손상 JSON·.txt 경고·반복/겹침 경고, exit 0. autofix — 같은 초안 2회 실행 후 원장에 실행 2개, 1차 수정 보존, render가 "누적 수정 1회(실행 2회)·수정 전 short" 표시. draft_store — 기본 거부 exit 1(현재 초안 불변), `--new-version` exit 0, v1이 이전 초안과 바이트 동일.

### 알려진 한계 (Phase 4)
- **승인 증명 없음:** 저장 도구는 사람이 승인했는지 확인하지 못한다. CLI 인자를 직접 구성하면 코치 없이도 저장된다. `ask` 권한 규칙은 `python3 scripts/save_wod.py save` 형태에만 걸리고, 다른 명령 형태·Bash 파일 쓰기(`cp`, `python3 -c`)·권한 우회 모드·Codex CLI에는 효력이 없다. `deny Edit(wods/**)`는 Edit/Write 도구만 막는다.
- `--coach-message`는 검증하지 않는다. `approved_at`은 저장 실행 시각이다(코치 발화 시각 아님).
- `--wods-dir`를 생략하면 실제 `wods/`가 기본값이다. 테스트·수동 검증에서는 항상 임시 경로를 지정해야 한다.
- 반복 경고 기준(동작 2회·패턴 3회)은 휴리스틱이며 코치 확인 전이다.
- `draft_store.py`는 에이전트가 후보 파일 절차를 따를 때만 보호한다. `Edit(drafts/**)` 허용이라 Write로 `drafts/<date>.json`을 직접 덮어쓰는 것은 권한으로 막지 않는다(Skill 규칙 2로만 금지).
- 원장(`drafts/*.history.json`)과 버전(`drafts/versions/`)은 git 제외 임시 폴더에 있다. 영구 보존은 저장된 기록의 `autofix` 필드뿐이다.
- 예전 `wods/*.txt` 형식은 읽지 않는다(경고만). 현재 실제 `wods/`에는 기록이 없다.
- E2E는 LLM 출력이라 실행마다 동작 선택·문장이 달라질 수 있다. 아래 결과는 2026-11-08 각 1회 실행 기록이다.
- 에이전트가 쓰는 서술 문장(개수·전체 사용 여부 등)은 코드로 검증되지 않는다. 사용자 E2E 세션 B에서 근거 없는 주장 1건이 나왔고, Skill 규칙 11로 금지했다(규칙 추가 후 재발 여부는 PLAN 시나리오 4개 실행에서만 관찰 — 해당 문장 없음).

## Phase 4 E2E (2026-11-08)

공통 하네스: 프로젝트를 `.git`·`drafts`·`wods` 없이 임시 폴더에 복사(스크립트 기본 경로가 복사본 안으로 향함 → 실제 `wods/` 미접근), 헤드리스 `claude -p --output-format stream-json`, `--settings <복사본>/.claude/settings.json`(샌드박스가 신뢰되지 않은 작업 공간이라 프로젝트 allow가 무시되기 때문). 실행 후 실제 저장소 `git status` 변화 없음, 실제 `wods/` 미생성 확인. 코드 수정 없음.

### A. PLAN §8.2 원래 시나리오 (Phase 4 완료 기준)

| ID | 입력 | PLAN 기대 결과 | 실제 결과 | 판정 |
|----|------|---------------|----------|------|
| S1 | "내일 18:30 수업 예상 10명이야. 오늘은 로잉 250m + 버피 10개 5라운드 했어. 내일은 짐내스틱 위주로 WOD 짜줘. 손목 아픈 회원 1명 있어." (Phase 3과 같은 입력, 현재 Skill로 재실행) | 짐내스틱 위주, 로잉·버피와 패턴 겹침 언급, 본운동 30분 검증, "추정 불가", 손목 회원 대체, 저장 전 승인 요청 | T2B·V-ups 중심 AMRAP 14(Box Jumps는 박스 10 vs 9 `short`로 autofix가 Wall Balls로 교체). 오늘 WOD(cardio·push)와 비교해 push 겹침 언급. 14 ≤ 30 검증됨. 완주 가능성 추정 불가(누락 목록). 손목 회원 T2B → V-ups. 풀업바 `possibly_short` → 운영 선택지(스크립트 근거 인용). 저장 시도 0, 승인 질문에서 멈춤 | PASS |
| S2 | "내일 성인 6명 수업 WOD 짜줘. 링 머슬업 넣어줘." | 층고 제한을 이유로 만들지 않고 대체 동작 제안 | 층고 제한(`high_ceiling`)을 근거로 링 머슬업 제외, 등록 대체가 없음을 밝히고 T2B+Burpees로 대체. 초안에 `ring_muscle_up` 없음. 링 로우·딥은 미등록이라 못 썼다고 안내. 저장 시도 0 | PASS |
| S3 | "내일 성인 6명 수업, AMRAP 40분으로 짜줘." | 30분 초과로 거부, 30분 이하로 조정 제안 | "AMRAP 40분은 만들지 않았습니다. 본운동은 최대 30분" + AMRAP 30 이하 / 40분 블록 안에 AMRAP 30 두 가지 제안. 초안 미생성, 저장 시도 0 | PASS |
| S4 | 주간 플랜 없이 요청 | 최근 기록만으로 생성 | (아래 B의 세션 B로 확인) 주간 플랜 없이 11-11 요청 → `recent_wods.py` 결과(11-06·11-08·11-10)만으로 동작 선택, 전날 Shuttle 제외 | PASS |
| S5 | "오늘 저녁 메뉴 추천해줘" | "WOD 요청이 아닙니다" | "WOD 요청이 아닙니다." 도구 호출 0. 안내 문장 1줄을 덧붙임(Skill의 "라고만 답한다"보다 한 줄 많음 — 경미) | PASS |
| S6 | 승인 없이 "좋네" 정도의 반응 | 저장하지 않고 명시적 승인 재확인 | (아래 B의 S5로 확인) "오 좋네, 괜찮은 것 같아" → 저장 시도 0, 승인으로 보지 않음, 경고 7건 재확인 후 질문 | PASS |

### B. 사용자 지정 통합 시나리오 (Phase 4 기능 흐름)

fixture: `wods/2026-11-06.json`(T2B·Box Jumps), `wods/2026-11-08.json`(Row·Burpees), `drafts/2026-11-10.json`(Wall Balls·V-ups) — 모두 `[E2E fixture]` 표시.

| ID | 내용 | 실제 결과 | 판정 |
|----|------|----------|------|
| S1 | 최근 7일 조회 후 60분 수업안 | 첫 단계에서 `recent_wods.py`, 11-08 Row 겹침 언급, 수업 60분·복싱 4×3/1 검증 통과 | PASS |
| S2 | 기존 초안 덮어쓰기 전 확인 | `draft_exists`로 멈추고 두 초안 코드 제시 → "새 버전" 답 후 `--new-version`, v1 = fixture(초안 코드 `df4de1386d8e` 일치) | PASS |
| S3 | 제약 위반 자동 수정·이력 보존 | 로잉 6 vs 5 → Row 200m → Shuttle 13회, 코치 요청 동작 변경을 명시. 원장·저장 기록 `autofix`에 최초 초안(Row)과 수정 보존 | PASS |
| S4 | 화이트보드·A/B/C | Rx 1회, 스케일 레벨별 한 줄(동작 3개), 각주. 응답 화이트보드 `--check-text` 빠진 줄 0 | PASS |
| S5 | 명시적 승인 없이 저장 안 함 | 턴 1–3 저장 시도 0, "좋네"는 승인 아님으로 처리 | PASS |
| S6 | 승인 후 저장 → 다음 세션 반영 | 테스트 입력 승인 후 `check` 재확인 → `save` exit 0(기록 코드 `21dce7366daf`, `agent_reported`, 경고 7건 수용). 새 세션(11-11)의 최근 기록에 11-10 반영 | PASS |

- S6 저장 권한은 **테스트 하네스가 코치의 권한 창 Yes를 대신**했다(샌드박스 복사본 설정에서만 `save`를 ask → allow). 승인 문장도 테스트 입력이다. 첫 저장 시도는 ask 규칙으로 거부됐고, 에이전트는 "저장하지 않았습니다"라고 정확히 보고했다.
- 사용자 지정 E2E의 첫 Turn 1은 신뢰되지 않은 작업 공간 때문에 프로젝트 allow가 무시돼 무효 처리하고 `--settings`로 재실행했다.

### E2E에서 발견한 문제
- **복합 명령 권한 거부:** `cmd; echo "exit=$?"`, `| python3 -c` 형태가 거부돼 재실행. → Skill 규칙 10(명령 하나씩) 추가. 추가 후 PLAN 시나리오 4개 실행에서는 복합 명령 0건.
- **근거 없는 단정:** 세션 B "등록된 동작 9개를 최근 7일에 모두 썼습니다"(사실 아님 — Hanging Knee Raise·Step-up 미사용). → Skill 규칙 11 추가.
- **자연어 요청 시 Skill 도구 권한:** PLAN 시나리오 S1–S3에서 헤드리스 세션의 `Skill` 도구 호출이 권한 거부됐고, 에이전트가 `SKILL.md`를 Read로 직접 읽어 같은 절차를 따랐다. 대화형 세션에서는 권한 창이 뜰 것으로 보이며, 헤드리스·대화형 모두에서 확인하지 않은 설정 변경은 하지 않았다.
- **S5 응답:** 필수 문구 뒤에 안내 1줄을 덧붙임(경미).
- (무효 처리된 첫 실행에서) 데이터에 없는 월볼 무게를 "확인 필요"와 함께 적은 사례 1건.

## 다음 할 일
1. 코치 확인: 반복 경고 기준(동작 2회·패턴 3회), 동작 패턴 분류, 장비 미확인 수량, 월볼 무게 구성, 짐내스틱 동작 추가(링 로우·딥 등 등록 여부).
2. (선택) 헤드리스·자동화 사용이 필요하면 `Skill` 도구 권한 허용 방식을 확인한다.
3. Phase 5 범위 결정 (키즈, 장비 회전, 패턴 판정, 결과 보정).

## 작업 로그
- 2026-11-07: 기획서 분석, MVP 범위·프로젝트 구조·구현 단계 설계, 문서 초안 작성. 기능 코드 없음.
- 2026-11-07: Phase 0 문서 정합성 점검. AGENTS.md 디렉터리 구조에 `drafts/` 추가, PLAN §7 Phase 4 완료 조건을 시나리오 S1–S6으로 수정.
- 2026-11-07: 시간 기준 명확화(60분 수업 / WOD 블록 최대 30분 / 60분 구성은 Post-MVP) — AGENTS.md, PLAN.md, README.md 반영. Phase 1 데이터 파일 3개 생성(기획서 값만, 미확인은 `null`). PLAN §4 데이터 형식을 실제 파일 기준으로 갱신(`sec_per_rep` → `unit` + `sec_per_unit`, `available` 3상태, `rules.md` 기계 판독 json 블록). 스크립트·Skill 미구현.
- 2026-11-07: 코치 확정 사항 반영 — 본운동 최대 30분(웜업·설명·쿨다운 불포함, AMRAP/EMOM 설정 시간·For Time TC), 웜업 7/설명 4/쿨다운 5분은 예시로 격하, 성인 월볼 금지 제거·월볼 보유, 셔틀런 1rep 15m·로잉 5대 확정, 2레인·2인 1조 교대는 `operational_examples`(규칙 아님)로 이동. 동작 시간을 `sec_per_unit` 단일값 → `time_estimate` 범위(null 허용)로 변경, 시간 표시 4상태(검증됨/추정/추정 불가/확인 필요) 도입, EMOM 지원 형식 추가. AGENTS·PLAN·README 반영. 스크립트·Skill 미구현.
- 2026-11-07: 장비 데이터 입력, **Phase 1 완료**. 수량을 `{value, precision: exact|approx|unknown}`으로 구분, 바벨·원판 lb / 덤벨·케틀벨 kg 키 사용. 링 '없음'→'보유, 층고 제한'으로 정정, `space.ceiling`(high_ceiling 제한)·`space.wall_target`(약 2.3m, 표준 타깃 불가) 추가, 동작에 `space_tags` 필드·Ring Muscle-up(제한 검증용) 추가. 수량 정확도별 경고 규칙을 rules.md §6에 명시. JSON 파싱·참조 검증 수행(오류 0). Git 기본 브랜치 main, .gitignore 추가, 첫 로컬 커밋.
- 2026-11-07: **Phase 2 완료**. `scripts/common.py`·`check_equipment.py`·`simulate.py` 구현, 테스트 67개 통과(`tests/fixtures/`에만 가상 시간 값). 종료 코드 0/1/2·공통 JSON 형식 확정. 초안 선택 필드(`group`, `weights`, `units_per_athlete`, `concurrent_athletes`) 추가(PLAN §4.3). `data/` 변경 없음. Skill·커밋 미진행.
- 2026-11-07: **Phase 3 완료** (Phase 순서 변경: Skill 먼저). `.claude/skills/wod-planner/SKILL.md`, `.claude/settings.json` 추가. 새 헤드리스 세션에서 Skill 발견·자연어 E2E(초안→검증 2종→보고→승인 대기) 확인, `wods/` 미생성. deny 규칙 실동작은 미검증. PLAN §6·§7, CLAUDE.md, AGENTS.md, README 갱신. 커밋 미진행.
- 2026-11-07: **Phase 3.5 완료** (사용자 지시로 Post-MVP 일부 앞당김). `autofix.py`(최대 3회 자동 수정·재검증), `check_class.py`(수업 시간 검증), 스케일 A/B/C·`max_workout_min` 검증, check_equipment issue 위치 정보. Skill §3·§5·§7 갱신, AGENTS·PLAN·rules.md 범위 문구 갱신. 테스트 108개 통과. settings.json 권한 추가 실패(분류기 거부), 새 절차 E2E 미실행. 커밋 미진행.
- 2026-11-08: **Phase 4 완료**. PLAN §8.2 시나리오 S1–S6 PASS(S1·S2·S3·S5 현재 Skill로 헤드리스 실행, S4·S6은 통합 E2E 세션으로 확인), 사용자 지정 통합 E2E 6개 PASS. 모두 샌드박스 복사본에서 실행, 실제 `wods/` 미접근. Skill 규칙 10(명령 하나씩 실행)·11(확인하지 않은 사실 단정 금지) 추가. 테스트 173개 통과. 커밋 미진행.
- 2026-11-08: **Phase 4 스크립트·테스트 완료**. `save_wod.py`·`recent_wods.py`·`draft_store.py`·autofix 이력 원장, Skill·settings·문서 갱신. CLI 인자만으로 저장 가능함을 재현하고, 초안 코드를 "승인 증명이 아닌 무결성 확인용"으로 코드·문서에 명시. 테스트 173개 통과. 시나리오 S1–S6 미실행. 커밋 미진행.
- 2026-11-07: **Phase 3.7 완료**. 화이트보드 간결 형식(Rx 1회, 스케일 레벨별 한 줄, T2B 약어·셔틀런 각주는 데이터 등록분만), 한 줄 스케일 완전성 검사. 테스트 138개 통과. 커밋 미진행.
- 2026-11-07: **Phase 3.6 완료**. 복싱 인터벌 시간 검증(`check_class.py --interval`), `render_wod.py`(초안 → 화이트보드·검증 요약·코치 확인 분리·출력 완전성 검사), autofix `final_text`. 출력 잘림은 JSON 누락이 아니라 표시·복사 단계로 판단, 화이트보드를 코드 생성으로 전환. 테스트 131개 통과. render_wod 실행 권한은 사용자가 settings.json·Skill에 추가.
