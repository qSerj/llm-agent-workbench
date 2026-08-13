# Prior Model and Agent Observations

Snapshot recorded on 2026-08-13 from the project owner's earlier benchmark
runs. These are preliminary empirical observations, not a reproducible public
leaderboard: most original raw bundles are not committed, provider model
versions can change, and the deterministic grader does not detect every factual
error. The later preserved GPT-OSS run is documented separately in the
[legacy import report](legacy-opencode-results-2026-08-12.md).

## Experimental Context

The original benchmark asked an OpenCode agent to inspect a synthetic C#
repository and create evidence-based documentation under `docs/**` without
changing source files. The runner recorded wall time, tool calls, reported
tokens and cost, grading, and optional estimated local energy. Agent performance
depends on repeated model/tool cycles, search discipline, and grounding—not
only single-prompt generation speed.

Two Linux machines established opposite local-inference profiles:

- **Work machine:** 48 GB RAM and GTX 960 2 GB. The GPU may be active for the
  desktop, but is not practically useful for these LLMs; runs are effectively
  CPU-bound. Approximate generation speeds were GPT-OSS 20B 6–7 tok/s,
  Nemotron 3 Nano 30B-A3B 6.9 tok/s, Gemma 4 12B 2.3 tok/s, Qwen3.6 27B
  1.1 tok/s, and Gemma 4 31B 0.84 tok/s.
- **Home machine:** i5-13600KF, 64 GB RAM, RTX 4070 Ti SUPER 16 GB. GPT-OSS
  20B reached roughly 157 tok/s in a non-agent generation benchmark with high
  GPU offload. A later complete OpenCode Task 1 took 14.46 seconds, scored
  16/16, but contained an unsupported usage example.

## Historical Task 1 Results

| Candidate | Execution | Grade | Wall time | Tools | Preliminary assessment |
| --- | --- | ---: | ---: | ---: | --- |
| GPT-OSS 20B | work CPU | 16/16 | 31:15 | 23 | Capable but impractically slow and search-inefficient |
| DeepSeek V4 Flash | OpenRouter | 16/16 | 4:42 | 19 | Careful and self-correcting; promising reviewer |
| Xiaomi MiMo v2.5 | OpenRouter | 16/16 | 1:09 | 15 | Fast worker; one factual error survived grading |
| GLM-4.7 Flash | OpenRouter | 16/16 | 3:33 | 17 | Useful, but prone to extending hardware semantics |
| GigaChat-3-Ultra | GigaChat/gpt2giga | 16/16 | 0:35 | 8 | Most compact grounded traversal in this group |
| GigaChat-2-Max | GigaChat/gpt2giga | 9/16 | 1:34 | 7 | Delegated poorly grounded subtasks that hallucinated |
| GigaChat-2-Pro | GigaChat/gpt2giga | 5/16 | 0:12 | 1 | Did not inspect the repository and invented a C++ project |

Reported OpenRouter costs for the small task were approximately $0.0027 for
MiMo v2.5, $0.0032 for GLM-4.7 Flash, and $0.0055 for DeepSeek V4 Flash. These
figures are useful observations, not current tariffs or linear estimates for a
large repository.

## Candidate Characteristics

- **GPT-OSS 20B:** sufficient capability and constraint following, but many
  extra searches and reads. Local utility is dominated by hardware; privacy or
  unattended batch work is a stronger justification than assumed zero cost.
- **DeepSeek V4 Flash:** the most even early cloud candidate. It re-read source
  and corrected its own wording, making it a plausible verifier.
- **MiMo v2.5:** direct and economical, but claimed both `ToRegisters()`
  implementations create a new array although one returns `_delays`. Treat as
  an efficient worker whose output requires review.
- **GLM-4.7 Flash:** generally capable, but explored irrelevant Go/Rust paths
  and described transport writes as hardware behavior beyond the evidence.
- **GigaChat-3-Ultra:** quickly located the interface, implementations, usage,
  and controller with few tool calls. It is the strongest early candidate for
  fast agentic execution, subject to broader cases and repetitions.
- **GigaChat-2-Max:** spontaneously demonstrated planner/worker delegation, but
  workers interpreted “profile” as a user profile and invented ID, email, and
  picture fields. Multi-agent structure amplified a grounding failure.
- **GigaChat-2-Pro:** unsuitable for this agentic coding case based on the
  observed run.

## Working Shortlist and Lessons

MiMo is the provisional cheap worker, DeepSeek V4 Flash the careful
solver/reviewer, and GigaChat-3-Ultra the strong fast agent. GPT-OSS remains a
local candidate where hardware and privacy justify it. This is role routing,
not a permanent model ranking.

The next meaningful comparisons are `solver → reviewer → fixer` and a strong
planner with cheaper workers plus a strong verifier. Worker instructions must
include exact artifacts or symbols, scope, evidence requirements, and acceptance
criteria. The GigaChat Max failure shows that decomposition alone does not add
quality.

Evaluation must combine formal grading, factual/source review, tool efficiency,
wall time, reported API cost, local resource use, and failed attempts. A 16/16
grade is one signal, not proof of factual correctness. On the work machine,
OpenRouter and GigaChat are the practical default; slow local inference is an
explicit experimental or privacy choice.
