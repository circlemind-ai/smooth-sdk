# Agents Guide

## Running commands

Always use `poetry run` to execute Python commands (tests, scripts, etc.) to ensure the correct virtualenv is used.

```bash
# Tests
poetry run pytest tests/ -v

# Single test file
poetry run pytest tests/test_models.py -v

# Python scripts
poetry run python -c "..."
```

## Project setup

```bash
poetry env use 3.14
poetry install --extras test
```
