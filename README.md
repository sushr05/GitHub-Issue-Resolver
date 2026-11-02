# Autonomous Software Engineer

An AI agent that accepts a GitHub issue, finds the relevant code, generates a fix, runs tests, and opens a pull request — automatically.

---

## Architecture

```
POST /process-issue
        ↓
  LangGraph Workflow
        ↓
  analyze_issue  →  retrieve_context  →  generate_fix
       ↑                                       ↓
       └──── retry (max 3) ──── run_tests ← apply_patch
                                    ↓ (pass)
                              generate_pr → PR URL
```

**Stack:** Python 3.11 · FastAPI · LangGraph · Tree-sitter · FAISS · GitPython · Docker · GitHub API

---

## Quick Start

### 1. Prerequisites

- Python 3.11 (via pyenv)
- Docker Desktop running
- Google Gemini API key (free at [aistudio.google.com](https://aistudio.google.com/app/apikey))
- GitHub Personal Access Token (repo + pull_request scopes)

### 2. Setup

```bash
# Install Python 3.11
pyenv install 3.11.9
pyenv local 3.11.9

# Create virtualenv
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e ".[dev]"

# Configure environment
cp .env.example .env
# Edit .env and fill in GOOGLE_API_KEY, GITHUB_TOKEN, etc.
```

### 3. Run the API

```bash
uvicorn app.main:app --reload
```

API docs: http://localhost:8000/docs

---

## Usage

### Step 1 — Index a repository

```bash
curl -X POST http://localhost:8000/index-repository \
  -H "Content-Type: application/json" \
  -d '{"repository_path": "/path/to/your/repo"}'
```

### Step 2 — Process an issue

```bash
curl -X POST http://localhost:8000/process-issue \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Registration fails when user email is null",
    "description": "When a user submits the registration form without an email address, the server throws a 500 error instead of returning a validation message.",
    "repository_path": "/path/to/your/repo",
    "issue_number": 42
  }'
```

Response:
```json
{
  "pr_url": "https://github.com/you/repo/pull/43",
  "pr_title": "fix: handle null email in register_user()",
  "root_cause": "register_user() calls email.lower() without null check",
  "files_changed": ["app/auth/registration.py"],
  "test_passed": true
}
```

---

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `POST /index-repository` | Parse a repo with Tree-sitter, build FAISS index |
| `POST /process-issue` | Run full pipeline: analyze → fix → test → PR |
| `POST /run-tests` | Run pytest in Docker (standalone) |
| `POST /generate-pr` | Create a GitHub PR from an existing patch (standalone) |
| `GET /health` | Health check |

---

## Project Structure

```
app/
├── agents/          # 5 specialized agents + patch applicator
├── api/             # FastAPI routes + dependency injection
├── hooks/           # Pre/post validation hooks
├── models/          # Pydantic schemas (issue, symbol, patch, PR, state)
├── parsers/         # Tree-sitter code parser
├── retrieval/       # Exact + semantic retrieval
├── vectorstore/     # FAISS store with HuggingFace embeddings
├── github/          # GitHub API client + PR builder
├── docker_runner/   # Docker-based test runner
├── workflow/        # LangGraph StateGraph
├── config.py        # Pydantic Settings
├── llm.py           # LLM factory (Gemini / Ollama)
└── main.py          # FastAPI entry point
```

---

## Running Tests

```bash
pytest tests/ -v
```

---

## Docker

```bash
docker-compose up
```

---

## Environment Variables

See `.env.example` for all available options.

Key variables:

| Variable | Description |
|----------|-------------|
| `GOOGLE_API_KEY` | Gemini Flash API key (free) |
| `GITHUB_TOKEN` | GitHub PAT |
| `GITHUB_REPO_OWNER` | Your GitHub username |
| `GITHUB_REPO_NAME` | Repo name for PRs |

---

## Future Roadmap

- Call graph traversal with Neo4j
- Multi-repository analysis
- Human approval node
- Web UI dashboard
- Support for Go, Rust, Java
