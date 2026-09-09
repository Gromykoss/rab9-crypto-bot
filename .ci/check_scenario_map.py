#!/usr/bin/env python3
"""Validate GWT scenario bindings and changed-file coverage."""

import argparse
import fnmatch
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAP_PATH = Path(__file__).with_name("scenario_map.yaml")
SCENARIO_ID_RE = re.compile(r"^[a-z0-9-]+\.[a-z0-9_]+$")
CARD_ID_RE = re.compile(r"^#{2,4}\s.*`([a-z0-9-]+\.[a-z0-9_]+)`\s*$")
TEST_ID_RE = re.compile(r'@pytest\.mark\.scenario\("([a-z0-9-]+\.[a-z0-9_]+)"\)')
SCENARIO_HEADER_RE = re.compile(r"^#{3,4}\s+.*$")
ANY_HEADER_RE = re.compile(r"^#{1,6}\s+")
NO_CI_RE = re.compile(r"<!--\s*no-ci\s*-->", re.IGNORECASE)

# Repo-level/meta outputs are intentionally outside scenario ownership.
# Domain implementation/spec/test/fixture files must still be present in the map.
WHITELIST = (
    "CHRONOLOGY.md",
    "PROJECT_MEMORY_GRAPH.md",
    "spec_drift_log.md",
    "briefings/**",
    "knowledge_graph/**",
    "docs/**",
    ".ci/scenario_map.yaml",
    ".ci/run_affected.py",
    ".ci/check_scenario_map.py",
    ".ci/lint_gwt_cards.py",
    ".github/workflows/gwt.yml",
    "pytest.ini",
)


def _strip_value(value):
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def fail_config(message):
    print(message, file=sys.stderr)
    raise SystemExit(3)


def fail_check(lines):
    if isinstance(lines, str):
        print(lines, file=sys.stderr)
    else:
        for line in lines:
            print(line, file=sys.stderr)
    raise SystemExit(1)


def load_map(path):
    if not path.exists():
        fail_config(f"scenario map not found: {path}")

    scenarios = []
    seen_ids = set()
    current = None
    current_list = None

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        fail_config(f"cannot read scenario map {path}: {exc}")

    for line_no, raw_line in enumerate(lines, 1):
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue

        if not raw_line.startswith(" ") and raw_line.endswith(":"):
            scenario_id = raw_line[:-1].strip()
            if not SCENARIO_ID_RE.fullmatch(scenario_id):
                fail_config(f"invalid scenario id at line {line_no}: {scenario_id}")
            if scenario_id in seen_ids:
                fail_config(f"duplicate scenario id: {scenario_id} (line {line_no})")
            seen_ids.add(scenario_id)
            current = {"id": scenario_id, "code": []}
            scenarios.append(current)
            current_list = None
            continue

        if current is None:
            fail_config(f"nested key before scenario at line {line_no}")

        stripped = raw_line.strip()
        if stripped.startswith("- "):
            if current_list is None:
                fail_config(f"list item without list key at line {line_no}")
            current[current_list].append(_strip_value(stripped[2:]))
            continue

        if ":" not in stripped:
            fail_config(f"unsupported line {line_no}: {raw_line}")

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
            fail_config(f"unsupported key at line {line_no}: {key}")

    if not scenarios:
        fail_config(f"scenario map is empty: {path}")

    validate_entries(scenarios)
    return scenarios


def validate_entries(scenarios):
    for scenario in scenarios:
        scenario_id = scenario["id"]
        for key in ("card", "test"):
            if not scenario.get(key):
                fail_config(f"{scenario_id}: missing {key}")
        if not scenario.get("code"):
            fail_config(f"{scenario_id}: code must be a non-empty list")

        card_path = ROOT / scenario["card"]
        if not card_path.is_file():
            fail_config(f"{scenario_id}: card file not found: {scenario['card']}")

        test_file = scenario["test"].split("::", 1)[0]
        if not (ROOT / test_file).is_file():
            fail_config(f"{scenario_id}: test file not found: {test_file}")

        for key in ("card", "test", "fixture"):
            value = scenario.get(key)
            if value and ".." in Path(value).parts:
                fail_config(f"{scenario_id}: mapped {key} path contains '..': {value}")
        for code_path in scenario.get("code", []):
            if ".." in Path(code_path).parts:
                fail_config(f"{scenario_id}: mapped code path contains '..': {code_path}")
            if not (ROOT / code_path).is_file():
                fail_config(f"{scenario_id}: code file not found: {code_path}")
        fixture = scenario.get("fixture")
        if fixture and not (ROOT / fixture).is_file():
            fail_config(f"{scenario_id}: fixture file not found: {fixture}")


def collect_card_ids(scenarios):
    ids = set()
    for card in sorted({scenario["card"] for scenario in scenarios}):
        path = ROOT / card
        lines = path.read_text(encoding="utf-8").splitlines()
        for index, line in enumerate(lines):
            match = CARD_ID_RE.search(line)
            if match:
                block = []
                for next_line in lines[index + 1 :]:
                    if ANY_HEADER_RE.match(next_line):
                        break
                    block.append(next_line)
                first_non_empty = [item for item in block if item.strip()][:3]
                if NO_CI_RE.search("\n".join(first_non_empty)):
                    continue
                ids.add(match.group(1))
    return ids


def collect_test_ids(scenarios):
    ids = set()
    for test_file in sorted({scenario["test"].split("::", 1)[0] for scenario in scenarios}):
        path = ROOT / test_file
        for match in TEST_ID_RE.finditer(path.read_text(encoding="utf-8")):
            ids.add(match.group(1))
    return ids


def check_three_way_binding(scenarios):
    map_ids = {scenario["id"] for scenario in scenarios}
    card_ids = collect_card_ids(scenarios)
    test_ids = collect_test_ids(scenarios)

    problems = []
    comparisons = (
        ("in map but not in card", map_ids - card_ids),
        ("in card but not in map", card_ids - map_ids),
        ("in map but not in tests", map_ids - test_ids),
        ("in tests but not in map", test_ids - map_ids),
        ("in card but not in tests", card_ids - test_ids),
        ("in tests but not in card", test_ids - card_ids),
    )
    for label, diff in comparisons:
        if diff:
            problems.append(f"{label}: {', '.join(sorted(diff))}")

    if problems:
        fail_check(["scenario id binding mismatch:"] + problems)


def run_git(args):
    proc = subprocess.run(
        ["git", "-c", "core.quotePath=false", *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        message = proc.stderr.strip() or proc.stdout.strip()
        fail_config(f"git {' '.join(args)} failed: {message}")
    return proc.stdout


def changed_files(base):
    output = run_git(["diff", "--name-only", f"{base}..HEAD"])
    return [line.strip() for line in output.splitlines() if line.strip()]


def whitelisted(path):
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in WHITELIST)


def mapped_paths(scenarios):
    paths = set()
    for scenario in scenarios:
        paths.add(scenario["card"])
        paths.add(scenario["test"])
        paths.add(scenario["test"].split("::", 1)[0])
        paths.update(scenario.get("code", []))
        if scenario.get("fixture"):
            paths.add(scenario["fixture"])
    return paths


def check_diff_coverage(scenarios, changed, base):
    covered = mapped_paths(scenarios)
    uncovered = [
        path
        for path in changed
        if not whitelisted(path)
        and path not in covered
        and not (
            path.startswith("openspec/specs/")
            and path.endswith(".md")
            and changes_only_no_ci(base, path)
        )
    ]
    if uncovered:
        fail_check(["files outside mapped domains and whitelist:"] + [f"  {path}" for path in uncovered])


def commit_messages_for_path(base, path):
    return run_git(["log", "--format=%B", f"{base}..HEAD", "--", path])


def changed_content_lines(base, path):
    output = run_git(["diff", f"{base}..HEAD", "--", path])
    lines = []
    for line in output.splitlines():
        if line.startswith(("+++", "---")):
            continue
        if not line.startswith(("+", "-")):
            continue
        text = line[1:].strip()
        if text:
            lines.append(text)
    return lines


def no_ci_block_lines(path):
    card_path = ROOT / path
    try:
        lines = card_path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        fail_config(f"cannot read card {path}: {exc}")

    no_ci_lines = set()
    for index, line in enumerate(lines):
        if not SCENARIO_HEADER_RE.match(line):
            continue
        heading = line.strip()
        block = []
        for next_line in lines[index + 1 :]:
            if ANY_HEADER_RE.match(next_line):
                break
            block.append(next_line)
        first_non_empty = [item for item in block if item.strip()][:3]
        if not NO_CI_RE.search("\n".join(first_non_empty)):
            continue
        no_ci_lines.add(heading)
        no_ci_lines.update(item.strip() for item in block if item.strip())
    return no_ci_lines


def changes_only_no_ci(base, path):
    changed_lines = changed_content_lines(base, path)
    if not changed_lines:
        return False
    allowed_lines = no_ci_block_lines(path)
    return bool(allowed_lines) and all(line in allowed_lines for line in changed_lines)


def check_card_change_rule(scenarios, changed, base):
    changed_set = set(changed)
    changed_cards = {scenario["card"] for scenario in scenarios if scenario["card"] in changed_set}
    if not changed_cards:
        return

    test_by_card = {}
    for scenario in scenarios:
        test_by_card.setdefault(scenario["card"], set()).add(scenario["test"].split("::", 1)[0])

    changed_tests = {
        scenario["test"].split("::", 1)[0]
        for scenario in scenarios
        if scenario["test"].split("::", 1)[0] in changed_set or scenario["test"] in changed_set
    }
    problems = []
    for card in sorted(changed_cards):
        if changes_only_no_ci(base, card):
            continue
        if test_by_card.get(card, set()) & changed_tests:
            continue
        messages = commit_messages_for_path(base, card)
        has_override = any(line.strip() == "tests update: not needed" for line in messages.splitlines())
        if has_override:
            continue
        problems.append(f"{card}: card changed without domain test change or 'tests update: not needed'")

    if problems:
        fail_check(["card-change rule violation:"] + problems)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True, help="base commit for base..HEAD checks")
    args = parser.parse_args(argv)

    scenarios = load_map(MAP_PATH)
    check_three_way_binding(scenarios)
    changed = changed_files(args.base)
    check_diff_coverage(scenarios, changed, args.base)
    check_card_change_rule(scenarios, changed, args.base)

    print(f"scenario map completeness OK: {len(scenarios)} scenarios, {len(changed)} changed files")


if __name__ == "__main__":
    main()
