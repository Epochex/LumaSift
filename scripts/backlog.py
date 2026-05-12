from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BACKLOG_PATH = ROOT / "docs" / "backlog.json"
PRIORITY_LABELS = {0: "P0", 1: "P1", 2: "P2", 3: "P3"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Read and update the LumaSift executable backlog.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("next", help="Show the next ready backlog item.")
    subparsers.add_parser("goal", help="Show product goal path and the next ready item.")
    subparsers.add_parser("list", help="List backlog items.")

    status_parser = subparsers.add_parser("set-status", help="Set backlog item status.")
    status_parser.add_argument("item_id")
    status_parser.add_argument("status", choices=["todo", "in_progress", "blocked", "done"])

    args = parser.parse_args()
    backlog = load_backlog()

    if args.command == "next":
        item = next_ready_item(backlog)
        if item is None:
            print("No ready backlog item.")
            return 1
        print(format_item(item))
        return 0

    if args.command == "goal":
        goal_path = ROOT / "GOAL.md"
        print(f"GOAL: {goal_path}")
        print(f"BACKLOG: {BACKLOG_PATH}")
        print()
        item = next_ready_item(backlog)
        if item is None:
            print("No ready backlog item.")
            return 1
        print(format_item(item))
        return 0

    if args.command == "list":
        for item in sorted_items(backlog):
            deps = ",".join(item.get("dependencies", [])) or "-"
            print(
                f"{item['id']} {priority_label(item)} {item['status']} "
                f"deps={deps} area={item.get('area', '-')} :: {item['title']}"
            )
        return 0

    if args.command == "set-status":
        set_status(backlog, args.item_id, args.status)
        save_backlog(backlog)
        print(f"{args.item_id} -> {args.status}")
        return 0

    return 2


def load_backlog() -> dict[str, Any]:
    with BACKLOG_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_backlog(backlog: dict[str, Any]) -> None:
    temp_path = BACKLOG_PATH.with_suffix(".json.tmp")
    with temp_path.open("w", encoding="utf-8") as handle:
        json.dump(backlog, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    temp_path.replace(BACKLOG_PATH)


def sorted_items(backlog: dict[str, Any]) -> list[dict[str, Any]]:
    return sorted(
        backlog.get("items", []),
        key=lambda item: (int(item.get("priority", 99)), str(item.get("id", ""))),
    )


def next_ready_item(backlog: dict[str, Any]) -> dict[str, Any] | None:
    done_ids = {item["id"] for item in backlog.get("items", []) if item.get("status") == "done"}
    for item in sorted_items(backlog):
        if item.get("status") != "todo":
            continue
        dependencies = set(item.get("dependencies", []))
        if dependencies.issubset(done_ids):
            return item
    return None


def set_status(backlog: dict[str, Any], item_id: str, status: str) -> None:
    for item in backlog.get("items", []):
        if item.get("id") == item_id:
            item["status"] = status
            return
    raise SystemExit(f"Unknown backlog item: {item_id}")


def priority_label(item: dict[str, Any]) -> str:
    return PRIORITY_LABELS.get(int(item.get("priority", 99)), f"P{item.get('priority')}")


def format_item(item: dict[str, Any]) -> str:
    lines = [
        f"{item['id']} {priority_label(item)} {item['title']}",
        f"status: {item['status']}",
        f"area: {item.get('area', '-')}",
        f"dependencies: {', '.join(item.get('dependencies', [])) or '-'}",
        f"rationale: {item.get('rationale', '-')}",
        "acceptance:",
    ]
    lines.extend(f"- {entry}" for entry in item.get("acceptance", []))
    if item.get("risk"):
        lines.append(f"risk: {item['risk']}")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
