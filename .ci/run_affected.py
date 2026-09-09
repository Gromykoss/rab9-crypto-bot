#!/usr/bin/env python3
"""Print GWT scenario tests affected by changed files.

Scenario ids must be unique. A scenario is affected by its card, fixture,
watched code paths, or its own pytest node/file path.
"""

import argparse
import sys
from pathlib import Path


MAP_PATH = Path(__file__).with_name("scenario_map.yaml")


def _strip_value(value):
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def load_map(path):
    if not path.exists():
        print(f"scenario map not found: {path}", file=sys.stderr)
        raise SystemExit(3)

    scenarios = []
    seen_ids = set()
    current = None
    current_list = None

    for line_no, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue

        if not raw_line.startswith(" ") and raw_line.endswith(":"):
            scenario_id = raw_line[:-1].strip()
            if scenario_id in seen_ids:
                print(f"duplicate scenario id: {scenario_id} (line {line_no})", file=sys.stderr)
                raise SystemExit(2)
            seen_ids.add(scenario_id)
            current = {"id": scenario_id, "code": []}
            scenarios.append(current)
            current_list = None
            continue

        if current is None:
            raise ValueError(f"nested key before scenario at line {line_no}")

        stripped = raw_line.strip()
        if stripped.startswith("- "):
            if current_list is None:
                raise ValueError(f"list item without list key at line {line_no}")
            current[current_list].append(_strip_value(stripped[2:]))
            continue

        if ":" not in stripped:
            raise ValueError(f"unsupported line {line_no}: {raw_line}")

        key, value = stripped.split(":", 1)
        key = key.strip()
        value = value.strip()
        if key == "code":
            current["code"] = []
            current_list = "code"
        elif key in {"card", "test", "fixture"}:
            current[key] = _strip_value(value)
            current_list = None
        else:
            raise ValueError(f"unsupported key at line {line_no}: {key}")

    return scenarios


def affected_tests(scenarios, changed):
    changed_set = set(changed)
    for scenario in scenarios:
        watched = set(scenario.get("code", []))
        watched.add(scenario["test"])
        watched.add(scenario["test"].split("::", 1)[0])
        for key in ("card", "fixture"):
            if scenario.get(key):
                watched.add(scenario[key])
        if watched & changed_set:
            yield scenario["test"]


def main(argv=None):
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--changed", nargs="*")
    group.add_argument("--all", action="store_true")
    args = parser.parse_args(argv)

    scenarios = load_map(MAP_PATH)
    tests = (scenario["test"] for scenario in scenarios) if args.all else affected_tests(scenarios, args.changed)

    for test in tests:
        print(test)


if __name__ == "__main__":
    main()
