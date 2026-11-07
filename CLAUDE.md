# CLAUDE.md — Claude Code 진입점

공통 규칙은 `AGENTS.md`에 있다. 아래 import로 함께 로드된다.

@AGENTS.md

## Claude Code 전용 안내

### 세션 시작 시
1. `docs/PROGRESS.md`를 읽고 현재 단계와 "다음 할 일"을 확인한다.
2. 개발 작업이면 `docs/PLAN.md`의 해당 단계 설계를 따른다.

### Skill
- WOD 작성 워크플로는 Skill로 제공한다: `.claude/skills/wod-planner/SKILL.md` (**아직 미구현** — Phase 4)
- 코치가 "내일 WOD 짜줘" 같은 요청을 하면 이 Skill을 사용한다.
- Skill은 절차와 판단 기준만 담고, 계산·검증·저장은 `scripts/`를 Bash로 실행해 처리한다.
- 박스 고유 정보(장비, 규칙, 동작 시간표)는 Skill 본문에 복사하지 않고 `data/` 파일을 읽게 한다. 데이터가 바뀌어도 Skill을 고칠 필요가 없게 하기 위함이다.

### 도구 사용
- 스크립트 실행: `python3 scripts/<name>.py ...`
- 테스트: `python3 -m unittest discover -s tests -v`
- `wods/`에 쓰는 것은 `scripts/save_wod.py`를 통해서만, 코치 승인 후에만 한다. Write 도구로 직접 쓰지 않는다.

### Codex CLI와 이어서 작업하기
- Codex는 `AGENTS.md`를 읽는다. Claude Code 전용 내용은 이 파일에만 두고, 모든 에이전트에게 필요한 규칙은 `AGENTS.md`에 둔다.
- 진행 상황은 반드시 `docs/PROGRESS.md`에 남겨, 어느 도구로 이어 가도 같은 상태에서 시작할 수 있게 한다.
