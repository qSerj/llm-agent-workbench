# Языковой опыт: Terra и Sonnet

Второй круг опыта `language-token-cost`: та же фикстура, эквивалентные русская
и английская постановки, скрытые проверки и пять повторов. Изменяется только
модель: GPT-5.6 Terra или Claude Sonnet 4.6.

Запуск:

```bash
.research-env/bin/python3 tools/run_chain.py \
  experiments/language-token-cost-frontier/experiment.yaml
```

Парная сводка после прогона:

```bash
python3 experiments/language-token-cost/analyze.py RUN_DIRECTORY \
  --ru terra-ru --en terra-en
python3 experiments/language-token-cost/analyze.py RUN_DIRECTORY \
  --ru sonnet-ru --en sonnet-en
```

Оба сравнения также входят в общую страницу оболочки `/series` вместе с
сериями Mimo и Opus.

## Прогон 2026-08-31

Все 20 исполнений получили `suite: PASS`, 10 из 10 проверок. Terra стоила
$0,399807 за десять исполнений, Sonnet — $0,767124; вся серия — $1,166930.

| модель и метрика | EN, среднее | RU, среднее | отношение средних RU/EN | медиана пар RU/EN |
|---|---:|---:|---:|---:|
| Terra `output_tokens` | 1 117,6 | 1 136,6 | 1,017 | 1,070 |
| Terra `reasoning_tokens` | 114,0 | 182,0 | 1,596 | 1,149 |
| Terra `total_tokens` | 35 745,4 | 36 247,8 | 1,014 | 1,015 |
| Terra стоимость, $ | 0,039262 | 0,040699 | 1,037 | 1,040 |
| Terra время, с | 51,6 | 220,1 | 4,266 | 2,282 |
| Sonnet `output_tokens` | 1 667,6 | 1 934,0 | 1,160 | 1,132 |
| Sonnet `cache_read_tokens` | 29 423,0 | 45 716,2 | 1,554 | 1,286 |
| Sonnet `total_tokens` | 41 095,2 | 58 144,2 | 1,415 | 1,208 |
| Sonnet стоимость, $ | 0,071353 | 0,082071 | 1,150 | 1,080 |
| Sonnet время, с | 101,8 | 109,9 | 1,079 | 0,752 |

Terra почти не показала языкового эффекта по токенам и цене, но три русских
исполнения имели долгие паузы, поэтому время выросло непропорционально. У Sonnet
русский дал на 41,5% больше общих токенов, главным образом из-за cache read, но
только на 15,0% большую цену: кэшированные токены дешевле обычных.

Провайдеры разложили токены иначе, чем Mimo: почти весь контекст Terra и Sonnet
оказался в `cache_read_tokens` и `cache_write_tokens`, а обычный `input_tokens`
равен единицам. Поэтому между моделями следует сравнивать прежде всего
`total_tokens` и фактическую стоимость, а не одно поле `input_tokens`.
