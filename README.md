# WOD Planner

크로스핏 코치를 대신해 다음 날 WOD를 **박스의 장비·공간 제약에 맞춰** 만들고,
**WOD 본운동이 최대 30분 안인지 검증**한 뒤(근거 데이터가 있으면 라운드 시간도 추정) 결과를 보여 주고 코치 승인을 기다리는 Claude Code 에이전트입니다.
코치가 명시적으로 승인한 초안을 저장 직전에 다시 검증해 `wods/YYYY-MM-DD.json`에 저장하고(`save_wod.py`), 저장된 최근 7일 기록을 다음 WOD에 참고합니다(`recent_wods.py`).

> AX School 과제 제출용 저장소입니다. 기획서: https://gist.github.com/nsdictionary/36fa6d76c435011389a925ed4012ef3c

## 대상 사용자

직원 없이 성인·키즈 수업을 혼자 지도하는 **소규모 크로스핏 박스 코치**.
오후 3시부터 밤 10시까지 수업을 한 뒤, 지친 상태로 다음 날 WOD를 설계해야 합니다.

## 자동화하는 업무

**다음 날 WOD 초안 작성과 본운동 시간(최대 30분) 검증** (주 5–6회, 하루 30–40분 → 목표 10분)

| 코치가 지금 손으로 하는 일 | 에이전트가 하는 일 |
|---|---|
| 지난 일주일 WOD를 떠올려 겹치지 않는 동작 고르기 | 저장된 최근 7일 기록을 `recent_wods.py`로 요약하고 동작·패턴 반복을 참고 경고로 표시 (금지는 아님) |
| 로잉 5대, 덤벨 수량, 낮은 층고·월볼 타깃 높이 등 장비·공간 제약 확인 | 장비 목록 파일 기준으로 스크립트가 검증, 불가 동작은 대체 제안 |
| 라운드당 시간·TC 암산 | 본운동 30분 이하를 스크립트가 검증. 라운드 시간은 근거 있는 추정 범위로만 보여 주고, 데이터가 없으면 "추정 불가"로 표시 |
| 화이트보드용 텍스트로 정리 | 화이트보드 형식으로 출력하고 승인을 기다림. 저장은 **코치 승인 후에만** `save_wod.py`로 (초안 무결성 확인·재검증·덮어쓰기 금지) |

범위 밖: 회원별 기록·PR 관리, TV 송출, 노션 연동, 복싱 프로그램 설계, 개인 PT, 키즈 WOD.
60분 수업안(준비운동·복싱 드릴·WOD·마무리)은 요청 시 **응답에만** 표시하고, 시간 합계만 스크립트로 검증합니다.

## 동작 방식

- **Claude Code Skill** (`.claude/skills/wod-planner/`)이 작업 절차를 담당
- **데이터 파일** (`data/`)에 박스 장비·동작 시간표·작성 규칙
- **Python 스크립트** (`scripts/`, 표준 라이브러리만)가 시간 검증·장비 검증·자동 수정·수업 시간 합계 검증·최근 기록 조회·초안 버전 보호·승인 저장을 결정적으로 수행
- **승인과 저장 안전장치 (보장 수준)**
  - **코치 승인 판단은 Skill(에이전트)이 대화에서 한다.** 저장 도구는 사람이 승인했다는 사실을 증명하지 못한다. 로컬 개인용 도구라는 범위에서 받아들인 한계다.
  - `save_wod.py save`는 **무결성과 상태**를 확인한다. 초안 코드(초안 내용 해시)가 코치에게 보여 준 값과 같아야 하고, 저장 직전 재검증에 오류가 없어야 한다. 남은 경고가 있으면 경고 코드가 지금 경고 목록과 같아야 하고, 같은 날짜 기록은 기록 코드가 있을 때만 교체한다. 이 코드들은 파일만 있으면 누구나 계산할 수 있어 **승인 증명이 아니다.**
  - `.claude/settings.json`에서 `python3 scripts/save_wod.py save`는 `ask`라서 실행할 때 권한 창이 뜬다. 이것은 명령 실행 허가이지 WOD 승인이 아니고, 다른 형태의 명령에는 적용되지 않는다.

자세한 설계는 [`docs/PLAN.md`](docs/PLAN.md)를 참고하세요.

## 현재 구현 상태

**Phase 4 완료 — 승인 저장(`save_wod.py`), 최근 기록 조회(`recent_wods.py`), 초안 버전 보호(`draft_store.py`), 자동 수정 이력 원장(`autofix.py`)을 추가했습니다. 테스트 173개 통과, PLAN의 에이전트 시나리오 S1–S6과 통합 E2E 6개를 새 헤드리스 세션(임시 샌드박스)에서 통과했습니다.**

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
| 최종 출력 생성 (`render_wod.py`) | ✅ 초안 JSON → 화이트보드 텍스트(간결 형식: Rx 동작별 한 줄 1회, Scale A/B/C 레벨별 한 줄, 등록 약어만 사용, 셔틀런 각주), 출력 완전성 검사, 검증 요약(passed는 코드 검사 항목만), 코치 확인 항목 분리, 자동 수정 전후 표시, 옮겨 쓴 텍스트 검사(`--check-text`) |
| 승인 후 저장 (`save_wod.py`) | ✅ `check`(재검증·초안 코드·경고 코드 표시, 파일 안 씀) / `save`(초안 코드 일치, 재검증 오류·정확 수량 부족 없음, 경고는 경고 코드로 수용, 같은 날짜 기록은 기록 코드로만 교체·이전본 `wods/archive/` 보존). 임시 파일 → fsync → 원자적 반영. 기록에 승인 시각(save 실행 시점의 실제 시스템 시각)·코치 발화(검증 안 됨, `approval.method = agent_reported`)·검증 결과·자동 수정 이력 포함 |
| 최근 기록 조회 (`recent_wods.py`) | ✅ `wods/YYYY-MM-DD.json`만, 기준일 이전 7일, 미래 기록 제외, 형식·시간·동작·패턴 요약, 반복 참고 경고, 손상·불완전·형식 불명 파일 경고 |
| 초안 보호 (`draft_store.py`) | ✅ 후보 → 현재 초안 반영. 같은 날짜 초안이 있으면 기본 거부, `--new-version`(이전 초안·이력 `drafts/versions/` 보존) / `--keep-existing` |
| 자동 수정 이력 보존 | ✅ `autofix.py --out`이 `<draft>.history.json` 원장에 실행을 추가(최초 초안·실행별 수정 전/후·수정 내역). 재검증해도 이전 수정이 사라지지 않고 `render_wod.py`가 누적 이력을 표시 |
| `wod-planner` Claude Code Skill | ✅ 최근 기록 조회 → 후보 초안 → `draft_store.py` → `autofix.py` → (요청 시) `check_class.py` → `render_wod.py` → `save_wod.py check` → 보고 → 승인 대기 → `save_wod.py save`(권한 확인). 새 세션 E2E 통과(2026-11-08) |
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

# 최근 7일 기록 (기준일 = 만들 WOD 날짜)
python3 scripts/recent_wods.py --date 2026-11-10 [--draft drafts/2026-11-10.json]

# 초안 보호: 후보 → 현재 초안 (같은 날짜 초안이 있으면 거부, --new-version / --keep-existing)
python3 scripts/draft_store.py commit 2026-11-10
python3 scripts/draft_store.py status 2026-11-10

# 승인 저장: 확인(파일 안 씀) → 코치 승인 후 저장 (초안 코드·경고 코드는 check 출력값, 무결성 확인용)
python3 scripts/save_wod.py check drafts/2026-11-10.json
python3 scripts/save_wod.py save drafts/2026-11-10.json --draft-code <초안 코드> --coach-message "저장" \
    [--accept-warnings <경고 코드>] [--replace-existing <기록 코드>]

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
