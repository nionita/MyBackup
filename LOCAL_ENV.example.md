# Local development environment template

Copy this file to `LOCAL_ENV.md` and fill in the details for this machine.
`LOCAL_ENV.md` is Git-ignored. Record paths and commands here, never credentials.

- Platform: Windows or Linux
- Shell: PowerShell or a Linux shell
- Preferred interpreter: absolute path to an existing Python 3.12+ executable
- Version checked: version and date
- Alternative interpreter (optional): path, version, and intended use

Use the existing interpreter directly. Do not install packages or create additional
environments. Verify the selected interpreter's version before running scripts.

Run commands from the repository root. Replace the example interpreter paths below
with paths verified on this machine.

## Windows (PowerShell)

```powershell
& "C:\path\to\python.exe" --version
$env:PYTHONPATH = "backup-tool"
& "C:\path\to\python.exe" -m unittest discover tests/
```

## Linux

```sh
/path/to/python3 --version
PYTHONPATH=backup-tool /path/to/python3 -m unittest discover tests/
```

## Other local notes

Record any machine-specific working directories or tooling paths needed to run or
test the project. Keep shared platform conventions in `AGENTS.md` or `README.md`.
