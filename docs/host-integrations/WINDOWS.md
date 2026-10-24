# Windows preparation, not native-runtime certification

[中文](WINDOWS-中文.md) · [Overview](README.md)

Windows native, Windows-to-WSL and Windows-to-remote are separate modes. Do not mix Windows
paths with Linux paths or assume localhost forwarding, mapped-drive locks or app PATH inheritance.
No Windows executor has been run by preparing these files.

Discovery prepares a bounded, read-only scan of standard Windows Uninstall metadata
(DisplayName, DisplayVersion and InstallLocation; at most 512 entries / about two seconds).
Exact recipe-name matches are installation candidates, never proof that MCP, Hooks or a
particular desktop mode works. No uninstall commands or conversations are read or executed.
Portable/MSIX installations, renamed apps, access-denied keys and incomplete scans may stay
unknown; they must not be treated as a client capability failure. Native registry execution
is still pending; synthetic Windows metadata tests on macOS are not Windows certification.

From a trusted source checkout with Python3.11+:

```powershell
./scripts/ep-host.ps1 list --json
./scripts/ep-host.ps1 discover --json
./scripts/ep-host.ps1 doctor --host workbuddy --json
./scripts/ep-host.ps1 config-preview --host workbuddy --json
```

The launcher prefers `api/.venv/Scripts/python.exe`, then `py -3.11`, then `python`.
It preserves argument arrays and exit status. It does not install Python, services, models or clients.
Run the same dependency preflight and EP backend setup appropriate to the target environment;
API/database/controller/worker/local model startup is not proved by this CLI.

## Isolated test environment

```powershell
py -3.11 -m venv .host-test-venv
./.host-test-venv/Scripts/python.exe -m pip install -r scripts/host-test-requirements.txt
./.host-test-venv/Scripts/python.exe scripts/verify-host-integrations.py
```

These test-only pins reproduce the development test inputs, not new global runtime requirements.
The manual-only workflow `.github/workflows/host-integrations.yml` prepares macOS/Windows runners
without provider secrets. Merely writing the workflow is not an executed test.

Native checks must cover cross-process locking, timeout/process-exit release, occupied destination,
CAS rollback conflict, Unicode/space paths, CRLF/BOM, executable startup and actual PowerShell smoke.
Shared-lock requests conservatively serialize as exclusive on Windows. No unlocked fallback is allowed.
Keep unknown or blocked core dependencies visible. WSL/remote success cannot certify native Windows.
