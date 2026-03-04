# Environment Setup

## Runtime Requirements

- Python `3.11+`
- `pip`
- Playwright Python package
- Playwright browser binaries
- Linux server support for headless Chromium

## Python Packages

Production dependencies are listed in `requirements.txt`.

- `playwright`
- `websockets`

Development dependencies are listed in `requirements-dev.txt`.

- `pytest`

## Recommended Setup

### 1. Create virtual environment

Use Python 3.11 or newer:

```bash
python3.11 -m venv .venv
```

### 2. Activate virtual environment

macOS / Linux:

```bash
source .venv/bin/activate
```

### 3. Install Python dependencies

```bash
pip install -r requirements-dev.txt
```

### 4. Install Playwright browser

```bash
playwright install chromium
```

For Linux servers, if system libraries are missing:

```bash
playwright install-deps chromium
```

## Notes

- Use the project virtual environment instead of the system Python.
- On macOS, Homebrew Python `3.11+` is a practical choice if the system Python is older than the project baseline.
- After activation, `python` and `pip` should resolve from `.venv/bin/`.

## Verification Commands

```bash
python --version
pip --version
pytest
```
