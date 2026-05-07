Project setup and environment instructions for Skitec

1) Create a Python virtual environment

Windows (PowerShell):

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Windows (cmd.exe):

```cmd
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

macOS / Linux (bash / zsh):

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

2) Freeze installed packages (pin in CI release pipeline)

```bash
# After validating on CI or a release environment
pip freeze > requirements.txt
```

3) Docker build (example for a service)

```bash
docker build -t skitec-identity:latest ./services/identity
docker run -p 8000:8000 skitec-identity:latest
```

4) Notes
- Use AWS Secrets Manager / SSM for secrets in production.
- Run migrations (Alembic) from a migration container or CI job.
- Use `requirements-dev.txt` for developer tooling and CI lint/test jobs.
