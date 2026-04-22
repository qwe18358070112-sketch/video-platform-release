from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path


TOKEN_RE = re.compile(r"GetClientTicket log (?:push back|map_context_token_ insert): (?P<token>[A-Fa-f0-9]{32,})")
SERVICE_RE = re.compile(
    r'"componentId":"(?P<component>[^"]+)".+?"serviceType":"(?P<service>[^"]+)"',
    re.S,
)
TS_FORMAT = "%Y-%m-%d %H:%M:%S.%f"


def parse_ts(line: str) -> datetime | None:
    if len(line) < 23:
        return None
    raw = line[:23]
    try:
        return datetime.strptime(raw, TS_FORMAT)
    except ValueError:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze clientframe auth/service context timing.")
    parser.add_argument("log_path", help="Path to clientframework.clientframe.debug.log")
    parser.add_argument("--date-prefix", default="", help="Optional YYYY-MM-DD prefix filter")
    parser.add_argument("--tail-lines", type=int, default=15000, help="How many trailing lines to inspect")
    parser.add_argument("--output", default="", help="Optional JSON output path")
    args = parser.parse_args()

    log_path = Path(args.log_path)
    lines = log_path.read_text(encoding="utf-8", errors="ignore").splitlines()[-args.tail_lines :]

    token_events: list[tuple[datetime, str]] = []
    service_events: list[tuple[datetime, str, str]] = []

    for line in lines:
        if args.date_prefix and not line.startswith(args.date_prefix):
            continue
        timestamp = parse_ts(line)
        if timestamp is None:
            continue

        token_match = TOKEN_RE.search(line)
        if token_match:
            token_events.append((timestamp, token_match.group("token")))

        service_match = SERVICE_RE.search(line)
        if service_match:
            service_events.append((timestamp, service_match.group("component"), service_match.group("service")))

    summary: dict[str, dict[str, object]] = defaultdict(lambda: {"events": 0, "candidateTokens": []})
    for event_time, component, service in service_events:
        key = f"{component}:{service}"
        summary[key]["events"] = int(summary[key]["events"]) + 1
        ranked: list[tuple[float, str]] = []
        for token_time, token in token_events:
            delta = (event_time - token_time).total_seconds()
            if 0 <= delta <= 12:
                ranked.append((abs(delta), token))
            else:
                after = (token_time - event_time).total_seconds()
                if 0 <= after <= 2:
                    ranked.append((abs(after) + 0.25, token))
        ordered: list[str] = []
        for _, token in sorted(ranked, key=lambda item: item[0]):
            if token not in ordered:
                ordered.append(token)
            if len(ordered) >= 6:
                break
        if ordered:
            summary[key]["candidateTokens"] = ordered

    result = {
        "generatedAt": datetime.now().isoformat(timespec="seconds"),
        "logPath": str(log_path.resolve()),
        "datePrefix": args.date_prefix,
        "serviceSummaries": summary,
    }

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
