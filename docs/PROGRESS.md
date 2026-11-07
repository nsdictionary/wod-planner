# PROGRESS — 진행 상황

> 모든 에이전트는 작업 시작 전 이 파일을 읽고, 작업 후 갱신한다.
> 상태 표기: ✅ 완료(코드·테스트로 확인됨) / 🚧 진행 중 / ⬜ 미착수

## 현재 단계: Phase 4 준비 — Phase 3 완료 (2026-11-07)

Phase 순서 변경(2026-11-07, 사용자 지시): Skill을 먼저 구현(Phase 3)하고, `recent_wods.py`·`save_wod.py`는 Phase 4로 미뤘다.
`wod-planner` Skill이 새 Claude Code 세션에서 발견되고, 자연어 요청 1건으로 초안 작성 → 두 검증 스크립트 → 보고 → 승인 대기까지 동작함을 확인했다.

## 단계별 상태

| Phase | 내용 | 상태 |
|-------|------|------|
| 0 | 설계 문서 (AGENTS.md, CLAUDE.md, docs/PLAN.md, docs/PROGRESS.md, README.md) | ✅ |
| 1 | 데이터 파일 (`data/equipment.json`, `data/movements.json`, `data/rules.md`) | ✅ 코치 확정 값 입력, 파싱·참조 검증 완료 (미확인 수량은 경고 대상으로 기록) |
| 2 | `scripts/simulate.py`, `scripts/check_equipment.py` + 테스트 | ✅ 테스트 67개 통과, 실제 데이터로 예시 WOD 실행 확인 |
| 3 | `.claude/skills/wod-planner/SKILL.md` + `.claude/settings.json` | ✅ Skill 발견·자연어 1건 E2E 확인 (시나리오 S1). S2–S6 미실행 |
| 4 | `scripts/recent_wods.py`, `scripts/save_wod.py` + 테스트 + 시나리오 S1–S6 | ⬜ 다음 단계 |
| 5 | Post-MVP (스케일 A/B/C, 키즈, 장비 회전, 패턴 판정, 결과 보정, 60분 전체 수업 구성) | ⬜ |

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

## 다음 할 일 — Phase 4
1. `scripts/recent_wods.py`: `wods/`에서 기준 날짜 이전 7일(`rules.md` `recent_days`) WOD 파일 조회, 헤더 파싱, 날짜 정렬.
2. `scripts/save_wod.py`: `--approved` 없으면 거부, 같은 날짜 파일이 있으면 거부(덮어쓰기 금지), `wods/YYYY-MM-DD.txt` 저장.
3. 두 스크립트 모두 `common.py`의 종료 코드·JSON 형식을 따른다. 테스트는 임시 디렉터리 사용.
4. Skill의 저장·최근 기록 단계가 새 스크립트를 쓰는지 확인 (`SKILL.md` §1·§7은 이미 "있으면 사용"으로 작성됨). `.claude/settings.json`에 두 스크립트 실행 허용 추가.
5. 시나리오 S1–S6 실행·기록.

## 코치 확인 필요

### A. 미확인 장비 수량 (Phase 1 완료에는 영향 없음 — 검증 시 경고로 표시)
- [ ] **A1.** 덤벨 1 / 1.5 / 2 / 10 / 15 / 20kg 개수 (현재 `unknown`)
- [ ] **A2.** 월볼 무게별 구성 (총 약 20개)
- [ ] **A3.** 링 개수, 줄넘기 개수
- [ ] **A4.** 케틀벨 무게별 개수
- [ ] **A5.** 정확한 층고 (현재 "낮음"만 기록)
- 추정 수량(`approx`): 풀업바 약 8명, 셔틀런 약 8명, 원판 10–45lb 각 약 10장, 월볼 약 20개, 타깃 약 2.3m

### B. 시간 추정 데이터 (선택 — 없어도 MVP 동작, 있으면 라운드 시간 추정 가능)
- [ ] **B1.** 동작별 추정 범위(빠른 회원~느린 회원)와 근거 → `movements.json` `time_estimate`
- [ ] **B2.** 동작 간 전환 시간 범위 → `rules.md` `estimation.transition_sec_range`
- [ ] **B3.** 피로도 반영 방식 → `rules.md` `estimation.fatigue_slowdown_per_round`
- 실제 수업 결과(완료 라운드·시간)를 모아 보정하는 방식이 현실적이다(Post-MVP R9).

### C. 기타
- [ ] **C1.** 동작 패턴 분류 초안 확인 (`movements.json` `patterns`). V-up 같은 코어 동작을 별도 분류로 둘지
- [ ] **C2.** 복싱 관련 요구 범위 (기획서는 복싱 파트 구성을 범위 밖으로 둠. 60분 구성 Post-MVP에서 시간 배분만 다룰지)
- [ ] **C3.** 자주 쓰는 동작 추가 목록 (현재 기획서 등장 동작 + 링 머슬업만 등록. 덤벨·케틀벨·줄넘기 동작 등)

## 작업 로그
- 2026-11-07: 기획서 분석, MVP 범위·프로젝트 구조·구현 단계 설계, 문서 초안 작성. 기능 코드 없음.
- 2026-11-07: Phase 0 문서 정합성 점검. AGENTS.md 디렉터리 구조에 `drafts/` 추가, PLAN §7 Phase 4 완료 조건을 시나리오 S1–S6으로 수정.
- 2026-11-07: 시간 기준 명확화(60분 수업 / WOD 블록 최대 30분 / 60분 구성은 Post-MVP) — AGENTS.md, PLAN.md, README.md 반영. Phase 1 데이터 파일 3개 생성(기획서 값만, 미확인은 `null`). PLAN §4 데이터 형식을 실제 파일 기준으로 갱신(`sec_per_rep` → `unit` + `sec_per_unit`, `available` 3상태, `rules.md` 기계 판독 json 블록). 스크립트·Skill 미구현.
- 2026-11-07: 코치 확정 사항 반영 — 본운동 최대 30분(웜업·설명·쿨다운 불포함, AMRAP/EMOM 설정 시간·For Time TC), 웜업 7/설명 4/쿨다운 5분은 예시로 격하, 성인 월볼 금지 제거·월볼 보유, 셔틀런 1rep 15m·로잉 5대 확정, 2레인·2인 1조 교대는 `operational_examples`(규칙 아님)로 이동. 동작 시간을 `sec_per_unit` 단일값 → `time_estimate` 범위(null 허용)로 변경, 시간 표시 4상태(검증됨/추정/추정 불가/확인 필요) 도입, EMOM 지원 형식 추가. AGENTS·PLAN·README 반영. 스크립트·Skill 미구현.
- 2026-11-07: 장비 데이터 입력, **Phase 1 완료**. 수량을 `{value, precision: exact|approx|unknown}`으로 구분, 바벨·원판 lb / 덤벨·케틀벨 kg 키 사용. 링 '없음'→'보유, 층고 제한'으로 정정, `space.ceiling`(high_ceiling 제한)·`space.wall_target`(약 2.3m, 표준 타깃 불가) 추가, 동작에 `space_tags` 필드·Ring Muscle-up(제한 검증용) 추가. 수량 정확도별 경고 규칙을 rules.md §6에 명시. JSON 파싱·참조 검증 수행(오류 0). Git 기본 브랜치 main, .gitignore 추가, 첫 로컬 커밋.
- 2026-11-07: **Phase 2 완료**. `scripts/common.py`·`check_equipment.py`·`simulate.py` 구현, 테스트 67개 통과(`tests/fixtures/`에만 가상 시간 값). 종료 코드 0/1/2·공통 JSON 형식 확정. 초안 선택 필드(`group`, `weights`, `units_per_athlete`, `concurrent_athletes`) 추가(PLAN §4.3). `data/` 변경 없음. Skill·커밋 미진행.
- 2026-11-07: **Phase 3 완료** (Phase 순서 변경: Skill 먼저). `.claude/skills/wod-planner/SKILL.md`, `.claude/settings.json` 추가. 새 헤드리스 세션에서 Skill 발견·자연어 E2E(초안→검증 2종→보고→승인 대기) 확인, `wods/` 미생성. deny 규칙 실동작은 미검증. PLAN §6·§7, CLAUDE.md, AGENTS.md, README 갱신. 커밋 미진행.
