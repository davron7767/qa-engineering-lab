"""Summarise JUnit XML files as a Markdown table (used for the GitHub Actions job summary).

Usage: python scripts/junit_summary.py <title> <junit.xml> [<junit.xml> ...]
Numbers come straight from the reports; nothing is estimated.
"""

import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def totals(path: Path) -> dict[str, float]:
    root = ET.parse(path).getroot()  # noqa: S314
    suites = [root] if root.tag == "testsuite" else root.findall("testsuite")
    result = {"tests": 0.0, "failures": 0.0, "errors": 0.0, "skipped": 0.0, "time": 0.0}
    for suite in suites:
        for key in result:
            result[key] += float(suite.get(key, 0) or 0)
    return result


def main() -> None:
    title, *files = sys.argv[1:]
    print(f"### {title}\n")
    print("| Report | Tests | Passed | Failed | Errors | Skipped | Time (s) |")
    print("|---|---:|---:|---:|---:|---:|---:|")
    for name in files:
        path = Path(name)
        if not path.exists():
            print(f"| {path.name} | report missing | | | | | |")
            continue
        t = totals(path)
        passed = t["tests"] - t["failures"] - t["errors"] - t["skipped"]
        print(
            f"| {path.name} | {t['tests']:.0f} | {passed:.0f} | {t['failures']:.0f} "
            f"| {t['errors']:.0f} | {t['skipped']:.0f} | {t['time']:.1f} |"
        )


if __name__ == "__main__":
    main()
