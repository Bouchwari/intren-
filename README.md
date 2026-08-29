# نظام إدارة العمل / Matama

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

## Build the executable

```bash
pyinstaller Matama.spec
```

The packaged app will be created in `dist/`.

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
|- tests/                      Test area (currently empty)
|- requirements.txt            Python packages
`- README.md
```

Golden rule: `ui/` calls `core/`, and `core/` calls `data/`.
