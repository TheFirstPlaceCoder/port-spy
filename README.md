<div align="center">

# 🕵️ PortSpy

### Find what is using a local port — instantly.

A tiny, dependency-free CLI tool for Windows, Linux, and macOS.

</div>

---

## What is PortSpy?

You know the situation:

```text
Error: address already in use
Port 8080 is already occupied
```

Now you have to remember `netstat`, `ss`, `lsof`, process commands, PID lookups, and the correct syntax for your operating system.

PortSpy turns that into one command:

```bash
python portspy.py 8080
```

Example output:

```text
PROTO  ADDRESS  PORT  STATE      PID    PROCESS   COMMAND
-----  -------  ----  ---------  -----  --------  ----------------------------
TCP    0.0.0.0  8080  LISTENING  12984  java.exe  java -jar application.jar
```

That's it.

---

## Features

- Find which process is using a local port
- Show the PID
- Show the process name
- Show the full process command line when available
- Detect TCP and UDP listeners
- Terminate the process with `--kill`
- JSON output for scripts and automation
- Works on Windows, Linux, and macOS
- No external Python packages required
- Single-file utility

---

## Requirements

- Python 3.10+
- Windows, Linux, or macOS

PortSpy uses built-in operating-system tools:

| OS | Tools |
|---|---|
| Windows | `netstat`, PowerShell, `taskkill` |
| Linux | `ss` or `lsof`, `ps` |
| macOS | `lsof`, `ps` |

No `pip install` is required.

---

## Installation

Clone the repository:

```bash
git clone https://github.com/YOUR_USERNAME/portspy.git
cd portspy
```

Or simply download `portspy.py`.

---

## Usage

## Interactive mode

You can also simply double-click `portspy.py` on Windows.

When PortSpy is started without command-line arguments, it switches to interactive mode:

```text
PortSpy
Find the process using a local TCP/UDP port.

Port: 8080
```

The window stays open after the result is displayed and closes only after you press Enter.

---

### Check a port

```bash
python portspy.py 8080
```

Example:

```text
PROTO  ADDRESS  PORT  STATE      PID    PROCESS   COMMAND
-----  -------  ----  ---------  -----  --------  --------------------------
TCP    0.0.0.0  8080  LISTENING  7421   java.exe  java -jar server.jar
```

---

### Kill the process using a port

```bash
python portspy.py 8080 --kill
```

Example:

```text
PROTO  ADDRESS  PORT  STATE      PID    PROCESS
-----  -------  ----  ---------  -----  --------
TCP    0.0.0.0  8080  LISTENING  7421   java.exe

Terminated PID 7421.
```

You may need Administrator/root permissions when terminating processes owned by another user.

---

### JSON output

```bash
python portspy.py 8080 --json
```

Example:

```json
[
  {
    "protocol": "TCP",
    "local_address": "0.0.0.0",
    "port": 8080,
    "state": "LISTENING",
    "pid": 7421,
    "process": "java.exe",
    "command": "java -jar server.jar"
  }
]
```

This is useful when PortSpy is called from another script.

---

## Examples

Check a development server:

```bash
python portspy.py 3000
```

Check a Spring Boot application:

```bash
python portspy.py 8080
```

Check PostgreSQL:

```bash
python portspy.py 5432
```

Check MySQL:

```bash
python portspy.py 3306
```

Kill whatever is using port `5173`:

```bash
python portspy.py 5173 --kill
```

---

## Exit codes

| Code | Meaning |
|---:|---|
| `0` | Port found successfully, or process terminated successfully |
| `1` | Nothing is using the port, or a process could not be terminated |
| `2` | Invalid input or unsupported environment |

This makes PortSpy easy to use inside shell scripts and CI utilities.

---

## How it works

PortSpy intentionally avoids third-party dependencies.

On **Windows**, it reads active connections using `netstat -ano`, then uses PowerShell/CIM to retrieve the process name and command line.

On **Linux**, it prefers `ss` and falls back to `lsof` when necessary.

On **macOS**, it uses `lsof`.

The results are normalized into the same output format on every supported platform.

---

## Why?

Finding the process behind an occupied port should not require remembering a different command for every operating system.

Instead of:

```bash
netstat -ano
tasklist
```

or:

```bash
ss -lntup
```

or:

```bash
lsof -i :8080
```

just run:

```bash
python portspy.py 8080
```

---

## Safety

`--kill` terminates processes.

Always check the displayed PID and process information before using it, especially when running PortSpy with elevated permissions.

PortSpy only inspects local network listeners and does not scan remote systems.

---

## Project structure

PortSpy is deliberately kept small.

One file. One job.

---

<div align="center">

Made with Python · PortSpy

</div>
