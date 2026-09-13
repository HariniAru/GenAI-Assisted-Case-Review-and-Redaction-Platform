# AGENTS.md

## Project Overview

This is a learning-focused GenAI-assisted case review and text-redaction platform built with a Python/FastAPI backend and a React frontend. It uses synthetic customer-call records and will eventually incorporate RAG, LangGraph, Docker, AWS, and CloudWatch.

AI output is advisory: reviewers verify recommendations before approved redactions or summaries are saved. Work incrementally so the architecture, code, and tradeoffs can be clearly explained in an interview.

## Project Documentation

- Read the relevant files in `docs/` before implementing a task. Detailed requirements and task-specific scope will be found there.
- Treat approved project documentation as the source of truth. If documentation conflicts with the existing implementation or is ambiguous, explain the conflict before making a material assumption.
- Update documentation when an approved change alters setup, behavior, architecture, or commands.

## Core Backend Commands

Run these from `backend/`:

- Install or synchronize dependencies: `uv sync`
- Format code: `uv run ruff format .`
- Lint code: `uv run ruff check .`
- Run tests: `uv run pytest`
- Apply database migrations: `uv run alembic upgrade head`
- Start the API: `uv run uvicorn app.main:app --reload`

## Coding Conventions

- Follow the existing project structure and naming conventions.
- Prefer clear, typed, maintainable code over clever or premature abstractions.
- Keep changes small and focused on the requested milestone.
- Use Python type hints, Pydantic v2, SQLAlchemy 2.x patterns, and Alembic for database schema changes.
- Add or update tests for new behavior and bug fixes.
- Keep dependencies minimal. Explain new production dependencies and update `pyproject.toml` and its lock file together.
- Store configuration in environment variables. Never commit secrets or `.env` files.
- Use only synthetic data; never add real customer or company data to the repository.
- Do not log sensitive text, credentials, tokens, or secrets.

## Learning and Verification

- Before coding, briefly explain the planned approach and the files likely to change.
- After coding, run the relevant checks and report their results.
- Explain important implementation choices in plain language, including reasonable alternatives and tradeoffs.
- When useful, end a milestone with a few interview-style questions that test understanding of the work completed.
