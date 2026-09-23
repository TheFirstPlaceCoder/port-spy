#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import signal
import subprocess
import sys
from dataclasses import asdict, dataclass
from typing import Iterable


@dataclass
class PortInfo:
    protocol: str
    local_address: str
    port: int
    state: str
    pid: int | None
    process: str | None = None
    command: str | None = None


def run_command(command: list[str]) -> str:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        return result.stdout.strip()
    except OSError:
        return ""


def parse_endpoint(endpoint: str) -> tuple[str, int] | None:
    endpoint = endpoint.strip()

    # IPv6 in [::1]:8080 form
    match = re.match(r"^\[(.*)\]:(\d+)$", endpoint)
    if match:
        return match.group(1), int(match.group(2))

    # Typical IPv4 / IPv6 netstat form: 127.0.0.1:8080, 0.0.0.0:80, [::]:443
    if ":" in endpoint:
        address, port_text = endpoint.rsplit(":", 1)
        if port_text.isdigit():
            return address, int(port_text)

    return None


def process_details_windows(pid: int) -> tuple[str | None, str | None]:
    # PowerShell is present on supported Windows versions and gives us both
    # process name and command line without external Python dependencies
    script = (
        f"$p = Get-CimInstance Win32_Process -Filter \"ProcessId={pid}\";"
        "if ($p) {"
        "[PSCustomObject]@{Name=$p.Name; CommandLine=$p.CommandLine} "
        "| ConvertTo-Json -Compress"
        "}"
    )
    output = run_command(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script]
    )
    if not output:
        return None, None

    try:
        data = json.loads(output)
        return data.get("Name"), data.get("CommandLine")
    except json.JSONDecodeError:
        return None, None


def process_details_unix(pid: int) -> tuple[str | None, str | None]:
    name = run_command(["ps", "-p", str(pid), "-o", "comm="]) or None
    command = run_command(["ps", "-p", str(pid), "-o", "args="]) or None
    return name, command


def process_details(pid: int | None) -> tuple[str | None, str | None]:
    if pid is None:
        return None, None

    if os.name == "nt":
        return process_details_windows(pid)

    return process_details_unix(pid)


def connections_windows(port: int) -> list[PortInfo]:
    output = run_command(["netstat", "-ano"])
    results: list[PortInfo] = []

    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        parts = line.split()
        if not parts:
            continue

        protocol = parts[0].upper()
        if protocol not in {"TCP", "UDP"}:
            continue

        if protocol == "TCP":
            if len(parts) < 5:
                continue
            local_endpoint = parts[1]
            state = parts[3]
            pid_text = parts[4]
        else:
            if len(parts) < 4:
                continue
            local_endpoint = parts[1]
            state = "BOUND"
            pid_text = parts[3]

        parsed = parse_endpoint(local_endpoint)
        if not parsed:
            continue

        address, found_port = parsed
        if found_port != port:
            continue

        try:
            pid = int(pid_text)
        except ValueError:
            pid = None

        name, command = process_details(pid)

        results.append(
            PortInfo(
                protocol=protocol,
                local_address=address,
                port=found_port,
                state=state,
                pid=pid,
                process=name,
                command=command,
            )
        )

    return deduplicate(results)


def connections_linux(port: int) -> list[PortInfo]:
    if shutil.which("ss"):
        output = run_command(["ss", "-H", "-lntup"])
        results: list[PortInfo] = []

        for raw_line in output.splitlines():
            parts = raw_line.split()
            if len(parts) < 5:
                continue

            protocol_raw = parts[0].lower()
            if not (protocol_raw.startswith("tcp") or protocol_raw.startswith("udp")):
                continue

            protocol = "TCP" if protocol_raw.startswith("tcp") else "UDP"
            state = parts[1].upper()
            local_endpoint = parts[4]

            parsed = parse_endpoint(local_endpoint)
            if not parsed:
                continue

            address, found_port = parsed
            if found_port != port:
                continue

            match = re.search(r'pid=(\d+)', raw_line)
            pid = int(match.group(1)) if match else None
            name, command = process_details(pid)

            results.append(
                PortInfo(
                    protocol=protocol,
                    local_address=address,
                    port=found_port,
                    state=state,
                    pid=pid,
                    process=name,
                    command=command,
                )
            )

        return deduplicate(results)

    return connections_lsof(port)


def connections_lsof(port: int) -> list[PortInfo]:
    if not shutil.which("lsof"):
        return []

    output = run_command(
        ["lsof", "-nP", f"-iTCP:{port}", f"-iUDP:{port}"]
    )

    results: list[PortInfo] = []

    for index, raw_line in enumerate(output.splitlines()):
        if index == 0 or not raw_line.strip():
            continue

        parts = raw_line.split()
        if len(parts) < 9:
            continue

        process_name = parts[0]

        try:
            pid = int(parts[1])
        except ValueError:
            pid = None

        endpoint = parts[8]
        state = "BOUND"

        if len(parts) >= 10 and parts[-1].startswith("(") and parts[-1].endswith(")"):
            state = parts[-1].strip("()")

        protocol = "TCP" if "TCP" in raw_line else "UDP"

        endpoint = endpoint.split("->", 1)[0]
        parsed = parse_endpoint(endpoint)

        if parsed:
            address, found_port = parsed
        else:
            address, found_port = "*", port

        if found_port != port:
            continue

        _, command = process_details(pid)

        results.append(
            PortInfo(
                protocol=protocol,
                local_address=address,
                port=found_port,
                state=state,
                pid=pid,
                process=process_name,
                command=command,
            )
        )

    return deduplicate(results)


def find_connections(port: int) -> list[PortInfo]:
    system = platform.system().lower()

    if system == "windows":
        return connections_windows(port)

    if system == "linux":
        return connections_linux(port)

    if system == "darwin":
        return connections_lsof(port)

    raise RuntimeError(f"Unsupported operating system: {platform.system()}")


def deduplicate(items: Iterable[PortInfo]) -> list[PortInfo]:
    seen: set[tuple] = set()
    result: list[PortInfo] = []

    for item in items:
        key = (
            item.protocol,
            item.local_address,
            item.port,
            item.state,
            item.pid,
        )
        if key not in seen:
            seen.add(key)
            result.append(item)

    return result


def kill_process(pid: int) -> None:
    if pid <= 0:
        raise RuntimeError("Cannot terminate this process.")

    if os.name == "nt":
        result = subprocess.run(
            ["taskkill", "/PID", str(pid), "/F"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if result.returncode != 0:
            message = result.stderr.strip() or result.stdout.strip()
            raise RuntimeError(message or f"Could not terminate PID {pid}.")
        return

    try:
        os.kill(pid, signal.SIGTERM)
    except PermissionError as exc:
        raise RuntimeError(
            f"Permission denied while terminating PID {pid}. "
            "Try running PortSpy with elevated permissions."
        ) from exc
    except ProcessLookupError as exc:
        raise RuntimeError(f"PID {pid} no longer exists.") from exc


def shorten(text: str | None, width: int) -> str:
    if not text:
        return "-"
    text = " ".join(text.split())
    if len(text) <= width:
        return text
    return text[: max(0, width - 3)] + "..."


def print_table(items: list[PortInfo]) -> None:
    headers = ["PROTO", "ADDRESS", "PORT", "STATE", "PID", "PROCESS", "COMMAND"]

    rows = [
        [
            item.protocol,
            shorten(item.local_address, 22),
            str(item.port),
            item.state or "-",
            str(item.pid) if item.pid is not None else "-",
            shorten(item.process, 24),
            shorten(item.command, 70),
        ]
        for item in items
    ]

    widths = [
        max(len(headers[i]), *(len(row[i]) for row in rows))
        for i in range(len(headers))
    ]

    line = "  ".join(headers[i].ljust(widths[i]) for i in range(len(headers)))
    separator = "  ".join("-" * widths[i] for i in range(len(headers)))

    print(line)
    print(separator)

    for row in rows:
        print("  ".join(row[i].ljust(widths[i]) for i in range(len(headers))))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="portspy",
        description="Find the process using a local TCP or UDP port.",
    )
    parser.add_argument(
        "port",
        type=int,
        nargs="?",
        help="Local port to inspect, for example 8080.",
    )
    parser.add_argument(
        "--kill",
        action="store_true",
        help="Terminate every process currently using the port.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON instead of a table.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="PortSpy 1.0.0",
    )
    return parser.parse_args()


def validate_port(port: int) -> None:
    if not 1 <= port <= 65535:
        raise ValueError("Port must be between 1 and 65535.")


def interactive_port() -> int:
    print("PortSpy")
    print("Find the process using a local TCP/UDP port.")
    print()

    while True:
        value = input("Port: ").strip()

        try:
            port = int(value)
            validate_port(port)
            return port
        except ValueError:
            print("Please enter a port between 1 and 65535.\n")


def pause_if_interactive(interactive: bool) -> None:
    if interactive:
        print()
        try:
            input("Press Enter to exit...")
        except (EOFError, KeyboardInterrupt):
            pass


def main() -> int:
    args = parse_args()
    interactive = args.port is None

    if interactive:
        try:
            args.port = interactive_port()
        except (EOFError, KeyboardInterrupt):
            return 0

    exit_code = 0

    try:
        validate_port(args.port)
        items = find_connections(args.port)
    except (ValueError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        pause_if_interactive(interactive)
        return 2

    if not items:
        if args.json:
            print("[]")
        else:
            print(f"No process is currently using port {args.port}.")
        pause_if_interactive(interactive)
        return 1

    if args.json:
        print(json.dumps([asdict(item) for item in items], indent=2))
    else:
        print()
        print_table(items)

    if args.kill:
        pids = sorted({item.pid for item in items if item.pid is not None})

        if not pids:
            print("\nNo process PID was available to terminate.", file=sys.stderr)
            exit_code = 1
        else:
            failed = False
            print()

            for pid in pids:
                try:
                    kill_process(pid)
                    print(f"Terminated PID {pid}.")
                except RuntimeError as exc:
                    failed = True
                    print(f"Could not terminate PID {pid}: {exc}", file=sys.stderr)

            exit_code = 1 if failed else 0

    pause_if_interactive(interactive)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
