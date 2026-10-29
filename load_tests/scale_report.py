"""Turn the scale experiment's raw output into one results table.

Runs inside the Locust container (scripts/scale_test.sh calls it), so nothing
needs to be installed on the host.

    python scale_report.py summarize results/1-copy   # one run -> results/1-copy.summary.json
    python scale_report.py report results                # all runs -> results/scale-report.md
"""

import csv
import json
import sys
from pathlib import Path

RUN_ORDER = ["1-copy", "3-copies", "3-copies-pgbouncer"]


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as file:
        return list(csv.DictReader(file))


def number(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def summarize(prefix: str) -> None:
    """Numbers for one run. Locust ran with --reset-stats, so they only cover the time
    after every simulated user had started (no ramp-up, almost no logins)."""
    totals = {row["Name"]: row for row in read_rows(Path(f"{prefix}_stats.csv"))}
    overall = totals["Aggregated"]
    failure_rows = read_rows(Path(f"{prefix}_failures.csv"))
    failure_rows.sort(key=lambda row: -int(row["Occurrences"]))
    summary = {
        "requests_per_second": round(float(overall["Requests/s"]), 1),
        "p50_ms": number(overall["50%"]),
        "p95_ms": number(overall["95%"]),
        "p99_ms": number(overall["99%"]),
        "total_requests": int(overall["Request Count"]),
        "total_failures": int(overall["Failure Count"]),
        "booking_p95_ms": number(totals.get("POST /api/bookings", {}).get("95%")),
        "top_errors": [
            f'{row["Occurrences"]}x {row["Name"]}: {row["Error"][:120]}' for row in failure_rows[:3]
        ],
    }
    Path(f"{prefix}.summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary))


def load_json(path: Path) -> dict:
    return json.loads(path.read_text()) if path.exists() else {}


def report(results_dir: str) -> None:
    folder = Path(results_dir)
    lines = [
        "| Run | API copies (1 CPU each) | Requests/s | p50 | p95 | p99 | Failed requests | "
        "Peak Postgres connections | Connections refused by Postgres | API CPU | Race test (100 at once) |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    notes = []
    for name in RUN_ORDER:
        summary = load_json(folder / f"{name}.summary.json")
        if not summary:
            continue
        extra = load_json(folder / f"{name}.extra.json")
        race = load_json(folder / f"{name}.race.json")
        failed_percent = 100 * summary["total_failures"] / max(summary["total_requests"], 1)
        race_text = "not run"
        if race:
            verdict = "correct" if race.get("correct") else "DOUBLE BOOKING"
            errors = sum(race.get("other", {}).values())
            error_text = f", {errors} failed (HTTP {', '.join(race['other'])})" if errors else ""
            race_text = (
                f'{verdict}: {race["status_201"]} booked, {race["status_409"]} told "just taken"'
                f"{error_text}, spread over {len(race['requests_per_instance'])} copies"
            )
        lines.append(
            f'| {name} | {extra.get("replicas", "?")} | {summary["requests_per_second"]} | '
            f'{summary["p50_ms"]:.0f} ms | {summary["p95_ms"]:.0f} ms | {summary["p99_ms"]:.0f} ms | '
            f'{summary["total_failures"]} of {summary["total_requests"]} ({failed_percent:.2f}%) | '
            f'{extra.get("peak_connections", "?")} of {extra.get("max_connections", "?")} | '
            f'{extra.get("refused_connections", "?")} | {extra.get("api_cpu", "?")} | {race_text} |'
        )
        for error in summary["top_errors"]:
            notes.append(f"- {name}: {error}")

    text = "\n".join(lines) + "\n"
    if notes:
        text += "\nMost common failures:\n\n" + "\n".join(notes) + "\n"
    first = load_json(folder / f"{RUN_ORDER[0]}.extra.json")
    # Was one copy really overloaded? Waiting time is the clearest sign: when requests
    # queue, the median latency jumps far above what an idle copy needs.
    one = load_json(folder / f"{RUN_ORDER[0]}.summary.json")
    many = load_json(folder / f"{RUN_ORDER[1]}.summary.json")
    many_extra = load_json(folder / f"{RUN_ORDER[1]}.extra.json")
    if one and one.get("p50_ms") is not None and one["p50_ms"] < 50:
        text += (
            f"\n**Note:** one copy still answered in {one['p50_ms']:.0f} ms (median), so it was not "
            "overloaded and the comparison says little. Run again with more users, e.g. "
            "`USERS=2500 bash scripts/scale_test.sh`.\n"
        )
    many_cpu = number(str(many_extra.get("api_cpu", "")).rstrip("%"))
    if many and many.get("p50_ms") is not None and many["p50_ms"] < 50 and many_cpu is not None:
        text += (
            f"\n**Note:** {many_extra.get('replicas', 3)} copies still answered in {many['p50_ms']:.0f} ms (median) "
            f"at {many_cpu:.0f}% CPU each, so they served all the load the simulated users created "
            f"({many['requests_per_second']} requests/s) "
            "and their real limit is higher. To find it, run again with more users, e.g. "
            "`USERS=2500 DURATION=180 bash scripts/scale_test.sh`.\n"
        )
    text += (
        f'\nSetup: {first.get("users", "?")} simulated patients per '
        f'{first.get("duration_seconds", "?")} second run, '
        "measured after all of them had started (Locust --reset-stats); logins are not part of it. "
        '"Connections refused" counts PostgreSQL "sorry, too many clients already" errors. '
        "A request that fails that way is a capacity problem, not a double booking. "
        f'Host: {first.get("host", "?")}. "API CPU" is the average per copy during the run; '
        "near 100% means the copies were the bottleneck, as intended.\n"
    )
    (folder / "scale-report.md").write_text(text)
    print(text)


if __name__ == "__main__":
    if sys.argv[1] == "summarize":
        summarize(sys.argv[2])
    else:
        report(sys.argv[2])
