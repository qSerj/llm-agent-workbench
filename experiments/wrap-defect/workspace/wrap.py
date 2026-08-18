"""Перенос текста по ширине.

Договор описан в README.md рядом. Модуль ничего не импортирует: он должен
работать на голом стандартном Python 3.
"""

from __future__ import annotations


def wrap_text(text: str, width: int) -> str:
    """Разложить текст по строкам не длиннее width символов."""
    if width < 1:
        width = 1
    lines: list[str] = []
    for paragraph in text.split("\n\n"):
        current = ""
        for word in paragraph.split():
            if not current:
                current = word
            elif len(current) + 1 + len(word) >= width:
                lines.append(current)
                current = word
            else:
                current = current + " " + word
        if current:
            lines.append(current)
    return "\n".join(lines)
