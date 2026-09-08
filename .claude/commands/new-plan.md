# /new-plan — 사용자와 의논해 plan 초안을 작성한다

`$ARGUMENTS` 는 이번 plan 의 주제다. 없으면 지금까지의 대화 맥락에서 주제를 잡는다.

## 역할 (거버넌스)
- plan 작성·의논 = **Claude(너)**. 코드 구현은 하지 않는다.
- 승인 = **사용자**. 너는 절대 `status: approved` 로 스스로 바꾸지 않는다. `draft` 로 둔다.
- 구현 = **codex**. 승인 후 `/run-plan` 이 headless 로 실행한다.

## 절차
1. **맥락 읽기**: `docs/memory.md` (프로젝트 분리형이면 해당 프로젝트 memory 도),
   `docs/plans/README.md`, 관련 기존 plan·코드를 읽는다. 추측 대신 실제 파일을 확인한다.
2. **의논 먼저**: 바로 파일을 쓰지 말고, 판단이 갈리는 지점을 사용자에게 확인한다
   — 범위, 우선순위, 대안 중 택일, 건드리면 안 되는 것. 모르는 건 묻는다.
3. **경로 결정**: `docs/plans/YYYY_MM/DD_PLANNN_topic.md`.
   - 오늘 날짜 기준. 같은 날 기존 plan 이 있으면 다음 번호로.
   - 단일 프로젝트 범위면 해당 프로젝트의 `docs/plans/` 아래에 둔다.
4. **작성**: `docs/plans/README.md` 의 reader-first 형식과 권장 섹션을 따른다.
   front matter 는 `planner: Claude`, `executor: codex`, `status: draft`.
5. **self-contained 검사** (중요): codex 는 stateless 로 실행되고 하네스 브리프에는
   **이 plan 전문만** 들어간다. 다른 plan·대화 맥락을 참조만 하면 실행자는 못 본다.
   필요한 선행 결정은 3~6줄로 이 plan 안에 재서술했는지 확인한다.
6. **handoff 3종 검사**: "구현해야 할 것 / 참고해야 할 것 / 신경써야 할 것" 이
   파일·모듈 수준으로 구체적인지 확인한다. 뭉뚱그렸으면 보강한다.
7. **보고**: 경로와 핵심 판단을 3~5줄로 요약하고, 사용자에게
   "검토 후 `status: approved` 로 바꾸면 `/run-plan` 으로 실행한다"고 안내한다.

## 신경쓸 것
- plan 은 실행자가 그대로 따라 할 수 있어야 한다. 애매한 문장은 실행 시 범위 이탈로 돌아온다.
- 이번에 **하지 않을 것**을 반드시 적는다. non-scope 가 없으면 codex 가 범위를 넓힌다.
- 검증 방법(명령어·확인 지점)을 적는다. 없으면 완료 판정이 불가능하다.
- 코드를 쓰고 싶어지면 멈춘다. 그건 plan 에 적어 codex 에 넘길 일이다.
