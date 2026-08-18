#!/usr/bin/env python3
"""Скрытый набор проверок к примеру wrap-defect.

Исполнитель этого файла не видит: набор накладывается поверх копии рабочего
пространства уже после прогона (`workbench/suite.py`). Проверяется ровно то, что
записано в договоре `README.md` рабочего пространства, — поведение, а не
устройство: любая правильная реализация должна пройти набор целиком.

Печатает один объект JSON на stdout и ничего больше.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable

WIDTH_CASES = [
    ("раз два три четыре пять шесть семь восемь", 12),
    ("a bb ccc dddd eeeee ffffff", 7),
    ("одно", 4),
]


def check_width_is_respected(wrap: object) -> tuple[bool, str]:
    for text, width in WIDTH_CASES:
        for line in wrap.wrap_text(text, width).split("\n"):
            if len(line) > width and " " in line:
                return False, f"строка длиннее {width}: {line!r}"
    return True, "ни одна строка не превышает ширину"


def check_exact_fit_stays(wrap: object) -> tuple[bool, str]:
    """Пункт 2: слово, помещающееся вплотную, не переносится."""
    result = wrap.wrap_text("раз два", 7)
    if result != "раз два":
        return False, f"строка ровно в ширину разорвана: {result!r}"
    result = wrap.wrap_text("aaa bbb ccc", 7)
    if result != "aaa bbb\nccc":
        return False, f"ожидалось 'aaa bbb\\nccc', получено {result!r}"
    return True, "слово, помещающееся вплотную, остаётся на строке"


def check_long_word_is_not_broken(wrap: object) -> tuple[bool, str]:
    result = wrap.wrap_text("кот длинноесловокотороенепомещается пёс", 6)
    if "длинноесловокотороенепомещается" not in result.split("\n"):
        return False, f"длинное слово разорвано или потеряно: {result!r}"
    return True, "длинное слово занимает свою строку целиком"


def check_paragraph_break_is_kept(wrap: object) -> tuple[bool, str]:
    """Пункт 4: пустая строка между абзацами остаётся пустой строкой."""
    result = wrap.wrap_text("раз два\n\nтри четыре", 12)
    if result != "раз два\n\nтри четыре":
        return False, f"разделение абзацев потеряно: {result!r}"
    return True, "абзацы разделены пустой строкой"


def check_paragraph_count_is_kept(wrap: object) -> tuple[bool, str]:
    text = "первый абзац тут\n\nвторой абзац тут\n\nтретий абзац тут"
    result = wrap.wrap_text(text, 10)
    paragraphs = [item for item in result.split("\n\n") if item.strip()]
    if len(paragraphs) != 3:
        return False, f"абзацев на выходе {len(paragraphs)}, а не 3: {result!r}"
    return True, "три абзаца на входе, три на выходе"


def check_spaces_are_tidied(wrap: object) -> tuple[bool, str]:
    result = wrap.wrap_text("раз    два\nтри", 20)
    if result != "раз два три":
        return False, f"пробелы не приведены в порядок: {result!r}"
    return True, "подряд идущие пробелы схлопнуты"


def check_no_edge_spaces(wrap: object) -> tuple[bool, str]:
    for text, width in WIDTH_CASES:
        for line in wrap.wrap_text(text, width).split("\n"):
            if line != line.strip():
                return False, f"строка с краевым пробелом: {line!r}"
    return True, "ни одна строка не начинается и не заканчивается пробелом"


def check_words_are_preserved(wrap: object) -> tuple[bool, str]:
    text = "раз два три\n\nчетыре пять шесть семь"
    result = wrap.wrap_text(text, 9)
    if result.split() != text.split():
        return False, f"последовательность слов изменилась: {result!r}"
    return True, "слова не потеряны и не добавлены"


def check_width_below_one_is_rejected(wrap: object) -> tuple[bool, str]:
    """Пункт 7: невозможную ширину нельзя молча подменить своей."""
    for width in (0, -3):
        try:
            wrap.wrap_text("раз два", width)
        except ValueError:
            continue
        except Exception as error:
            return False, f"ширина {width}: поднято {type(error).__name__}, а не ValueError"
        return False, f"ширина {width} принята вместо ValueError"
    return True, "ширина меньше единицы поднимает ValueError"


def check_empty_text(wrap: object) -> tuple[bool, str]:
    result = wrap.wrap_text("", 10)
    if result != "":
        return False, f"пустой текст дал {result!r}"
    return True, "пустой текст даёт пустую строку"


CHECKS: list[tuple[str, Callable[[object], tuple[bool, str]]]] = [
    ("width-is-respected", check_width_is_respected),
    ("exact-fit-stays", check_exact_fit_stays),
    ("long-word-is-not-broken", check_long_word_is_not_broken),
    ("paragraph-break-is-kept", check_paragraph_break_is_kept),
    ("paragraph-count-is-kept", check_paragraph_count_is_kept),
    ("spaces-are-tidied", check_spaces_are_tidied),
    ("no-edge-spaces", check_no_edge_spaces),
    ("words-are-preserved", check_words_are_preserved),
    ("width-below-one-is-rejected", check_width_below_one_is_rejected),
    ("empty-text", check_empty_text),
]


def main() -> None:
    try:
        import wrap
    except Exception as error:
        # Измерить поведение нечем. Это не «не пройдено», это «неизвестно».
        print(
            json.dumps(
                {
                    "checks": [
                        {
                            "id": name,
                            "outcome": "UNDETERMINED",
                            "rationale": f"wrap.py не импортируется: {error}",
                        }
                        for name, _ in CHECKS
                    ]
                },
                ensure_ascii=False,
            )
        )
        return

    checks = []
    for name, check in CHECKS:
        try:
            ok, rationale = check(wrap)
            outcome = "PASS" if ok else "FAIL"
        except Exception as error:
            outcome = "FAIL"
            rationale = f"{type(error).__name__}: {error}"
        checks.append({"id": name, "outcome": outcome, "rationale": rationale})
    print(json.dumps({"checks": checks}, ensure_ascii=False))


if __name__ == "__main__":
    sys.exit(main())
