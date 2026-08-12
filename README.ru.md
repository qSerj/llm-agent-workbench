# LLM Agent Workbench

[English version](README.md)

LLM Agent Workbench — ранний исследовательский прототип для запуска одной и
той же задачи через разные агентные модели и провайдеры с последующим
сравнением качества, времени, tool calls, токенов, стоимости API и примерного
энергопотребления локальных моделей.

Сейчас репозиторий фиксирует рабочий прототип `r4.2`, с которого начинается
развитие полноценного Workbench. Это уже полезный небольшой benchmark-runner
для OpenCode, но ещё не оболочка управления результатами из [VISION.md](VISION.md).

## Что уже работает

- LM Studio, OpenRouter и произвольные OpenAI-compatible endpoints;
- одинаковые задания и отдельный Git workspace для каждого запуска;
- ограниченные права агента: fixture доступен для чтения, изменять можно только
  `docs/**`;
- автоматическая оценка, полная JSONL-трасса, diff, status, время, tool calls,
  токены и явно сообщённая провайдером стоимость;
- оценка энергии и цены электричества по заданной средней мощности компьютера.

## Требования

- Python 3.10+ без сторонних Python-зависимостей;
- [OpenCode](https://opencode.ai/) в `PATH`;
- .NET 8 SDK для проверки C# fixture;
- CLI LM Studio (`lms`) только для локального режима LM Studio.

Ключи и авторизация настраиваются вне репозитория. Подробности находятся в
[инструкции по провайдерам](docs/providers.md).

## Быстрый старт

Проверка без обращения к моделям:

```bash
python3 run_agent.py --version
python3 -m unittest discover -s tests -v
dotnet build fixture/InterleaverBench.sln -m:1
```

Пример одного задания через OpenRouter:

```bash
python3 run_agent.py \
  --provider openrouter \
  --model openai/gpt-oss-120b:free \
  --tasks 1 \
  --tag first-run
```

Пример OpenAI-compatible endpoint:

```bash
python3 run_agent.py \
  --provider compatible \
  --provider-id local \
  --base-url http://127.0.0.1:8090/v1 \
  --model GigaChat-3-Ultra \
  --tasks 1,2,3
```

Передавайте точный model ID, который отдаёт ваш провайдер. Все параметры:
`python3 run_agent.py --help`.

## Результаты и метрики

Запуски сохраняются в `agent_runs/<timestamp>_<provider>_<model>/`. Для каждого
задания остаются prompt, фактическая модель, `opencode.jsonl`, метаданные
завершения, Git diff/status, оценка grader и полный workspace. Итог по запуску
записывается в `run_summary.json`.

У tool call нет единой цены в токенах: обычно оплачивается следующий inference,
куда вместе с историей и инструкциями попадает результат инструмента. Поэтому
runner сохраняет наблюдаемые step-метрики, а не придумывает цену для `read` или
`grep`. Если OpenCode не сообщил стоимость, она остаётся `null`. Энергия —
расчётная величина, а не показание датчика. Подробнее: [телеметрия](docs/telemetry.md).

## Куда развивается проект

Тег `prototype-r4.2` — историческая исходная точка, не стабильный релиз.
Ближайший этап — практическое сравнение готовых open-source систем для
экспериментов, tracing и evaluation. Прототип не рефакторируется, пока эта
проверка не покажет, какой небольшой интеграционный слой действительно нужен.

См. [VISION.md](VISION.md), [протокол bake-off](docs/research/bakeoff-protocol.md),
[обзор инструментов](docs/research/tool-landscape.md) и
[заметки об orchestration](docs/orchestration.md).
Правила разработки описаны в [AGENTS.md](AGENTS.md). Лицензия — [MIT](LICENSE).
