#!/usr/bin/env python3
"""Validate an execution envelope and export its projection over OTLP/HTTP."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from workbench.otel_projection import project_to_otel


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("envelope", type=Path)
    parser.add_argument(
        "--endpoint",
        required=True,
        help="OTLP/HTTP traces endpoint, for example http://127.0.0.1:4318/v1/traces",
    )
    parser.add_argument("--correlated-output", type=Path)
    args = parser.parse_args()

    try:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    except ImportError as error:
        raise SystemExit("OTLP projection requires the optional research environment") from error

    envelope = json.loads(args.envelope.read_text(encoding="utf-8"))
    provider = TracerProvider(
        resource=Resource.create({"service.name": "llm-agent-workbench"})
    )
    provider.add_span_processor(
        SimpleSpanProcessor(OTLPSpanExporter(endpoint=args.endpoint))
    )
    trace_id, span_id = project_to_otel(
        envelope, provider.get_tracer("llm-agent-workbench.envelope-v1")
    )
    provider.shutdown()
    correlated = json.loads(json.dumps(envelope))
    correlated["correlations"].extend(
        [
            {"system": "opentelemetry", "kind": "trace_id", "value": trace_id},
            {"system": "opentelemetry", "kind": "span_id", "value": span_id},
        ]
    )
    if args.correlated_output:
        args.correlated_output.write_text(
            json.dumps(correlated, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(f"OTel trace/span: {trace_id}/{span_id}")


if __name__ == "__main__":
    main()
