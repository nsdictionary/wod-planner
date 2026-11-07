# WOD Planner

크로스핏 코치를 대신해 다음 날 WOD를 **박스의 장비·공간 제약에 맞춰** 만들고,
**WOD 본운동이 최대 30분 안인지 검증**한 뒤(근거 데이터가 있으면 라운드 시간도 추정) 결과를 보여 주고 코치 승인을 기다리는 Claude Code 에이전트입니다.
승인된 WOD를 날짜별 텍스트로 저장하는 기능(`save_wod.py`)은 **아직 구현되지 않았습니다** (Phase 4 예정).

> AX School 과제 제출용 저장소입니다. 기획서: https://gist.github.com/nsdictionary/36fa6d76c435011389a925ed4012ef3c

## 대상 사용자

직원 없이 성인·키즈 수업을 혼자 지도하는 **소규모 크로스핏 박스 코치**.
오후 3시부터 밤 10시까지 수업을 한 뒤, 지친 상태로 다음 날 WOD를 설계해야 합니다.

## 자동화하는 업무

**다음 날 WOD 초안 작성과 본운동 시간(최대 30분) 검증** (주 5–6회, 하루 30–40분 → 목표 10분)

| 코치가 지금 손으로 하는 일 | 에이전트가 하는 일 |
|---|---|
| 지난 일주일 WOD를 떠올려 겹치지 않는 동작 고르기 | 최근 7일 기록 파일을 읽고 동작 패턴 중복 확인 |
| 로잉 5대, 덤벨 수량, 낮은 층고·월볼 타깃 높이 등 장비·공간 제약 확인 | 장비 목록 파일 기준으로 스크립트가 검증, 불가 동작은 대체 제안 |
| 라운드당 시간·TC 암산 | 본운동 30분 이하를 스크립트가 검증. 라운드 시간은 근거 있는 추정 범위로만 보여 주고, 데이터가 없으면 "추정 불가"로 표시 |
| 화이트보드용 텍스트로 정리 | 화이트보드 형식으로 출력하고 승인을 기다림. 저장은 **코치 승인 후에만** (저장 기능은 Phase 4 예정) |

범위 밖: 회원별 기록·PR 관리, TV 송출, 노션 연동, 복싱 프로그램 설계, 개인 PT, 키즈 WOD.
60분 수업안(준비운동·복싱 드릴·WOD·마무리)은 요청 시 **응답에만** 표시하고, 시간 합계만 스크립트로 검증합니다.

## 동작 방식

- **Claude Code Skill** (`.claude/skills/wod-planner/`)이 작업 절차를 담당
- **데이터 파일** (`data/`)에 박스 장비·동작 시간표·작성 규칙
- **Python 스크립트** (`scripts/`, 표준 라이브러리만)가 시간 검증·장비 검증·자동 수정·수업 시간 합계 검증을 결정적으로 수행 (최근 기록 조회·저장 스크립트는 Phase 4 예정)
- **승인 게이트**: 코치가 확인하기 전에는 저장하지 않음

자세한 설계는 [`docs/PLAN.md`](docs/PLAN.md)를 참고하세요.

## 현재 구현 상태

**Phase 3.6 완료 — 초안 검증 후 고칠 수 있는 문제를 스크립트가 최대 3회 자동 수정·재검증하고, 최종 화이트보드 WOD(Rx + Scale A/B/C)와 검증 요약을 초안 JSON에서 생성합니다. 60분 수업 시간과 복싱 드릴 라운드 시간도 검증합니다. 승인 후 저장(`save_wod.py`)과 최근 기록 조회(`recent_wods.py`)는 아직 없습니다.**

| 기능 | 상태 |
|------|------|
| 설계 문서 (AGENTS.md, CLAUDE.md, PLAN, PROGRESS) | ✅ 완료 |
| 장비·동작·규칙 데이터 파일 | ✅ 코치 확정 값 입력, 파싱·참조 검증 (미확인 수량은 경고 대상) |
| 시간 검증·추정 스크립트 (`simulate.py`) | ✅ 본운동 30분 검증(AMRAP/EMOM/For Time, TC 필수). 라운드 추정은 시간 데이터가 있을 때만 — 실제 데이터는 아직 없어 "추정 불가" 출력. EMOM 추정은 미지원 |
| 장비 제약 검증 스크립트 (`check_equipment.py`) | ✅ 미등록·미보유·금지·층고 제한 검출, 추정/미확인 수량 경고, 인원 대비 수량 비교, 월볼 타깃 경고, 대체 동작 제안 |
| 자동 수정·재검증 (`autofix.py`) | ✅ 사용 불가 동작·시간 상한 초과·장비 부족을 한 번에 하나씩 최대 3회 수정, 매번 두 검증 재실행. 대체 동작은 장비가 충분하다는 근거가 있는 것만(정확 수량 우선), 단위가 다르면 거리 근거가 있을 때만 환산. 운영 방식(파트너·시차 출발)은 자동 적용하지 않고 동시 사용 인원 계산을 근거로 코치에게 반환 |
| 코치 요청 본운동 상한 (`max_workout_min`) | ✅ "18분 이내" 같은 요청을 30분 상한과 함께 검증 |
| 스케일 A/B/C (`scales`) | ✅ 스케일 동작의 사용 가능 여부 검증, Rx 대체 시 스케일에도 반영, 성인인데 없으면 경고. 스케일별 장비 수량은 인원 배분을 몰라 비교하지 않음 |
| 60분 수업안 시간 검증 (`check_class.py`) | ✅ 블록 합계 = 수업 시간, 필수 블록, WOD 블록 ≥ 본운동, 복싱 드릴 내부 시간(`--interval boxing=4x3/1` = 3분 × 4라운드 + 휴식 1분 × 3회, 마지막 라운드 뒤 휴식 없음). 수업안 내용(준비운동·복싱 드릴)은 Skill이 응답에만 작성 |
| 최종 출력 생성 (`render_wod.py`) | ✅ 초안 JSON → 화이트보드 텍스트(Rx·스케일 모든 동작 한 줄씩), 출력 완전성 검사, 검증 요약(passed는 코드 검사 항목만), 코치 확인 항목 분리, 자동 수정 전후 표시, 옮겨 쓴 텍스트 검사(`--check-text`) |
| 최근 기록 조회 / 승인 후 저장 스크립트 | ⬜ 미착수 (Phase 4). 지금은 승인해도 `wods/`에 저장되지 않음 |
| `wod-planner` Claude Code Skill | ✅ 요청 해석 → 초안(`drafts/`) → `autofix.py` 검증·자동 수정 → (요청 시) `check_class.py` → 보고 → 승인 대기. 저장 단계는 Phase 4. 새 절차의 새 세션 E2E는 미실행 |
| 키즈 버전, 장비 회전 계산 | ⬜ MVP 이후 |

최신 진행 상황: [`docs/PROGRESS.md`](docs/PROGRESS.md)

### Skill 사용 (Claude Code)

프로젝트 폴더에서 Claude Code를 열고 자연어로 요청합니다.

```
내일 18:30 수업 예상 10명이야. 오늘은 로잉 250m + 버피 10개 5라운드 했어. 짐내스틱 위주로 WOD 짜줘.
```

`/wod-planner <요청>`으로 직접 호출할 수도 있습니다. 결과로 화이트보드용 WOD, 본운동 시간 검증, 완주 가능성(추정 또는 추정 불가 사유), 장비·운영 경고가 나오고 승인을 기다립니다.

### 스크립트 직접 실행

```bash
# 장비·공간 검증 (기획서 예시 WOD, 실제 data/ 사용)
python3 scripts/check_equipment.py tests/fixtures/drafts/plan_example_amrap.json

# 본운동 시간 검증 + 완주 가능성 추정
python3 scripts/simulate.py tests/fixtures/drafts/plan_example_amrap.json

# 검증 + 자동 수정 (최대 3회), 수정본을 다른 파일로
python3 scripts/autofix.py <draft.json> --out <fixed.json>

# 60분 수업 시간 배분 검증
python3 scripts/check_class.py --total 60 --block warmup=12 --block boxing=15 --block briefing=5 \
    --block wod=18 --block cooldown=10 --require boxing --interval boxing=4x3/1 --wod <draft.json>

# 최종 출력 (화이트보드 + 검증 요약 + 코치 확인 항목)
python3 scripts/autofix.py <draft.json> --out <draft.json> --json > autofix.json
python3 scripts/render_wod.py <draft.json> --autofix-report autofix.json \
    --total 60 --block warmup=12 --block boxing=15 --block briefing=5 --block wod=18 --block cooldown=10 \
    --require boxing --interval boxing=4x3/1

# 기계 판독 출력 / 다른 데이터 디렉터리
python3 scripts/simulate.py <draft.json> --json --data-dir tests/fixtures/data
```

종료 코드: `0` 통과(경고 가능) / `1` 규칙 위반·미해결 문제 / `2` 입력·데이터 오류.

## 개발 환경

- Claude Code (주 개발 도구) — 진입점 `CLAUDE.md`
- Codex CLI (보조) — 공통 규칙 `AGENTS.md`
- Python 3.11+ (표준 라이브러리만, 외부 패키지 없음)

테스트:

```bash
python3 -m unittest discover -s tests -v
```
