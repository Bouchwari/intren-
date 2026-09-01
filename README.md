# نظام المطعمة / Matama

Offline desktop app for cafeteria records, students, reports, and supplier paperwork.

Built with Python + PySide6.

## Setup

### 1. Install Python
Use Python 3.11 or newer from `https://www.python.org/downloads/`.

### 2. Create a virtual environment
```bash
python -m venv venv
```

Activate it:
- Windows: `venv\Scripts\activate`
- Mac/Linux: `source venv/bin/activate`

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

## Run the app

```bash
python src/main.py
```

The app opens into the main Matama window with a right-to-left sidebar for dashboard, students, meal programs, daily logs, reports, reception and infraction records, quarterly documents, and settings.

## Run the tests

```bash
python -m pytest -q
```

## Build the portable executable

PyInstaller builds for the operating system that runs it. On Windows:

```bash
pyinstaller --clean --noconfirm Matama.spec
```

The single portable file is created as `dist/Matama.exe`. Git tags beginning
with `v` also run `.github/workflows/release.yml`, test the app on Windows,
build the executable, and attach it to a GitHub release.

The app stores `matama.db` beside the executable. Keep the executable in a
writable folder such as Documents or Desktop, and use الإعدادات → النسخ
الاحتياطي regularly.

## Project structure

```text
work_system/
|- src/                        Application source
|  |- main.py                  Entry point
|  |- ui/                      Screens and widgets
|  |- core/                    Business logic
|  `- data/                    Database access
|- config/                     Shared settings and constants
|- templets/                   Document and spreadsheet templates
|- build/ and dist/            Generated packaging output
|- matama.db                   Local SQLite database
|- tests/                      Automated test suite
|- requirements.txt            Python packages
`- README.md
```

Layer rule: `ui/` may call `core/` and `data/`; `core/` may call `data/`;
SQL stays in `data/`, and Qt stays in `ui/`.
