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

범위 밖: 회원별 기록·PR 관리, TV 송출, 노션 연동, 복싱 파트 구성, 개인 PT.
60분 전체 수업 구성(웜업·설명·쿨다운·복싱·스트렝스·악세서리 시간 배분)은 MVP 이후에 다룹니다.

## 동작 방식

- **Claude Code Skill** (`.claude/skills/wod-planner/`)이 작업 절차를 담당
- **데이터 파일** (`data/`)에 박스 장비·동작 시간표·작성 규칙
- **Python 스크립트** (`scripts/`, 표준 라이브러리만)가 시간 검증·장비 검증을 결정적으로 수행 (최근 기록 조회·저장 스크립트는 Phase 4 예정)
- **승인 게이트**: 코치가 확인하기 전에는 저장하지 않음

자세한 설계는 [`docs/PLAN.md`](docs/PLAN.md)를 참고하세요.

## 현재 구현 상태

**Phase 3 완료 — Claude Code에서 자연어로 WOD 초안 작성·검증까지 동작합니다. 승인 후 저장(`save_wod.py`)과 최근 기록 조회(`recent_wods.py`)는 아직 없습니다.**

| 기능 | 상태 |
|------|------|
| 설계 문서 (AGENTS.md, CLAUDE.md, PLAN, PROGRESS) | ✅ 완료 |
| 장비·동작·규칙 데이터 파일 | ✅ 코치 확정 값 입력, 파싱·참조 검증 (미확인 수량은 경고 대상) |
| 시간 검증·추정 스크립트 (`simulate.py`) | ✅ 본운동 30분 검증(AMRAP/EMOM/For Time, TC 필수). 라운드 추정은 시간 데이터가 있을 때만 — 실제 데이터는 아직 없어 "추정 불가" 출력. EMOM 추정은 미지원 |
| 장비 제약 검증 스크립트 (`check_equipment.py`) | ✅ 미등록·미보유·금지·층고 제한 검출, 추정/미확인 수량 경고, 인원 대비 수량 비교, 월볼 타깃 경고, 대체 동작 제안 |
| 최근 기록 조회 / 승인 후 저장 스크립트 | ⬜ 미착수 (Phase 4). 지금은 승인해도 `wods/`에 저장되지 않음 |
| `wod-planner` Claude Code Skill | ✅ 요청 해석 → 초안(`drafts/`) → 두 스크립트 검증·자동 수정 → 보고 → 승인 대기. 저장 단계는 Phase 4 |
| 스케일 A/B/C, 키즈 버전, 장비 회전 계산 | ⬜ MVP 이후 |
| 60분 전체 수업 구성 | ⬜ MVP 이후 |

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

# 기계 판독 출력 / 다른 데이터 디렉터리
python3 scripts/simulate.py <draft.json> --json --data-dir tests/fixtures/data
```

종료 코드: `0` 통과(경고 가능) / `1` 규칙 위반 / `2` 입력·데이터 오류.

## 개발 환경

- Claude Code (주 개발 도구) — 진입점 `CLAUDE.md`
- Codex CLI (보조) — 공통 규칙 `AGENTS.md`
- Python 3.11+ (표준 라이브러리만, 외부 패키지 없음)

테스트:

```bash
python3 -m unittest discover -s tests -v
```
