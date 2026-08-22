# moracano — backend

JunctionX Korea 2026 · 경상북도 방언 Dialect Root 플랫폼의 백엔드/AI 분석 서비스.
기획·문제정의·아키텍처는 `docs/spec.md` 참고.

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
- NO body lines, NO co-authoring yourself. NO mentioning session in commit

## Progress Log

- Keep a running log of work in `docs/progress.md` — AI 분석 파이프라인 작업은 대신
  `docs/ai/progress.md`에 남긴다(현재 AI 쪽 작업은 마무리돼 새 항목이 드물 것).
- One dated section per work session (`## YYYY-MM-DD — short title`), newest at the bottom.
- Each entry: what was done, key results (tables/numbers where relevant), and a `### Next` list of
  what's left. This is the backup of "what Claude did" across sessions — write it so a fresh session
  (or teammate) can pick up context without re-reading the whole diff history.
