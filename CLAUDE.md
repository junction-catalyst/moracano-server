# moracano — AI

경상북도 방언 Dialect Root 생성 AI 모듈. 녹음된 음성에서 음절 분할·프로소디(피치/길이/리듬)를 추출하고,
규칙 기반 라벨링·Similar Voices 매칭·PCA 뿌리 방향 좌표를 계산해 백엔드(`/api/voices/{id}/analyze`)에
붙는 분석 서비스를 담당한다.

# Workflow

## Collaboration

### Code Styles

- Use modern language features
- Limit lines to 120 characters maximum.
- Prefer pure functions where possible.
- NEVER write docstrings, function descriptions, or line-by-line comments.
- Only add inline comments to explain the *why* of non-obvious business logic, not the *what* of the code.
- 사전학습 모델은 항상 특징추출기(zero-shot)로만 쓴다 — 이 프로젝트 범위에서 새로 학습/파인튜닝하는 모델은 없다.

### Commit Template

`<category>: <short_summary>`

- categories: 'feat', 'fix', 'refactor', 'docs', 'test', 'chore', 'perf'
- example: `feat: add threshold-based label generation`
- **70 chars max**, imperative, English only
- NO body lines, NO co-authoring yourself.

## Progress Log

- Keep a running log of work in `docs/progress.md`.
- One dated section per work session (`## YYYY-MM-DD — short title`), newest at the bottom.
- Each entry: what was done, key results (tables/numbers where relevant), and a `### Next` list of
  what's left. This is the backup of "what Claude did" across sessions — write it so a fresh session
  (or teammate) can pick up context without re-reading the whole diff history.
