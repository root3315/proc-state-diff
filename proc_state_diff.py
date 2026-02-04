#!/usr/bin/env python3
"""
proc-state-diff: Compare and visualize process state snapshots.

Captures the current system process list, saves it to a JSON file,
and can later compare two snapshots to report added, removed, and
changed processes.
"""

import argparse
import json
import os
import signal
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_HISTORY_FILE = ".proc_state_diff_history.json"


def capture_snapshot():
    """Capture the current process state using ps aux."""
    try:
        result = subprocess.run(
            ["ps", "aux", "--no-headers"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except FileNotFoundError:
        print("ERROR: 'ps' command not found. This tool requires a Linux/macOS system.", file=sys.stderr)
        sys.exit(1)
    except subprocess.TimeoutExpired:
        print("ERROR: 'ps' command timed out.", file=sys.stderr)
        sys.exit(1)

    if result.returncode != 0:
        print(f"ERROR: 'ps' failed: {result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)

    processes = {}
    for line in result.stdout.strip().splitlines():
        parts = line.split(None, 10)
        if len(parts) < 11:
            continue
        pid = parts[1]
        cmd = parts[10]
        proc_info = {
            "user": parts[0],
            "pid": int(pid),
            "cpu": float(parts[2]),
            "mem": float(parts[3]),
            "vsz": int(parts[4]),
            "rss": int(parts[5]),
            "tty": parts[6],
            "stat": parts[7],
            "start": parts[8],
            "time": parts[9],
            "command": cmd,
            "full_line": line,
        }
        processes[pid] = proc_info

    snapshot = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "hostname": os.uname().nodename,
        "process_count": len(processes),
        "processes": processes,
    }
    return snapshot


def save_snapshot(snapshot, filepath):
    """Save a snapshot dict to a JSON file."""
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(snapshot, f, indent=2)
    return path


def load_snapshot(filepath):
    """Load a snapshot dict from a JSON file."""
    path = Path(filepath)
    if not path.exists():
        print(f"ERROR: Snapshot file not found: {filepath}", file=sys.stderr)
        sys.exit(1)
    with open(path, "r") as f:
        return json.load(f)


def compare_snapshots(old, new, ignore_cpu=False, ignore_mem=False):
    """
    Compare two snapshots and return a diff report dict.
    """
    old_procs = old.get("processes", {})
    new_procs = new.get("processes", {})

    old_pids = set(old_procs.keys())
    new_pids = set(new_procs.keys())

    added_pids = sorted(new_pids - old_pids, key=lambda p: int(p))
    removed_pids = sorted(old_pids - new_pids, key=lambda p: int(p))
    common_pids = old_pids & new_pids

    changed = []
    for pid in sorted(common_pids, key=lambda p: int(p)):
        old_p = old_procs[pid]
        new_p = new_procs[pid]
        diffs = []

        for field in ["user", "cpu", "mem", "vsz", "rss", "tty", "stat", "start", "time", "command"]:
            if ignore_cpu and field == "cpu":
                continue
            if ignore_mem and field in ("mem", "vsz", "rss"):
                continue
            old_val = old_p.get(field)
            new_val = new_p.get(field)
            if old_val != new_val:
                diffs.append({
                    "field": field,
                    "old": old_val,
                    "new": new_val,
                })

        if diffs:
            changed.append({
                "pid": pid,
                "command": new_p.get("command", "?"),
                "changes": diffs,
            })

    report = {
        "old_timestamp": old.get("timestamp", "unknown"),
        "new_timestamp": new.get("timestamp", "unknown"),
        "old_hostname": old.get("hostname", "unknown"),
        "new_hostname": new.get("hostname", "unknown"),
        "old_process_count": old.get("process_count", 0),
        "new_process_count": new.get("process_count", 0),
        "added": [new_procs[pid] for pid in added_pids],
        "removed": [old_procs[pid] for pid in removed_pids],
        "changed": changed,
        "summary": {
            "added_count": len(added_pids),
            "removed_count": len(removed_pids),
            "changed_count": len(changed),
        },
    }
    return report


def format_report(report, verbose=False, color=True):
    """Format a diff report into a human-readable string."""
    lines = []

    def _c(text, code):
        if not color:
            return text
        codes = {"green": "32", "red": "31", "yellow": "33", "cyan": "36", "bold": "1"}
        return f"\033[{codes.get(code, '0')}m{text}\033[0m"

    lines.append("=" * 70)
    lines.append(_c("PROCESS STATE DIFF REPORT", "bold"))
    lines.append("=" * 70)
    lines.append(f"  Snapshot A: {report['old_timestamp']}  (host: {report['old_hostname']})")
    lines.append(f"  Snapshot B: {report['new_timestamp']}  (host: {report['new_hostname']})")
    lines.append("")

    summary = report["summary"]
    lines.append(f"  Total in A: {report['old_process_count']}")
    lines.append(f"  Total in B: {report['new_process_count']}")
    lines.append(f"  {_c('Added:    ' + str(summary['added_count']), 'green')}")
    lines.append(f"  {_c('Removed:  ' + str(summary['removed_count']), 'red')}")
    lines.append(f"  {_c('Changed:  ' + str(summary['changed_count']), 'yellow')}")
    lines.append("")

    if summary["added_count"] > 0:
        lines.append("-" * 70)
        lines.append(_c("ADDED PROCESSES", "green"))
        lines.append("-" * 70)
        for p in report["added"]:
            lines.append(f"  PID {p['pid']:>6}  {p['user']:<10}  CPU:{p['cpu']:>5}  MEM:{p['mem']:>5}  {p['command']}")
        lines.append("")

    if summary["removed_count"] > 0:
        lines.append("-" * 70)
        lines.append(_c("REMOVED PROCESSES", "red"))
        lines.append("-" * 70)
        for p in report["removed"]:
            lines.append(f"  PID {p['pid']:>6}  {p['user']:<10}  CPU:{p['cpu']:>5}  MEM:{p['mem']:>5}  {p['command']}")
        lines.append("")

    if summary["changed_count"] > 0:
        lines.append("-" * 70)
        lines.append(_c("CHANGED PROCESSES", "yellow"))
        lines.append("-" * 70)
        for entry in report["changed"]:
            lines.append(f"  PID {entry['pid']:>6}  {entry['command']}")
            for change in entry["changes"]:
                old_str = str(change["old"])
                new_str = str(change["new"])
                if verbose or change["field"] in ("command", "stat"):
                    lines.append(f"    {change['field']}: {_c(old_str, 'red')} -> {_c(new_str, 'green')}")
            lines.append("")

    if summary["added_count"] == 0 and summary["removed_count"] == 0 and summary["changed_count"] == 0:
        lines.append(_c("  No differences detected.", "cyan"))
        lines.append("")

    return "\n".join(lines)


def load_history(history_file):
    """Load the change history from a JSON file."""
    path = Path(history_file)
    if not path.exists():
        return {"runs": []}
    with open(path, "r") as f:
        return json.load(f)


def save_history(history, history_file):
    """Save the change history to a JSON file."""
    with open(history_file, "w") as f:
        json.dump(history, f, indent=2)


def cmd_capture(args):
    """Handle the 'capture' subcommand."""
    snapshot = capture_snapshot()
    filepath = save_snapshot(snapshot, args.output)
    print(f"Captured {snapshot['process_count']} processes -> {filepath}")
    if args.quiet:
        return
    print(f"  Timestamp: {snapshot['timestamp']}")
    print(f"  Hostname:  {snapshot['hostname']}")


def cmd_diff(args):
    """Handle the 'diff' subcommand."""
    old_snap = load_snapshot(args.snapshot_a)
    new_snap = load_snapshot(args.snapshot_b)
    report = compare_snapshots(
        old_snap, new_snap,
        ignore_cpu=args.ignore_cpu,
        ignore_mem=args.ignore_mem,
    )
    output = format_report(report, verbose=args.verbose, color=not args.no_color)
    print(output)

    if args.json:
        json_path = args.json
        save_snapshot(report, json_path)
        print(f"JSON report saved to {json_path}")


def cmd_track(args):
    """Handle the 'track' subcommand: capture and auto-compare against previous snapshot."""
    history_file = args.history if args.history else DEFAULT_HISTORY_FILE
    history = load_history(history_file)

    new_snap = capture_snapshot()

    if history["runs"]:
        last_run = history["runs"][-1]
        old_snap = last_run.get("snapshot")
        if old_snap is None:
            print("ERROR: Previous snapshot data missing from history. Cannot compare.", file=sys.stderr)
            sys.exit(1)

        report = compare_snapshots(
            old_snap, new_snap,
            ignore_cpu=args.ignore_cpu,
            ignore_mem=args.ignore_mem,
        )
        output = format_report(report, verbose=args.verbose, color=not args.no_color)
        print(output)

        run_entry = {
            "timestamp": new_snap["timestamp"],
            "hostname": new_snap["hostname"],
            "process_count": new_snap["process_count"],
            "summary": report["summary"],
        }
        if args.keep_snapshots:
            run_entry["snapshot"] = new_snap
        if args.output:
            snap_path = save_snapshot(new_snap, args.output)
            run_entry["snapshot_file"] = str(snap_path)
    else:
        print(f"Captured {new_snap['process_count']} processes (baseline run).")
        print(f"  Timestamp: {new_snap['timestamp']}")
        print(f"  Hostname:  {new_snap['hostname']}")
        print("Run again to see a comparison.")

        run_entry = {
            "timestamp": new_snap["timestamp"],
            "hostname": new_snap["hostname"],
            "process_count": new_snap["process_count"],
            "summary": None,
        }
        if args.keep_snapshots:
            run_entry["snapshot"] = new_snap
        if args.output:
            snap_path = save_snapshot(new_snap, args.output)
            run_entry["snapshot_file"] = str(snap_path)

    history["runs"].append(run_entry)

    if args.max_history and len(history["runs"]) > args.max_history:
        history["runs"] = history["runs"][-args.max_history:]

    save_history(history, history_file)
    print(f"  History updated -> {history_file}")


def cmd_history(args):
    """Handle the 'history' subcommand: view tracked change history."""
    history_file = args.history if args.history else DEFAULT_HISTORY_FILE
    history = load_history(history_file)

    if not history["runs"]:
        print("No tracked runs found.")
        return

    runs = history["runs"]
    if args.last:
        runs = runs[-args.last:]

    lines = []
    lines.append("=" * 70)
    lines.append("PROCESS STATE CHANGE HISTORY")
    lines.append("=" * 70)

    for i, run in enumerate(runs):
        lines.append("")
        ts = run.get("timestamp", "unknown")
        host = run.get("hostname", "unknown")
        count = run.get("process_count", "?")
        lines.append(f"  Run {i + 1}: {ts}  (host: {host}, processes: {count})")

        summary = run.get("summary")
        if summary:
            lines.append(f"    Added: {summary['added_count']}  |  Removed: {summary['removed_count']}  |  Changed: {summary['changed_count']}")
        else:
            lines.append("    (baseline — no comparison)")

        snap_file = run.get("snapshot_file")
        if snap_file:
            lines.append(f"    Snapshot file: {snap_file}")

    lines.append("")
    print("\n".join(lines))


def cmd_list_snapshots(args):
    """Handle the 'list' subcommand: show recent snapshots in a directory."""
    snap_dir = Path(args.directory)
    if not snap_dir.is_dir():
        print(f"ERROR: Directory not found: {snap_dir}", file=sys.stderr)
        sys.exit(1)

    snaps = sorted(snap_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not snaps:
        print(f"No JSON snapshot files found in {snap_dir}")
        return

    print(f"{'File':<50} {'Processes':>10}  {'Timestamp'}")
    print("-" * 90)
    for snap_file in snaps[:30]:
        try:
            with open(snap_file, "r") as f:
                data = json.load(f)
            ts = data.get("timestamp", "n/a")
            count = data.get("process_count", "?")
            print(f"{snap_file.name:<50} {count:>10}  {ts}")
        except (json.JSONDecodeError, KeyError):
            print(f"{snap_file.name:<50} {'(invalid)':>10}  -")


def main():
    parser = argparse.ArgumentParser(
        prog="proc-state-diff",
        description="Compare and visualize process state snapshots.",
    )
    subparsers = parser.add_subparsers(dest="command")

    # capture
    cap_parser = subparsers.add_parser("capture", help="Capture current process state to a JSON file")
    cap_parser.add_argument("-o", "--output", default="snapshot.json", help="Output file path (default: snapshot.json)")
    cap_parser.add_argument("-q", "--quiet", action="store_true", help="Suppress metadata output")
    cap_parser.set_defaults(func=cmd_capture)

    # diff
    diff_parser = subparsers.add_parser("diff", help="Compare two snapshots")
    diff_parser.add_argument("snapshot_a", help="First snapshot file (baseline)")
    diff_parser.add_argument("snapshot_b", help="Second snapshot file (comparison)")
    diff_parser.add_argument("-v", "--verbose", action="store_true", help="Show all changed fields")
    diff_parser.add_argument("--ignore-cpu", action="store_true", help="Ignore CPU changes")
    diff_parser.add_argument("--ignore-mem", action="store_true", help="Ignore memory changes")
    diff_parser.add_argument("--no-color", action="store_true", help="Disable color output")
    diff_parser.add_argument("--json", metavar="FILE", help="Also save the diff report as JSON")
    diff_parser.set_defaults(func=cmd_diff)

    # track
    track_parser = subparsers.add_parser("track", help="Capture and auto-compare against previous snapshot")
    track_parser.add_argument("-o", "--output", help="Save snapshot to this file path")
    track_parser.add_argument("--history", help=f"History file path (default: {DEFAULT_HISTORY_FILE})")
    track_parser.add_argument("-v", "--verbose", action="store_true", help="Show all changed fields")
    track_parser.add_argument("--ignore-cpu", action="store_true", help="Ignore CPU changes")
    track_parser.add_argument("--ignore-mem", action="store_true", help="Ignore memory changes")
    track_parser.add_argument("--no-color", action="store_true", help="Disable color output")
    track_parser.add_argument("--keep-snapshots", action="store_true", help="Keep full snapshot data in history file")
    track_parser.add_argument("--max-history", type=int, default=50, help="Maximum number of runs to keep (default: 50)")
    track_parser.set_defaults(func=cmd_track)

    # history
    hist_parser = subparsers.add_parser("history", help="View tracked change history")
    hist_parser.add_argument("--history", help=f"History file path (default: {DEFAULT_HISTORY_FILE})")
    hist_parser.add_argument("--last", type=int, help="Show only the last N runs")
    hist_parser.set_defaults(func=cmd_history)

    # list
    list_parser = subparsers.add_parser("list", help="List snapshot files in a directory")
    list_parser.add_argument("-d", "--directory", default=".", help="Directory to scan (default: current dir)")
    list_parser.set_defaults(func=cmd_list_snapshots)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
