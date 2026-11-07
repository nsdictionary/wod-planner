# PROGRESS — 진행 상황

> 모든 에이전트는 작업 시작 전 이 파일을 읽고, 작업 후 갱신한다.
> 상태 표기: ✅ 완료(코드·테스트로 확인됨) / 🚧 진행 중 / ⬜ 미착수

## 현재 단계: Phase 2 준비 — Phase 1 완료 (2026-11-07)

Phase 1 데이터 파일 3개가 코치 확정 값으로 채워졌다. JSON 파싱과 데이터 참조(동작→장비, 대체 동작, 공간 태그, 패턴, 수량 형식)를 검증했다.
자동 테스트는 Phase 2에서 `tests/`에 추가한다.

## 단계별 상태

| Phase | 내용 | 상태 |
|-------|------|------|
| 0 | 설계 문서 (AGENTS.md, CLAUDE.md, docs/PLAN.md, docs/PROGRESS.md, README.md) | ✅ |
| 1 | 데이터 파일 (`data/equipment.json`, `data/movements.json`, `data/rules.md`) | ✅ 코치 확정 값 입력, 파싱·참조 검증 완료 (미확인 수량은 경고 대상으로 기록) |
| 2 | `scripts/simulate.py`, `scripts/check_equipment.py` + 테스트 | ⬜ 다음 단계 |
| 3 | `scripts/recent_wods.py`, `scripts/save_wod.py` + 테스트 | ⬜ |
| 4 | `.claude/skills/wod-planner/SKILL.md` + 시나리오 테스트 | ⬜ |
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

## 다음 할 일 — Phase 2 계획
1. `scripts/common.py`: `data/` 로더(equipment·movements JSON, `rules.md` 첫 json 블록), 초안 JSON 로드·형식 검증. `--data-dir`로 경로 교체 가능(테스트용).
2. `scripts/check_equipment.py`
   - 미등록 동작, 미보유 장비(`available: false`), `banned_movements`, 층고 제한(`space_tags` ∩ `restricted_space_tags`) → **오류**, 종료 코드 1, `substitutes` 제안
   - 보유 미확인(`available: null`) → 확인 필요 / `approx` → 추정 수량 경고 / `unknown` → 수량 미확인 경고 / `wall_target` → 타깃 높이 경고
   - 예상 인원 vs 보유 수량(장비 수·풀업바·셔틀런 동시 인원) 표시. 부족 시 운영 방식은 선택지로만 제안
3. `scripts/simulate.py`
   - 본운동 시간(AMRAP/EMOM `duration_min`, For Time `time_cap_min`) ≤ 30분 **검증됨**. 초과·For Time TC 없음·미지원 형식 → 종료 코드 1
   - 모든 동작 `time_estimate`와 `transition_sec_range`가 있을 때만 라운드 시간·예상 라운드/완료 **추정 범위** + 근거. 없으면 **추정 불가** + 없는 항목 목록(종료 코드 0). 피로도 `null`이면 "피로도 미반영"
4. 공통 출력: 기본 한국어 텍스트, `--json` 기계 판독.
5. 테스트: `tests/fixtures/`(테스트용 장비·동작·시간 범위)로 `tests/test_check_equipment.py`, `tests/test_simulate.py`. 케이스는 `docs/PLAN.md` §8.1. 실제 `data/`는 파싱·참조 무결성 테스트에만 사용.
6. 완료 조건: 기획서 예시 WOD로 시간 데이터 있음/없음 두 경우 모두 테스트 통과.

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
