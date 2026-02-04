# proc-state-diff

Compare and visualize process state snapshots to track what changed between runs.

## Overview

`proc-state-diff` captures the current system process list (via `ps aux`), saves it to a JSON file, and can later compare two snapshots to report **added**, **removed**, and **changed** processes.

Useful for:
- Debugging what spawned or died between two points in time.
- Monitoring resource usage shifts (CPU, memory) per process.
- Auditing command-line changes in running processes.

## Requirements

- Python 3.6+
- Linux or macOS (requires the `ps` command)
- No external dependencies

## Installation

Clone or copy the project directory. No `pip install` step is needed — the tool runs directly.

```bash
git clone <repo-url>
cd proc-state-diff
```

## Usage

### Capture a snapshot

```bash
python3 proc_state_diff.py capture -o before.json
```

Run it again later to get a second snapshot:

```bash
python3 proc_state_diff.py capture -o after.json
```

### Compare two snapshots

```bash
python3 proc_state_diff.py diff before.json after.json
```

This prints a color-coded report showing:

- **Added processes** — PIDs present in the second snapshot but not the first.
- **Removed processes** — PIDs that existed in the first but not the second.
- **Changed processes** — PIDs in both snapshots whose attributes differ.

### Options

| Flag | Description |
|---|---|
| `-v, --verbose` | Show every changed field (by default only `command` and `stat` are shown in detail) |
| `--ignore-cpu` | Exclude CPU% from comparison |
| `--ignore-mem` | Exclude memory fields (MEM%, VSZ, RSS) from comparison |
| `--no-color` | Disable ANSI color codes |
| `--json FILE` | Save the structured diff report as JSON |

### List saved snapshots

```bash
python3 proc_state_diff.py list -d /path/to/snapshots
```

Displays the most recent 30 JSON snapshot files in the given directory with their timestamps and process counts.

## Example session

```bash
# Capture baseline
python3 proc_state_diff.py capture -o snap1.json

# ... do some work, start/stop services ...

# Capture second state
python3 proc_state_diff.py capture -o snap2.json

# See what changed
python3 proc_state_diff.py diff snap1.json snap2.json -v
```

## Output format

The diff report includes a summary header followed by three sections:

```
======================================================================
PROCESS STATE DIFF REPORT
======================================================================
  Snapshot A: 2026-04-14T10:00:00+00:00  (host: myserver)
  Snapshot B: 2026-04-14T10:05:00+00:00  (host: myserver)

  Total in A: 142
  Total in B: 148
  Added:    6
  Removed:  2
  Changed:  8
----------------------------------------------------------------------
ADDED PROCESSES
----------------------------------------------------------------------
  PID   4821  www-data    CPU:  1.2  MEM:  3.4  /usr/sbin/apache2 -k start
  ...
----------------------------------------------------------------------
CHANGED PROCESSES
----------------------------------------------------------------------
  PID   1234  python3 app.py
    cpu: 0.5 -> 12.3
    mem: 1.2 -> 4.8
    ...
```

## JSON snapshot structure

Each captured snapshot is a JSON object:

```json
{
  "timestamp": "2026-04-14T10:00:00+00:00",
  "hostname": "myserver",
  "process_count": 142,
  "processes": {
    "1": {
      "user": "root",
      "pid": 1,
      "cpu": 0.0,
      "mem": 0.3,
      "vsz": 169312,
      "rss": 11420,
      "tty": "?",
      "stat": "Ss",
      "start": "Apr13",
      "time": "0:03",
      "command": "/sbin/init"
    }
  }
}
```

## License

MIT
