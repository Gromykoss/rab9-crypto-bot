#!/usr/bin/env python3
"""Lint GWT card shape and pytest scenario node bindings."""

import argparse
import ast
import re
import sys
from pathlib import Path


DEFAULT_MAP_PATH = Path(__file__).with_name("scenario_map.yaml")
SCENARIO_ID_RE = re.compile(r"^[a-z0-9-]+\.[a-z0-9_]+$")
VALID_ID_IN_TICKS_RE = re.compile(r"`([a-z0-9-]+\.[a-z0-9_]+)`")
ANY_TICKS_RE = re.compile(r"`([^`]+)`")
SCENARIO_HEADER_RE = re.compile(r"^(#{3,4})\s+(.*)$")
ANY_HEADER_RE = re.compile(r"^#{1,6}\s+")
WHEN_RE = re.compile(r"^\s*-\s*(?:\*\*)?WHEN(?:\*\*)?\s*(.*)$", re.IGNORECASE)
THEN_RE = re.compile(r"^\s*-\s*(?:\*\*)?THEN(?:\*\*)?\s*(.*)$", re.IGNORECASE)
NO_CI_RE = re.compile(r"<!--\s*no-ci\s*-->", re.IGNORECASE)


def _strip_value(value):
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def fail_config(message):
    print(message, file=sys.stderr)
    raise SystemExit(3)


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

    return scenarios


def is_scenario_heading(text):
    return re.search(r"\bGIVEN\b", text, re.IGNORECASE) or "Scenario:" in text


def extract_id(heading):
    valid_match = VALID_ID_IN_TICKS_RE.search(heading)
    if valid_match:
        return valid_match.group(1), None

    tick_match = ANY_TICKS_RE.search(heading)
    if tick_match and "." in tick_match.group(1):
        return None, f"invalid scenario id format: {tick_match.group(1)}"
    return None, None


def parse_card(path):
    errors = []
    warnings = []
    scenarios = []

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return [], [f"cannot read card: {exc}"], []

    for index, line in enumerate(lines):
        match = SCENARIO_HEADER_RE.match(line)
        if not match:
            continue

        heading = match.group(2).strip()
        if not is_scenario_heading(heading):
            continue

        start_line = index + 1
        block = []
        for next_line in lines[index + 1 :]:
            if ANY_HEADER_RE.match(next_line):
                break
            block.append(next_line)

        first_non_empty = [item for item in block if item.strip()][:3]
        if NO_CI_RE.search("\n".join(first_non_empty)):
            warnings.append(f"skipped (no-ci): {heading}")
            continue

        scenario_id, id_error = extract_id(heading)
        if id_error:
            errors.append(f"{id_error}: {path}:{start_line}: {heading}")
        elif not scenario_id:
            errors.append(f"scenario without id: {path}:{start_line}: {heading}")
        elif not SCENARIO_ID_RE.fullmatch(scenario_id):
            errors.append(f"invalid scenario id format: {scenario_id}: {path}:{start_line}")

        if not re.search(r"\bGIVEN\b", heading, re.IGNORECASE):
            errors.append(f"GIVEN missing: {path}:{start_line}: {heading}")

        when_lines = []
        then_lines = []
        for body_line in block:
            when_match = WHEN_RE.match(body_line)
            if when_match:
                when_text = when_match.group(1).strip()
                when_lines.append(when_text)
                if not when_text:
                    errors.append(f"empty WHEN: {path}:{start_line}: {heading}")
            then_match = THEN_RE.match(body_line)
            if then_match:
                then_text = then_match.group(1).strip()
                then_lines.append(then_text)
                if not then_text:
                    errors.append(f"empty THEN: {path}:{start_line}: {heading}")

        if scenario_id:
            scenarios.append(
                {
                    "id": scenario_id,
                    "path": path,
                    "line": start_line,
                    "heading": heading,
                }
            )
            if not when_lines:
                errors.append(f"scenario without WHEN: {scenario_id}: {path}:{start_line}")
            if not then_lines:
                errors.append(f"scenario without THEN: {scenario_id}: {path}:{start_line}")

    return scenarios, errors, warnings


def collect_cards(specs_dir):
    if not specs_dir.is_dir():
        fail_config(f"specs_dir not found: {specs_dir}")

    per_file = {}
    all_scenarios = []
    seen = {}

    for path in sorted(specs_dir.glob("*.md"), key=lambda item: item.name):
        scenarios, errors, warnings = parse_card(path)
        per_file[path] = {"errors": errors, "warnings": warnings}
        all_scenarios.extend(scenarios)
        for scenario in scenarios:
            seen.setdefault(scenario["id"], []).append(scenario)

    for scenario_id in sorted(seen):
        locations = seen[scenario_id]
        if len(locations) < 2:
            continue
        detail = ", ".join(f"{item['path']}:{item['line']}" for item in locations)
        message = f"duplicate scenario id: {scenario_id}: {detail}"
        for item in locations:
            per_file[item["path"]]["errors"].append(message)

    return per_file, all_scenarios


def map_by_id(scenarios):
    mapped = {}
    for scenario in scenarios:
        mapped[scenario["id"]] = scenario
    return mapped


def apply_untested_warnings(per_file, card_scenarios, mapped):
    warnings = 0
    for scenario in card_scenarios:
        if scenario["id"] in mapped:
            continue
        message = f"UNTESTED: {scenario['id']}"
        per_file[scenario["path"]]["warnings"].append(message)
        warnings += 1
    return warnings


def is_scenario_mark(func):
    if not isinstance(func, ast.Attribute) or func.attr != "scenario":
        return False
    mark = func.value
    if not isinstance(mark, ast.Attribute) or mark.attr != "mark":
        return False
    pytest_name = mark.value
    if not isinstance(pytest_name, ast.Name) or pytest_name.id != "pytest":
        return False
    return True


def scenario_decorator(decorator):
    func = decorator.func if isinstance(decorator, ast.Call) else decorator
    if not is_scenario_mark(func):
        return None, None
    if not isinstance(decorator, ast.Call):
        return None, "missing call parentheses"
    if decorator.keywords:
        return None, "keywords are not allowed"
    if len(decorator.args) != 1:
        return None, "expected exactly one positional argument"
    arg = decorator.args[0]
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        return arg.value, None
    return None, "argument must be a string literal"


def collect_test_markers(path):
    try:
        source = path.read_text(encoding="utf-8")
    except OSError as exc:
        return None, [f"cannot read test file: {path}: {exc}"]
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        return None, [f"syntax error: {path}:{exc.lineno}: {exc.msg}"]

    errors = []

    class MarkerVisitor(ast.NodeVisitor):
        def __init__(self):
            self.class_stack = []
            self.markers = []

        def visit_ClassDef(self, node):
            self.class_stack.append(node.name)
            self.generic_visit(node)
            self.class_stack.pop()

        def visit_FunctionDef(self, node):
            self._visit_function(node)

        def visit_AsyncFunctionDef(self, node):
            self._visit_function(node)

        def _visit_function(self, node):
            for decorator in node.decorator_list:
                scenario_id, malformed = scenario_decorator(decorator)
                if scenario_id is None and malformed is None:
                    continue
                line = getattr(decorator, "lineno", getattr(node, "lineno", "?"))
                if malformed:
                    errors.append(f"malformed scenario marker: {path}:{line}: {malformed}")
                    continue
                self.markers.append(
                    {
                        "id": scenario_id,
                        "class": self.class_stack[-1] if self.class_stack else "",
                        "function": node.name,
                        "line": node.lineno,
                    }
                )
            self.generic_visit(node)

    visitor = MarkerVisitor()
    visitor.visit(tree)
    markers = visitor.markers
    return markers, errors


def marker_matches_node(marker, map_node, path):
    map_file, *parts = map_node.split("::")
    if Path(map_file).name != path.name:
        return False
    if not parts:
        return True
    if len(parts) == 1:
        return parts[0] in {marker["class"], marker["function"]}
    if len(parts) == 2:
        return parts[0] == marker["class"] and parts[1] == marker["function"]
    return False


def check_tests(test_paths, card_ids, mapped):
    per_file = {}
    for path in test_paths:
        per_file[path] = {"errors": [], "warnings": []}
        if not path.is_file():
            fail_config(f"test file not found: {path}")
        markers, parse_errors = collect_test_markers(path)
        per_file[path]["errors"].extend(parse_errors)
        if markers is None:
            continue
        for marker in markers:
            scenario_id = marker["id"]
            if not marker["function"].startswith("test_"):
                per_file[path]["errors"].append(
                    f"scenario marker is not on test function: {scenario_id}: {path}:{marker['line']}:{marker['function']}"
                )
            if scenario_id not in card_ids:
                per_file[path]["errors"].append(f"marker id not in any card: {scenario_id}")
            if scenario_id in mapped:
                map_node = mapped[scenario_id].get("test", "")
                if not marker_matches_node(marker, map_node, path):
                    per_file[path]["errors"].append(
                        f"marker/func mismatch for {scenario_id}: map says {map_node}, found {marker['function']} in {path}"
                    )
    return per_file


def print_file_reports(per_file):
    total_errors = 0
    total_warnings = 0
    for path in sorted(per_file, key=lambda item: str(item)):
        errors = per_file[path]["errors"]
        warnings = per_file[path]["warnings"]
        total_errors += len(errors)
        total_warnings += len(warnings)
        status = "OK" if not errors and not warnings else f"{len(errors)} errors, {len(warnings)} warnings"
        stream = sys.stderr if errors else sys.stdout
        print(f"{path}: {status}", file=stream)
        for error in errors:
            print(f"  {error}", file=sys.stderr)
        for warning in warnings:
            print(f"  {warning}", file=sys.stdout)
    return total_errors, total_warnings


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("specs_dir")
    parser.add_argument("--map", default=str(DEFAULT_MAP_PATH))
    parser.add_argument("--tests", nargs="*")
    args = parser.parse_args(argv)

    specs_dir = Path(args.specs_dir)
    map_path = Path(args.map)
    scenarios_from_map = load_map(map_path)
    mapped = map_by_id(scenarios_from_map)

    card_reports, card_scenarios = collect_cards(specs_dir)
    apply_untested_warnings(card_reports, card_scenarios, mapped)

    all_reports = dict(card_reports)
    card_ids = {scenario["id"] for scenario in card_scenarios}
    if args.tests:
        test_paths = [Path(item) for item in args.tests]
        all_reports.update(check_tests(test_paths, card_ids, mapped))

    errors, warnings = print_file_reports(all_reports)
    summary = (
        f"lint summary: {len(all_reports)} files, {len(card_scenarios)} scenarios, "
        f"{errors} errors, {warnings} warnings"
    )
    print(summary, file=sys.stderr if errors else sys.stdout)
    raise SystemExit(1 if errors else 0)


if __name__ == "__main__":
    main()
