#!/usr/bin/env python3
"""Print latest client report path; optionally open index.html in browser."""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from origenlab_email_pipeline.config import load_settings


def _is_wsl() -> bool:
    try:
        with open("/proc/version", encoding="utf-8", errors="ignore") as f:
            return "microsoft" in f.read().lower()
    except OSError:
        return False


def _open_via_windows(html: Path) -> bool:
    """WSL: open HTML in Windows default browser (Linux has no HTML handler)."""
    html = html.resolve()
    try:
        r = subprocess.run(
            ["wslpath", "-w", str(html)],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        win_path = (r.stdout or "").strip()
        if not win_path:
            return False
        subprocess.Popen(
            ["cmd.exe", "/c", "start", "", win_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.CalledProcessError):
        return False


def _open_html(html: Path) -> bool:
    """Open HTML file in default browser; return True if opened."""
    if sys.platform == "win32":
        subprocess.run(["cmd", "/c", "start", "", html.resolve().as_uri()], check=False)
        return True
    if sys.platform == "darwin":
        subprocess.run(["open", html.resolve().as_uri()], check=False)
        return True
    if _is_wsl() and _open_via_windows(html):
        return True
    for cmd in ("wslview", "xdg-open"):
        if shutil.which(cmd):
            try:
                subprocess.run([cmd, html.resolve().as_uri()], check=False)
                return True
            except OSError:
                pass
    try:
        return bool(webbrowser.open(html.resolve().as_uri()))
    except Exception:
        return False


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--open", action="store_true", help="Open index.html in default browser")
    ap.add_argument("--overview", action="store_true", help="Open overview.html (run summary + links) instead of report")
    ap.add_argument("--list", type=int, default=0, metavar="N", help="List N newest folders")
    args = ap.parse_args()

    root = load_settings().resolved_reports_dir()
    if not root.is_dir():
        print("No reports dir yet:", root)
        print("Run: uv run python scripts/reports/generate_client_report.py --fast --name test")
        sys.exit(1)

    # Overview mode: open run_*/overview.html (newest first)
    if args.overview:
        overviews = [
            p / "overview.html"
            for p in root.iterdir()
            if p.is_dir() and p.name.startswith("run_") and (p / "overview.html").is_file()
        ]
        overviews.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        if not overviews:
            print("No overview.html found. Run: WITH_EMBEDDINGS=1 bash scripts/reports/run_all.sh")
            sys.exit(1)
        html = overviews[0]
        print("Latest overview:", html)
        if args.open:
            if _open_html(html):
                print("(opened in default browser)")
            else:
                wp = ""
                if _is_wsl():
                    try:
                        wp = subprocess.run(
                            ["wslpath", "-w", str(html.resolve())],
                            capture_output=True, text=True, timeout=5, check=True,
                        ).stdout.strip()
                    except Exception:
                        pass
                print("Open manually:", html.resolve(), file=sys.stderr)
                if wp:
                    print("  Windows:", wp, file=sys.stderr)
        return

    # Report dirs: direct children with index.html, or run_*/client_report (run_all.sh)
    candidates: list[Path] = []
    for p in root.iterdir():
        if not p.is_dir():
            continue
        if (p / "index.html").is_file():
            candidates.append(p)
        if p.name.startswith("run_") and (p / "client_report" / "index.html").is_file():
            candidates.append(p / "client_report")
    dirs = sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True)
    if not dirs:
        print("No report folders with index.html under:", root)
        sys.exit(1)

    if args.list:
        for p in dirs[: args.list]:
            print(p)
        return

    latest = dirs[0]
    html = latest / "index.html"
    print("Latest report:")
    print(" ", html)
    print("\nFolder:", latest)
    if args.open:
        opened = _open_html(html)
        if opened:
            print("(opened in default browser)")
        if not opened:
            win_hint = ""
            if _is_wsl():
                try:
                    wp = subprocess.run(
                        ["wslpath", "-w", str(html.resolve())],
                        capture_output=True,
                        text=True,
                        timeout=5,
                        check=True,
                    ).stdout.strip()
                    if wp:
                        win_hint = f"\n  Windows path (paste in Explorer address bar):\n  {wp}"
                except Exception:
                    pass
            print("\nOpen the report manually:", file=sys.stderr)
            print(" ", html.resolve(), file=sys.stderr)
            print(win_hint, file=sys.stderr)
            print(
                "  Or in Cursor: File → Open File… → pick index.html",
                file=sys.stderr,
            )


if __name__ == "__main__":
    main()
