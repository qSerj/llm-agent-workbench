---
name: new-adr
description: Scaffold the next architecture decision record under docs/decisions/ with the correct sequential number, status line, and section structure. Invoke as /new-adr <short topic>.
disable-model-invocation: true
---

Create a new ADR for: $ARGUMENTS

## 1. Number and filename

List `docs/decisions/` and take the highest number plus one, zero-padded to four digits. Do **not** count `archive/prototype-r4.2/docs/decisions/` (0001–0002 live there and are frozen history) — but do not reuse those numbers either; numbering is continuous across both.

Filename: `docs/decisions/NNNN-slug.md`, slug in lowercase English with hyphens, matching the existing style (`0005-portable-research-bundle.md`).

## 2. Language

New ADRs are Russian, following `0006`. Use terms from `docs/GLOSSARY.ru.md`; introduce a significant term as `русский термин (english term)` on first use. Keep program names, filenames, JSON field names, and code identifiers untranslated.

## 3. Template

```markdown
# ADR NNNN: <Заголовок>

Статус: <принято | принято как направление, реализация отложена | предложено>. Дата: YYYY-MM-DD.

## Контекст

<Что происходит и почему решение вообще потребовалось. Конкретные ограничения,
а не общие рассуждения.>

## Решение

<Что именно принято. Если решение — направление без реализации, скажите это
прямо здесь, а не только в статусе.>

## Следствия

<Что теперь становится проще, что сложнее, что придётся поддерживать, и от
чего отказываемся.>
```

Use today's real date. An ADR may legitimately be accepted as a direction with implementation deferred — `0005` is the precedent.

## 4. Draft, do not invent

Fill the sections from the actual conversation and repository state. If you do not know the context or consequences, ask rather than writing plausible-sounding filler. Read the relevant stage-1 design documents and `VISION.md` first — an ADR that contradicts the stated anti-scope (no own trace store, viewer, prompt management, cost dashboard, labeling system, or execution engine) needs to address that contradiction explicitly.

## 5. After writing

If the decision changes the experiment format, update `docs/design/stage-1.md` — the single page that describes what is implemented. Mention the new ADR in `docs/CURRENT_STATE.md` if it changes the current state.

Suggested commit subject: English, imperative, 3–5 words, e.g. `Record portable research bundle decision`.
