# Architecture Documentation — Autonomous Software Engineer (ASE)

> **Who is this for?** Anyone — whether you're a developer, a student, or just curious — who wants to understand how this project works under the hood. Every section starts with a plain-English explanation before getting into the details. No prior knowledge of any specific tool or library is assumed.

---

## Table of Contents

1. [What the System Does — The 30-Second Pitch](#1-what-the-system-does--the-30-second-pitch)
2. [End-to-End Request Lifecycle](#2-end-to-end-request-lifecycle)
3. [High-Level Architecture Diagram](#3-high-level-architecture-diagram)
4. [Technology Stack & Key Dependencies](#4-technology-stack--key-dependencies)
5. [Application Entry Point & Server Bootstrap](#5-application-entry-point--server-bootstrap)
6. [API Layer — Every Endpoint Explained](#6-api-layer--every-endpoint-explained)
7. [GitHub Integration Layer](#7-github-integration-layer)
8. [LLM Abstraction Layer — Provider Cascade & Prompt Engineering](#8-llm-abstraction-layer--provider-cascade--prompt-engineering)
9. [LLM Retry & Rate-Limit Handling](#9-llm-retry--rate-limit-handling)
10. [Code Parsing — Tree-Sitter AST Extraction](#10-code-parsing--tree-sitter-ast-extraction)
11. [Vector Store — FAISS Embedding & Indexing](#11-vector-store--faiss-embedding--indexing)
12. [Hybrid Retrieval Engine — Exact + Semantic Search](#12-hybrid-retrieval-engine--exact--semantic-search)
13. [Agent Orchestration — LangGraph State Machine](#13-agent-orchestration--langgraph-state-machine)
14. [Agent Deep Dives](#14-agent-deep-dives)
15. [Hook System — Validation & Formatting Gates](#15-hook-system--validation--formatting-gates)
16. [Sandboxed Test Execution — Docker Runner](#16-sandboxed-test-execution--docker-runner)
17. [Data Models — Complete Schema Reference](#17-data-models--complete-schema-reference)
18. [Configuration System](#18-configuration-system)
19. [Dependency Injection](#19-dependency-injection)
20. [Dashboard — Frontend UI](#20-dashboard--frontend-ui)
21. [Testing Strategy](#21-testing-strategy)
22. [CI/CD Pipeline](#22-cicd-pipeline)
23. [Deployment & Containerisation](#23-deployment--containerisation)
24. [Error Handling & Resilience Patterns](#24-error-handling--resilience-patterns)
25. [Security Considerations](#25-security-considerations)
26. [Known Limitations & Future Improvements](#26-known-limitations--future-improvements)
27. [Complete Directory Structure](#27-complete-directory-structure)
28. [Interview FAQ — Common Deep-Dive Questions](#28-interview-faq--common-deep-dive-questions)

---

## 1. What the System Does — The 30-Second Pitch

**In plain English:** Imagine you file a bug report on GitHub. Normally a human developer would read the bug, find the broken code, write a fix, test it, and then submit the fix for review. This system does all of that *automatically* using AI.

The **Autonomous Software Engineer** (ASE) is an AI-powered backend agent that takes a GitHub issue (a bug report) as input and, without any human intervention:

1. **Clones** the target repository to a local workspace — *i.e., downloads a copy of the project's source code to its own machine so it can work on it.*
2. **Parses** every Python, JavaScript, and TypeScript file using Tree-Sitter ASTs and extracts all functions, classes, and methods as structured `Symbol` objects — *i.e., reads through every code file and builds a catalogue of every function and class it finds. Think of it like creating a table of contents for a book, but for code.*
3. **Embeds** those symbols into a FAISS vector index for semantic code search — *i.e., converts each function/class into a numerical "fingerprint" (a list of numbers) so that later, when it needs to find code related to a bug, it can search by meaning rather than just by name.*
4. **Analyses** the issue using an LLM (AI model like Gemini / HuggingFace / Ollama) to identify root cause, affected files, and severity — *i.e., sends the bug description to an AI and asks "what's going wrong, which files are broken, and how bad is it?"*
5. **Retrieves** the most relevant code snippets using a hybrid exact+semantic search — *i.e., finds the actual code that's related to the bug using two strategies: looking for functions mentioned by name in the bug report, and looking for functions that are conceptually related.*
6. **Generates** a minimal, targeted code patch via the LLM — *i.e., asks the AI to write the smallest possible code change that would fix the bug.*
7. **Applies** the patch to disk, auto-formats with `ruff` + `black`, and commits to a `fix/auto-{timestamp}` branch — *i.e., saves the AI-written fix into the code files, cleans up the formatting so it looks tidy, and creates a new version (branch) in Git with a timestamp like `fix/auto-20260912`.*
8. **Tests** the fix inside a sandboxed Docker container running `pytest` — *i.e., runs the project's existing tests inside an isolated "sandbox" (a lightweight virtual environment) to make sure the fix doesn't break anything else.*
9. **Retries** up to 3 times (re-analysing and re-generating) if tests fail — *i.e., if the tests reveal the fix is wrong, it goes back to step 4 and tries again from scratch, up to 3 attempts.*
10. **Opens a Pull Request** on GitHub with an LLM-generated title and Markdown description — *i.e., submits the fix for human review on GitHub, complete with a nicely written explanation of what was changed and why.*

The entire pipeline is orchestrated as a **LangGraph state machine** with 6 nodes, conditional retry edges, and shared `AgentState`.

> **What's a state machine?** Think of it like a flowchart. Each box (node) is a step in the process. Arrows connect the boxes to show which step comes next. Some arrows are "conditional" — they say "if the test passed, go here; if it failed, go back there." The "state" is a shared notepad that every step can read from and write to, so each step knows what previous steps have done.

---

## 2. End-to-End Request Lifecycle

**In plain English:** This section walks through exactly what happens, step by step, from the moment someone asks the system to fix a bug until the final pull request is created. Think of it like tracing a package from the moment you click "order" to when it arrives at your door.

Here is exactly what happens when a client calls `POST /process-issue`:

```
Client → POST /process-issue { title, description, github_url }
   │
   ├─ 1. FastAPI creates a UUID task_id
   │      (A unique tracking number, like an order confirmation number)
   │
   ├─ 2. Stores { status: "pending", steps: {...} } in tasks_db (in-memory dict)
   │      (Saves the task info in a temporary "database" that lives in memory)
   │
   ├─ 3. Returns 202 Accepted { task_id, status: "pending" }
   │      (Immediately tells the client "got it, here's your tracking number")
   │
   ├─ 4. Starts the actual work in the background
   │      (The response is sent back right away — the heavy lifting happens behind the scenes)
   │
   │  ╔══════════════════════════════════════════════════════════════════╗
   │  ║           BACKGROUND TASK EXECUTION                            ║
   │  ╠══════════════════════════════════════════════════════════════════╣
   │  ║                                                                ║
   │  ║  Step 1: CLONE                                                 ║
   │  ║    Download the repo's source code (or update it if we         ║
   │  ║    already have a copy)                                        ║
   │  ║    → Saved to: /tmp/ase_workspace/owner_repo                   ║
   │  ║                                                                ║
   │  ║  Step 2: INDEX                                                 ║
   │  ║    Scan every code file, extract all functions/classes,         ║
   │  ║    and build a searchable index of them                        ║
   │  ║    → Saved to: data/indices/{repo_name}/                       ║
   │  ║                                                                ║
   │  ║  Steps 3–8: THE AI WORKFLOW (6-step pipeline)                  ║
   │  ║    ┌──────────────┐     ┌──────────────────┐                   ║
   │  ║    │ analyze_issue│────→│ retrieve_context  │                   ║
   │  ║    └──────────────┘     └────────┬─────────┘                   ║
   │  ║          ↑                       ↓                             ║
   │  ║          │              ┌──────────────────┐                   ║
   │  ║          │              │   generate_fix   │                   ║
   │  ║          │              └────────┬─────────┘                   ║
   │  ║          │                       ↓                             ║
   │  ║          │              ┌──────────────────┐                   ║
   │  ║          │              │   apply_patch    │                   ║
   │  ║          │              └────────┬─────────┘                   ║
   │  ║          │                       ↓                             ║
   │  ║          │              ┌──────────────────┐                   ║
   │  ║    retry │              │    run_tests     │                   ║
   │  ║   (max 3)│              └────────┬─────────┘                   ║
   │  ║          │                       │                             ║
   │  ║          │            ┌──────────┴─────────┐                   ║
   │  ║          │         passed?              failed?                ║
   │  ║          │            ↓               retry < 3?               ║
   │  ║          │    ┌──────────────┐        yes → ↑ (loop back)      ║
   │  ║          │    │ generate_pr  │        no  → END (give up)      ║
   │  ║          │    └──────┬───────┘                                 ║
   │  ║          │           ↓                                         ║
   │  ║          │         END                                         ║
   │  ╚══════════════════════════════════════════════════════════════════╝
   │
   ├─ Client polls: GET /process-issue/{task_id}
   │   (The client keeps asking "is it done yet?" using the tracking number)
   │   → Returns { status, steps: { clone, index, analyze, ... }, result }
   │
   └─ Final result: { pr_url, root_cause, files_changed, test_passed }
```

The **`POST /process-github-issue`** endpoint works identically but with two differences:
- It **fetches the bug report details automatically** from GitHub (title, description, labels, and up to 5 comments) — you only need to provide the repo URL and issue number.
- It runs **synchronously** — meaning the HTTP response waits until the entire pipeline finishes before responding. No tracking number, no polling, you just wait and get the result directly. This is useful for automated scripts that can handle longer wait times.

---

## 3. High-Level Architecture Diagram

**In plain English:** This diagram shows all the major "pieces" of the system and how they connect. Think of it like an org chart for the software — each box is a component with a specific job, and the arrows show how they talk to each other.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                            CLIENT LAYER                                 │
│   (Dashboard UI / curl / CI script / GitHub webhook)                    │
│   This is whoever is asking the system to fix a bug — could be         │
│   a web dashboard, a command-line tool, or an automated script.        │
└────────┬────────────────────────────────────────────────────────────────┘
         │  HTTP (web requests)
         ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         FASTAPI APPLICATION                             │
│   The "front desk" — receives requests and routes them to the right    │
│   part of the system.                                                   │
│                                                                         │
│  ┌───────────────┐ ┌──────────────────┐ ┌────────────┐ ┌────────────┐  │
│  │ /process-issue│ │/process-github-  │ │/index-     │ │/run-tests  │  │
│  │ (async, 202)  │ │ issue (sync)     │ │ repository │ │(standalone)│  │
│  └───────┬───────┘ └────────┬─────────┘ └─────┬──────┘ └─────┬──────┘  │
│          │                  │                  │              │          │
│  ┌───────┴──────────────────┴──────────────────┴──────────────┘          │
│  │   SHARED SERVICES (created once, reused by all requests)             │
│  │   Indexing Agent, Test Runner, FAISS Store, etc.                     │
│  └──────────────────────────────┬───────────────────────────────────────┘
                                  │
         ┌────────────────────────┼────────────────────────┐
         ▼                        ▼                        ▼
┌─────────────────┐  ┌────────────────────┐  ┌──────────────────────────┐
│  GITHUB LAYER   │  │  INDEXING LAYER    │  │   WORKFLOW ENGINE        │
│  Talks to GitHub│  │  Reads & catalogues│  │   The AI brain — runs    │
│  to clone repos │  │  code files, builds│  │   the 6-step pipeline    │
│  and create PRs │  │  search index      │  │   to analyse, fix, and  │
│                 │  │                    │  │   test the code          │
└─────────────────┘  └────────────────────┘  └──────────┬───────────────┘
                                                         │
                          ┌──────────────────────────────┤
                          ▼                              ▼
               ┌───────────────────┐          ┌──────────────────┐
               │   LLM LAYER      │          │  DOCKER RUNNER   │
               │   The AI models  │          │  A safe sandbox  │
               │   that understand│          │  to run tests in │
               │   and write code │          │  isolation       │
               └───────────────────┘          └──────────────────┘
```

---

## 4. Technology Stack & Key Dependencies

**In plain English:** This is the "ingredients list" — every major tool and library the project uses, what it does, and why we picked it over alternatives. If you're new to these, don't worry — the "Purpose" column explains what each one actually does.

| Category | Technology | Version | Purpose (What it does) |
|----------|-----------|---------|------------------------|
| **Web Framework** | FastAPI | ≥0.111.0 | Handles incoming web requests. Think of it as the "reception desk" that receives instructions and sends back responses. Also auto-generates documentation for all our endpoints. |
| **ASGI Server** | Uvicorn | ≥0.30.0 | The actual web server that runs our app and handles network connections. FastAPI is the app; Uvicorn is the engine that makes it accessible over the internet. |
| **Orchestration** | LangGraph | ≥1.0.0 | Manages the multi-step AI pipeline as a flowchart (state machine). Handles "if tests fail, go back and try again" logic cleanly. |
| **LLM Framework** | LangChain Core | ≥1.0.0 | A wrapper that lets us talk to different AI models (Gemini, HuggingFace, Ollama) using the same code. Without it, we'd need different code for each AI provider. |
| **LLM: Primary** | Google Gemini Flash (`gemini-2.0-flash-lite`) | via `langchain-google-genai` | Our first-choice AI model. Free to use, fast, and good at producing structured JSON output. |
| **LLM: Fallback 1** | HuggingFace Inference (`Qwen/Qwen2.5-Coder-32B-Instruct`) | via `langchain-huggingface` | If Gemini is unavailable, we fall back to this model. Free with a HuggingFace account and specifically designed for coding tasks. |
| **LLM: Fallback 2** | Ollama (`codellama:7b`) | via `langchain-ollama` | Last resort — runs entirely on your own computer, no internet or API key needed. Useful for offline development or when all cloud services are down. |
| **Embeddings** | Sentence Transformers (`all-MiniLM-L6-v2`) | ≥3.0.1 | Converts text (code, descriptions) into numerical "fingerprints" (384 numbers) that capture meaning. Two similar pieces of code will have similar fingerprints, enabling "search by meaning." Runs locally, no API key needed. |
| **Vector DB** | FAISS CPU (`IndexFlatIP`) | ≥1.8.0 | A high-speed search engine for those numerical fingerprints. Given a query fingerprint, it finds the most similar ones in milliseconds. Think of it like a super-fast "find similar" feature. |
| **AST Parsing** | Tree-Sitter | ≥0.23.0 | Reads code files and understands their structure (where functions start and end, what classes contain, etc.) without actually running the code. Works for Python, JavaScript, and TypeScript. |
| **Git Operations** | GitPython | ≥3.1.40 | Lets our Python code do Git things — clone repos, create branches, make commits — programmatically instead of typing commands in a terminal. |
| **GitHub API** | PyGithub | ≥2.3.0 | Talks to GitHub's API to fetch bug reports (issues) and create pull requests. |
| **Containerisation** | Docker SDK for Python | ≥7.0.0 | Controls Docker containers from Python code. We use this to run tests in isolated "sandboxes" so the target repo's dependencies don't conflict with ours. |
| **Data Validation** | Pydantic v2 | ≥2.7.0 | Ensures data has the right shape and types. For example, it makes sure a "score" field is actually a number between 0 and 1, not a random string. |
| **Configuration** | pydantic-settings | ≥2.10.0 | Reads settings from a `.env` file (a simple text file of key=value pairs) and converts them into typed Python objects. |
| **Code Formatting** | Ruff + Black | ruff ≥0.4.0, black ≥24.0.0 | Auto-fixes code style issues. Ruff catches common mistakes and bad patterns; Black reformats code to look consistent. Applied to every patch the AI generates. |
| **Retry Logic** | Tenacity | ≥8.3.0 | Automatically retries operations that fail temporarily (e.g., an API that's briefly overloaded). Handles timing, backoff, and giving up after too many failures. |
| **HTTP Client** | HTTPX | ≥0.27.0 | Makes HTTP requests. Used in our tests to simulate a client calling our API without needing a real running server. |
| **Python** | 3.10–3.11 | — | The programming language everything is written in. We're constrained to these versions because some of our dependencies (like numpy) require them. |

### Why These Choices?

Here's the reasoning behind some of the less obvious technology picks:

- **LangGraph over raw LangChain Agents:** LangGraph lets us define the pipeline as an explicit flowchart — "first do A, then B, then if tests fail go back to A." With raw LangChain Agents, we'd have to hack this flow control into the AI prompts, which is fragile and hard to debug.

- **FAISS over Chroma/Pinecone:** FAISS is free, runs on your machine, needs zero setup, and is fast enough for our use case (searching through hundreds to a few thousand code symbols). Other options like Pinecone require a cloud account and network calls, adding complexity for no real benefit at our scale.

- **Tree-Sitter over Python's built-in `ast` module:** Tree-Sitter can parse Python, JavaScript, *and* TypeScript with a single consistent API. Python's `ast` module only works with Python files. Tree-Sitter can also handle broken or incomplete code files without crashing, which is important when scanning unfamiliar repos.

- **`all-MiniLM-L6-v2` over OpenAI embeddings:** It's free, runs locally, doesn't need an API key, and its 384-dimensional output is more than sufficient for finding similar code snippets. It loads in about 1 second.

- **Docker for test sandboxing:** The repos we're fixing have their own dependencies (libraries, packages). Running their tests directly on our machine could cause conflicts. Docker gives each test run its own isolated mini-environment.

---

## 5. Application Entry Point & Server Bootstrap

**In plain English:** This section explains what happens when you start the server. Think of it like what happens when you turn on a restaurant — the lights come on, the kitchen is set up, and the front desk is ready to take orders. Here, "starting the server" means our app loads its configuration, registers all its endpoints (the "menu" of things it can do), and starts listening for requests.

**File:** [`app/main.py`](file:///c:/Users/sushr/Downloads/autonomous-software-engineer-main/autonomous-software-engineer-main/app/main.py)

```python
# Simplified representation of what main.py does:
app = FastAPI(title="Autonomous Software Engineer", version="0.1.0")

# 1. CORS — Allow requests from any website (for development)
#    In production, you'd restrict this to only your frontend's domain.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# 2. Lifespan — Log when the server starts and stops
@asynccontextmanager
async def lifespan(app):
    logger.info("Starting...")
    yield
    logger.info("Shutting down")

# 3. Route registration — Tell FastAPI about all 6 groups of endpoints
app.include_router(indexing.router)      # POST /index-repository
app.include_router(issues.router)        # POST /process-issue, GET /process-issue/{id}
app.include_router(testing.router)       # POST /run-tests
app.include_router(pr.router)            # POST /generate-pr
app.include_router(github_issues.router) # POST /process-github-issue
app.include_router(indices.router)       # GET /indices

# 4. Serve the web dashboard as static files
app.mount("/dashboard", StaticFiles(directory="dashboard", html=True))

# 5. Health check — a simple "are you alive?" endpoint
@app.get("/health")
async def health(): return {"status": "ok", "version": "0.1.0"}
```

### Key Details:
- **Logging is set up immediately** when the file is first loaded (before the app even starts), so every part of the system can write log messages from the very beginning.
- **The AI pipeline (LangGraph graph) is also built once at startup**, not every time a request comes in. This means the AI model is loaded into memory once and shared across all requests — much faster than reloading it every time.
- The **dashboard** (the web UI) is served as static files only if the `dashboard/` folder exists.

---

## 6. API Layer — Every Endpoint Explained

**In plain English:** "Endpoints" are like doors into the system — each one accepts a specific type of request and does a specific thing. This section explains every door, what you need to knock with, and what you get back.

### 6.1 `POST /process-issue` — Async Pipeline Trigger

> **What it does:** You send a bug description and a GitHub URL, and the system starts fixing the bug in the background. You get a tracking number back immediately so you can check on progress.

**File:** [`app/api/routes/issues.py`](file:///c:/Users/sushr/Downloads/autonomous-software-engineer-main/autonomous-software-engineer-main/app/api/routes/issues.py)

**What you send (Request Body):**
```json
{
  "title": "Fix null pointer in user registration",
  "description": "When email is None, the validate_email function crashes...",
  "github_url": "https://github.com/owner/repo",
  "issue_number": 42,        // optional — the GitHub issue number
  "labels": ["bug", "P1"]    // optional — labels from the GitHub issue
}
```

**What you get back (Response — 202 Accepted):**
```json
{
  "task_id": "a1b2c3d4-...",
  "status": "pending",
  "message": "Workflow started in background."
}
```

**What happens internally:**
1. A UUID `task_id` is generated.
2. A `tasks_db[task_id]` entry is created with status `"pending"` and a `steps` dict tracking 8 pipeline stages: `clone → index → analyze → retrieve → generate → apply → test → pr`.
3. `run_workflow_in_background` is enqueued as a `BackgroundTask` (FastAPI's built-in mechanism — runs in the same event loop after the response is sent).
4. Inside the background task:
   - Each step updates `tasks_db` in real-time via `_update_step(task_id, step, status, detail, duration)`.
   - The LangGraph workflow is executed with `compiled_graph.astream()` — this yields events for each node completion, allowing step-by-step progress tracking.
   - After streaming completes, `compiled_graph.aget_state(config)` reads the final checkpoint to extract the result.

**Task lifecycle states:** `pending` → `running` → `completed` | `failed`

**Step lifecycle states:** `pending` → `running` → `done` | `failed`

### 6.2 `GET /process-issue/{task_id}` — Poll Task Status

> **What it does:** You provide a tracking number and get back the current progress of that task — which steps are done, which are still running, and the final result if it's finished.

Returns the full task status including per-step progress:

```json
{
  "task_id": "a1b2c3d4-...",
  "status": "running",
  "title": "Fix null pointer...",
  "github_url": "https://github.com/owner/repo",
  "submitted_at": "2026-09-12T14:30:00Z",
  "steps": {
    "clone":    { "status": "done",    "duration": 3.21, "detail": "Ready at /tmp/..." },
    "index":    { "status": "done",    "duration": 8.50, "detail": "247 symbols from 32 files" },
    "analyze":  { "status": "done",    "duration": null,  "detail": "Null check missing..." },
    "retrieve": { "status": "running", "duration": null,  "detail": null },
    "generate": { "status": "pending", "duration": null,  "detail": null },
    "apply":    { "status": "pending", "duration": null,  "detail": null },
    "test":     { "status": "pending", "duration": null,  "detail": null },
    "pr":       { "status": "pending", "duration": null,  "detail": null }
  },
  "result": null,
  "error": null
}
```

### 6.3 `GET /process-issue` — List All Tasks

> **What it does:** Returns a list of all tasks that have ever been submitted, sorted newest first. Used by the dashboard's Task History page.

### 6.4 `POST /process-github-issue` — Sync Pipeline from Issue Number

> **What it does:** Like `/process-issue`, but simpler — you just give it a GitHub URL and an issue number, and it fetches the bug details automatically from GitHub. The key difference is that it waits for the entire pipeline to finish before responding (no tracking number or polling).

**File:** [`app/api/routes/github_issues.py`](file:///c:/Users/sushr/Downloads/autonomous-software-engineer-main/autonomous-software-engineer-main/app/api/routes/github_issues.py)

**What you send:** `{ "github_url": "https://github.com/owner/repo", "issue_number": 42 }`

**Key differences from `/process-issue`:**
- Fetches issue data (title, body, labels, up to 5 comments) from the GitHub API via `GitHubClient.fetch_issue()`.
- Runs the full pipeline **synchronously** — the HTTP response blocks until completion.
- Uses `compiled_graph.ainvoke()` (not `astream`) — no step-by-step streaming.
- Returns the full result directly. No task_id or polling.
- On error, returns HTTP 500 with the exception message.

**Best for:** CI scripts, GitHub Actions, webhooks where the caller controls the timeout.

### 6.5 `POST /index-repository` — Standalone Indexing

> **What it does:** Scans a code repository and builds a searchable index of all functions and classes. You can use this independently, without running the full bug-fix pipeline.

**File:** [`app/api/routes/indexing.py`](file:///c:/Users/sushr/Downloads/autonomous-software-engineer-main/autonomous-software-engineer-main/app/api/routes/indexing.py)

Accepts `{ "repository_path": "/absolute/path/to/repo" }` and runs the Tree-Sitter + FAISS indexing pipeline. Uses dependency injection (`Depends(get_indexing_agent)`) for the `RepositoryIndexingAgent` singleton.

Returns: `{ total_files, total_symbols, indexed_at, message }`.

### 6.6 `POST /run-tests` — Standalone Test Execution

> **What it does:** Runs a repository's test suite inside an isolated Docker container. Useful if you just want to check whether tests pass without running the full pipeline.

**File:** [`app/api/routes/testing.py`](file:///c:/Users/sushr/Downloads/autonomous-software-engineer-main/autonomous-software-engineer-main/app/api/routes/testing.py)

Accepts `{ "repository_path": "..." }` and runs `pytest` inside Docker. Uses `Depends(get_test_runner)` for the `DockerTestRunner` singleton.

### 6.7 `POST /generate-pr` — Standalone PR Generation

> **What it does:** Takes pre-made fix information and generates a pull request description using AI. Useful if you've already fixed the bug yourself and just want a nice PR write-up.

**File:** [`app/api/routes/pr.py`](file:///c:/Users/sushr/Downloads/autonomous-software-engineer-main/autonomous-software-engineer-main/app/api/routes/pr.py)

Accepts a pre-constructed payload with issue details, patch info, and test results.

### 6.8 `GET /indices` — List Indexed Repositories

> **What it does:** Shows all repositories that have been scanned and indexed so far. Used by the dashboard's Repositories page.

**File:** [`app/api/routes/indices.py`](file:///c:/Users/sushr/Downloads/autonomous-software-engineer-main/autonomous-software-engineer-main/app/api/routes/indices.py)

Scans the `data/indices/` directory and returns metadata from each saved index, sorted most-recently-indexed-first.

### 6.9 `GET /health` — Health Check

> **What it does:** A simple "is the server alive?" check. Returns `{ "status": "ok", "version": "0.1.0" }`. The dashboard uses this to show a green (healthy) or red (down) indicator.

---

## 7. GitHub Integration Layer

**In plain English:** This section covers everything that talks to GitHub — downloading repository code, reading bug reports, and creating pull requests. There are three components, each with a specific job.

### 7.1 `RepoCloner` — Workspace Management

> **What it does:** Downloads a copy of a GitHub repository so the system can work on it locally. If we already have a copy, it updates it instead of downloading the whole thing again.

**File:** [`app/github/cloner.py`](file:///c:/Users/sushr/Downloads/autonomous-software-engineer-main/autonomous-software-engineer-main/app/github/cloner.py)

**How it converts a GitHub URL to a folder name:**
```
https://github.com/owner/repo  →  owner_repo
https://github.com/owner/repo.git  →  owner_repo
```
Uses regex: `github\.com[:/](.+?)(?:\.git)?$`, then replaces `/` with `_`.

**The download logic (3 branches):**

```
repo_path = /tmp/ase_workspace/{owner_repo}

if repo_path does NOT exist:
    → git clone {github_url} {repo_path}

elif repo_path exists AND origin URL matches:
    → git reset --hard        (discard any uncommitted changes)
    → git clean -fdx          (remove untracked files, including prior patch artifacts)
    → git checkout main       (try main first)
      └─ fallback: git checkout master
    → git pull                (fetch latest)

elif repo_path exists BUT origin URL DOESN'T match:
    → shutil.rmtree(repo_path)    (delete entire directory)
    → git clone {github_url} {repo_path}  (fresh clone)
```

**Design decision:** URL comparison strips trailing `/` and `.git` to handle both `https://github.com/o/r` and `https://github.com/o/r.git` formats.

**Error recovery:** If *any* git operation fails during the update path (e.g., corrupted repo, merge conflict), the entire directory is deleted and a fresh clone is performed. This ensures the workspace is always in a clean, predictable state.

### 7.2 `GitHubClient` — Issue Fetching

> **What it does:** Reads bug reports (issues) from GitHub's API, including the description and any comments people have left.

**File:** [`app/github/client.py`](file:///c:/Users/sushr/Downloads/autonomous-software-engineer-main/autonomous-software-engineer-main/app/github/client.py)

- Wraps PyGithub's `Github` class.
- Instantiated with `@lru_cache(maxsize=1)` via `get_github_client()` — singleton for the process lifetime.
- If `GITHUB_TOKEN` is not set, `self._gh = None` and `available` property returns `False`. All operations become no-ops — nothing crashes, GitHub features just become unavailable.
- `fetch_issue(github_url, issue_number)` method:
  - Extracts the `owner/repo` slug from the URL using the same regex pattern as `RepoCloner`.
  - Fetches the issue object via PyGithub.
  - Combines the issue body with up to **5 comments** to provide richer context. Comments are prefixed with `--- Comment by {username} ---` so the AI can tell them apart.
  - Returns a `FetchedIssue` dataclass with `number`, `title`, `description`, and `labels`.

### 7.3 `PRBuilder` — Pull Request Creation

> **What it does:** Creates a pull request on GitHub with the AI-generated fix. If GitHub isn't configured, it gracefully skips this step instead of crashing.

**File:** [`app/github/pr_builder.py`](file:///c:/Users/sushr/Downloads/autonomous-software-engineer-main/autonomous-software-engineer-main/app/github/pr_builder.py)

- Uses `get_github_client()` singleton.
- Calls `repo.create_pull(title, body, base, head)` via PyGithub.
- `base` branch defaults to `"main"` (set in the `PRDraft.base_branch` field).
- `head` branch is the `fix/auto-{timestamp}` branch created by `PatchApplicator`.
- **Graceful degradation:** If `GITHUB_TOKEN` is not set or `get_repo()` returns `None`, the draft is returned as-is without a `pr_url`. The pipeline still completes successfully — you just won't get a PR URL. The fix is still committed locally.
- On any exception during PR creation (e.g., branch not pushed, auth failure), the error is logged and the draft is returned without a URL — **no exception propagates**.

---

## 8. LLM Abstraction Layer — Provider Cascade & Prompt Engineering

**In plain English:** "LLM" stands for Large Language Model — these are the AI models (like ChatGPT, Gemini, etc.) that can understand and generate text. This section explains how we connect to AI models and how we ask them questions in a way that gets useful answers.

### 8.1 Provider Cascade

> **What's a cascade?** The system tries to use AI providers in order of preference. If the first one isn't available, it tries the second. If that fails too, it tries the third. It's like having a backup plan for your backup plan.

**File:** [`app/llm.py`](file:///c:/Users/sushr/Downloads/autonomous-software-engineer-main/autonomous-software-engineer-main/app/llm.py)

`get_llm()` checks providers in priority order with try/except fallback:

```
1. GOOGLE_API_KEY is set?
   ├─ Yes → try ChatGoogleGenerativeAI(model="gemini-2.0-flash-lite", temp=0.2)
   │   ├─ Success → return Gemini
   │   └─ Exception → log warning, fall through
   └─ No → fall through

2. HF_TOKEN is set?
   ├─ Yes → try HuggingFaceEndpoint(repo_id=HF_MODEL, max_new_tokens=4096, temp=0.2)
   │        → wrap in ChatHuggingFace(llm=endpoint)
   │   ├─ Success → return HuggingFace
   │   └─ Exception → log warning, fall through
   └─ No → fall through

3. Always available:
   → ChatOllama(base_url=OLLAMA_BASE_URL, model=OLLAMA_MODEL, temp=0.2)
   → (tries langchain_ollama first, falls back to langchain_community import)
```

**Why `temperature=0.2`?** "Temperature" controls how creative/random the AI's responses are. Low temperature (0.2) means the AI gives more predictable, focused answers — which is what we want when generating code and structured JSON responses. We didn't use zero because some AI providers don't support it or produce weirdly repetitive output.

**Why `convert_system_message_to_human=True` for Gemini?** The Gemini API doesn't natively support a distinct "system" role in the same way as OpenAI. This flag converts `SystemMessage` into a `HumanMessage` prefix, which works reliably with the Gemini chat interface.

**Why `max_new_tokens=4096` for HuggingFace?** The Inference API has a default limit of ~250 tokens. Code patches require much more output, so this is explicitly raised.

### 8.2 Prompt Engineering Patterns

> **What's prompt engineering?** It's the art of asking AI the right questions in the right way to get useful answers. The quality of the output heavily depends on how you phrase the input.

All three AI-backed steps (analysis, code fix, PR generation) follow the same pattern:

1. **System prompt** — Defines the role, output schema (exact JSON structure), and rules. For example, the IssueAnalysisAgent's system prompt:
   ```
   You are an expert software engineer analyzing a GitHub issue.
   Given an issue and retrieved relevant code snippets, identify:
   1. The root cause of the bug
   2. Your reasoning
   3. Which files are affected
   ...
   Respond ONLY with valid JSON matching this exact schema: { ... }
   ```
   The prompt also asks for `keywords` — symbol names the LLM thinks are involved. These are used to improve subsequent retrieval.

2. **User prompt** — Provides the specific bug report, code, and context for this particular task.

3. **Response parsing** — The AI's response is cleaned up, parsed as JSON, and validated into Pydantic models.

#### Code fence stripping algorithm:
```python
if raw.startswith("```"):
    raw = raw.split("```")[1]     # Take content after first fence
    if raw.startswith("json"):
        raw = raw[4:]             # Remove "json" language tag
    raw = raw.rsplit("```", 1)[0]  # Remove closing fence (if present)
```
This handles AI models that wrap JSON in `` ```json ... ``` `` formatting (common with Gemini and open-source models).

**Key prompt rules for the Code Fix agent:**
```
Rules:
- Only modify code that is directly related to the bug
- Keep changes minimal and focused
- The original_code must be the EXACT text currently in the file (copy it verbatim)
- The new_code must be valid, complete replacement code
```

The "copy verbatim" instruction is critical — when we apply the fix, we use text search-and-replace (`find this exact text → replace with new text`). If the AI paraphrases or reformats the original code instead of copying it exactly, the search-and-replace will fail and the patch won't be applied.

**How code context is formatted for the AI:**
```
[1] register_user (function) — app/auth.py:12-25
Match: exact (score=1.00)
```python
def register_user(email):
    ...
```
```

This format gives the AI the file location alongside the actual source code, so it can generate patches that reference the correct files.

---

## 9. LLM Retry & Rate-Limit Handling

**In plain English:** When you call an AI service over the internet, sometimes it fails — maybe the service is overloaded, maybe you're making too many requests too fast, or maybe the server just had a hiccup. This section explains how the system automatically retries failed AI calls instead of crashing.

> **What's a rate limit?** AI services limit how many requests you can make per minute. If you exceed the limit, they send back a "429 Too Many Requests" error and ask you to wait before trying again.

**File:** [`app/utils/retry.py`](file:///c:/Users/sushr/Downloads/autonomous-software-engineer-main/autonomous-software-engineer-main/app/utils/retry.py)

The `@llm_retry` decorator (using Tenacity) is applied to:
- `IssueAnalysisAgent.analyze()`
- `CodeFixAgent.generate_fix()`
- `PRGenerationAgent.generate_pr()`

### Retry decision logic:

The system checks error messages with string matching to classify the failure:

```python
def _is_rate_limit(exc):
    # Checks for: "429", "rate limit", "quota", "resource_exhausted", "too many requests"
    return any(k in str(exc).lower() for k in (...))

def _is_retryable(exc):
    # Rate limits OR server errors
    return _is_rate_limit(exc) or any(k in str(exc).lower() for k in ("500","502","503","504","timeout"))
```

- **Rate limit errors** → **Yes, retry** — but wait a while first
- **Server errors (5xx, timeout)** → **Yes, retry** — temporary problem
- **Everything else** → **No, don't retry** — retrying won't help

### Wait strategy (custom, not built-in Tenacity waits):

```python
def _wait_for_rate_limit(retry_state):
    exc = retry_state.outcome.exception()
    if _is_rate_limit(exc):
        return random.uniform(45, 90)      # 45-90 seconds for rate limits
    else:
        backoff = min(2 ** attempt, 15)     # Exponential: 2, 4, 8, 15, 15...
        jitter = random.uniform(0, 3)      # Random jitter 0-3 seconds
        return backoff + jitter
```

**Why 45–90 seconds for rate limits?** Gemini's free tier enforces per-minute quotas. The 429 response typically asks for a 60-second wait. Using 45–90s with jitter ensures we don't all retry at exactly the same time if multiple requests are in flight.

**Configuration:** Maximum **5 attempts** total (`stop_after_attempt(5)`). After 5 failures, the exception is re-raised and propagates up to the LangGraph node, where it's caught and stored in `AgentState.error`.

---

## 10. Code Parsing — Tree-Sitter AST Extraction

**In plain English:** Before the AI can fix code, it needs to understand what code exists in the repository. This section explains how the system reads through every code file and builds a catalogue of all functions and classes — like creating an index for a textbook.

> **What's an AST?** AST stands for "Abstract Syntax Tree." It's a structured representation of code that a computer can understand. Instead of seeing code as plain text, an AST represents it as a tree of nodes — "this is a function called `foo`, it takes two parameters, and its body contains these statements." Tree-Sitter is a library that builds these trees very quickly.

**File:** [`app/parsers/tree_sitter_parser.py`](file:///c:/Users/sushr/Downloads/autonomous-software-engineer-main/autonomous-software-engineer-main/app/parsers/tree_sitter_parser.py)

### Supported Languages & AST Node Types:

| Extension | Language | AST Node Types Extracted |
|-----------|----------|---------------------------|
| `.py` | Python | `function_definition`, `class_definition` |
| `.js` | JavaScript | `function_declaration`, `class_declaration`, `method_definition` |
| `.ts`, `.tsx` | TypeScript | `function_declaration`, `class_declaration`, `method_definition` |

### Skipped Directories:

The parser ignores common "junk" directories that don't contain useful application code:
```python
SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv",
             "env", "dist", "build", ".mypy_cache", ".pytest_cache"}
```
These are checked using `any(skip in file_path.parts for skip in SKIP_DIRS)` — matches at any depth in the path.

### How parsing works, step by step:

1. **Identify the language:** Look at the file extension (`.py` → Python, `.js` → JavaScript, etc.). If it's not a supported extension, skip the file.
2. **Read the file:** Read the raw bytes from disk. If the file can't be read (e.g., permission denied), skip it with a warning — don't crash.
3. **Build the syntax tree:** Use the language-specific Tree-Sitter parser (pre-built in `__init__` for all 3 languages).
4. **Walk the tree:** Manual recursive walk (not the Tree-Sitter Query API) for compatibility across `tree-sitter ≥0.23.x`:
   ```python
   def _walk(node, target_types):
       if node.type in target_types:
           yield node
       for child in node.children:
           yield from _walk(child, target_types)
   ```
5. **Extract the name:** Find the first `identifier` or `property_identifier` child of each definition node. If none found, use `anonymous_{start_line}`.
6. **Avoid duplicates:** Track `(start_line, end_line)` pairs in a `seen` set to avoid duplicates (can happen with nested class methods since both the class and its methods are yielded).
7. **Extract the source code:** Use line-based slicing (`lines[start_line-1:end_line]`) rather than byte offsets for correctness with multi-byte encodings.

### How it determines what type of symbol it found:

```
If the node type contains "class"    → It's a CLASS
If the node type contains "method"   → It's a METHOD
If its first keyword is "async"      → It's an ASYNC_FUNCTION
Otherwise                            → It's a regular FUNCTION
```

### Docstring extraction (Python only):

For Python functions, the parser also extracts docstrings (the description text that appears right after a function's definition, enclosed in triple quotes `"""..."""`). This extra context helps the AI understand what the function is supposed to do. JavaScript and TypeScript don't have a standard docstring format that's part of the AST, so this step is skipped for those languages.

### Repository scanning:

The `scan_repository()` function simply walks through every file in the repository, applies the parsing logic above to each supported file, and returns one big list of all discovered functions, classes, and methods.

---

## 11. Vector Store — FAISS Embedding & Indexing

**In plain English:** After we've extracted all the functions and classes from a repository, we need a way to *search* through them efficiently. This section explains how we convert code into numbers (embeddings) and use a fast search engine (FAISS) to find relevant code given a bug description.

> **What's an embedding?** Imagine you could represent any piece of text as a point in space. Similar texts would be close together, and different texts would be far apart. That's what an embedding does — it converts text into a list of numbers (a "vector") that captures its meaning. For example, the embedding for "validate email address" would be close to the embedding for "check if email is valid" even though the words are different.

**File:** [`app/vectorstore/faiss_store.py`](file:///c:/Users/sushr/Downloads/autonomous-software-engineer-main/autonomous-software-engineer-main/app/vectorstore/faiss_store.py)

### The Embedding Model

- **Model:** `all-MiniLM-L6-v2` — a small, efficient AI model specifically designed for creating embeddings
- **Output:** 384 numbers per input (a 384-dimensional vector)
- **Runs locally** on your machine — no internet connection or API keys needed. First time it runs, it downloads ~22MB; after that, it uses the cached copy.
- **L2 normalisation:** `faiss.normalize_L2(vectors)` is applied after encoding. This converts inner product (IP) to cosine similarity. In plain terms, we scale each vector so they have unit length — this mathematical step lets us use "inner product" (a fast operation) to compute "cosine similarity" (what we actually want).

### The FAISS Index

```python
self._index = faiss.IndexFlatIP(EMBEDDING_DIM)  # 384-dimensional, inner product search
```

> **What's FAISS?** FAISS (Facebook AI Similarity Search) is a library from Meta that's really good at finding similar vectors quickly. Think of it as a phone book, but instead of looking up people by name, you look up code by meaning.

- **`IndexFlatIP`** means "brute-force inner product search" — it compares the query against *every* stored vector to find the best matches. No shortcuts, exact results.
- After normalisation, inner product is mathematically equivalent to cosine similarity — a standard measure of how similar two vectors are (1.0 = identical meaning, 0.0 = completely unrelated).
- **Why brute force?** For our expected scale (a few hundred to a few thousand code symbols per repo), brute-force search takes less than 1 millisecond. Fancier approximate search methods would add complexity without any noticeable speed improvement.

### The Slot ↔ Symbol Mapping

The critical invariant: **FAISS slot index `i` maps 1:1 to `self._symbols[i]`.**

```python
# During indexing:
self._index.add(vectors)      # vectors[0] → slot 0, vectors[1] → slot 1, ...
self._symbols.extend(symbols)  # symbols[0] ↔ slot 0, symbols[1] ↔ slot 1, ...

# During search:
distances, indices = self._index.search(query_vector, k)
# indices[0][j] = slot number → self._symbols[slot] = the matching Symbol object
```

This parallel list design is simple, fast, and eliminates the need for a separate ID-to-symbol mapping.

### Search Result Scoring

```python
score = float(np.clip(dist, 0.0, 1.0))
# dist is already cosine similarity (0..1) because vectors are L2-normalised
# Clip ensures we don't return negative values (shouldn't happen but safety guard)
```

### What Gets Saved to Disk

Two files per indexed repository:

| File | Format | Contents |
|------|--------|----------|
| `{path}.faiss` | FAISS binary | The raw vector index |
| `{path}.symbols.pkl` | Python pickle | The `list[Symbol]` in slot order |

**Why pickle for symbols?** Pydantic models can be pickled, and it preserves the exact Python objects including all fields. JSON serialisation would work but requires model reconstruction on load.

Each repository gets its own folder, so multiple repos don't interfere with each other:
```
data/indices/
├── owner_repo1/        ← Index for repo1
│   ├── symbol_index.json
│   ├── faiss_index.faiss
│   └── faiss_index.symbols.pkl
└── owner_repo2/        ← Index for repo2
    ├── symbol_index.json
    ├── faiss_index.faiss
    └── faiss_index.symbols.pkl
```

---

## 12. Hybrid Retrieval Engine — Exact + Semantic Search

**In plain English:** When the AI needs to find code related to a bug, we search in two different ways and combine the results. It's like searching for a book in a library — you might search by exact title *and* by topic, then merge the results to get the best coverage.

### 12.1 Exact Matcher — Finding Code Mentioned by Name

> **What it does:** Looks for function and class names that appear literally in the bug report. If someone writes "the `validate_email` function crashes," we can directly find the function called `validate_email`.

**File:** [`app/retrieval/exact_matcher.py`](file:///c:/Users/sushr/Downloads/autonomous-software-engineer-main/autonomous-software-engineer-main/app/retrieval/exact_matcher.py)

**Tokenisation algorithm:**
```python
Input: "registerUser endpoint throws error in validate_email"

1. Extract all identifiers via regex: \b([a-zA-Z_][a-zA-Z0-9_]*)\b
   → {"registerUser", "endpoint", "throws", "error", "in", "validate_email"}

2. For each identifier:
   a. Add lowercase version: "registeruser", "validate_email"
   b. Split camelCase: "registerUser" → ["register", "User"]
      → Add parts ≥3 chars: "register", "user"
   c. If camelCase split produced multiple parts, join with underscore:
      → "register_user"
   d. Split snake_case: "validate_email" → ["validate", "email"]
      → Add parts ≥3 chars: "validate", "email"

Final tokens: {"registeruser", "register", "user", "register_user",
               "validate_email", "validate", "email", "endpoint", ...}
```

**Lookup:** A `dict[str, Symbol]` is built from the symbol index with lowercase keys. Each token is looked up in O(1).

**Scoring:**
- **Direct name match** (the search term exactly matches a function name) → score **1.0** (perfect match)
- **Partial match** (a sub-part of the search term matches) → score **0.7** (good match, but less certain)

**Why partial matching?** Developers often refer to functions informally — saying "the register function" when they mean `register_user`, or using camelCase `registerUser` when the actual function is `register_user`. Partial matching catches these cases.

### 12.2 Semantic Retriever — Finding Code by Meaning

> **What it does:** Converts the bug report into an embedding (numerical fingerprint) and uses FAISS to find code with similar meaning, even if none of the exact names match.

**File:** [`app/retrieval/semantic_retriever.py`](file:///c:/Users/sushr/Downloads/autonomous-software-engineer-main/autonomous-software-engineer-main/app/retrieval/semantic_retriever.py)

This is simpler than it sounds:
1. Take the full bug report text (`title + description`).
2. Convert it to an embedding using `all-MiniLM-L6-v2`.
3. Ask FAISS: "find me the `top_k` most similar code embeddings."
4. Return those matches with their similarity scores.

### 12.3 Merging the Results

> **How do we combine exact and semantic search results?** Exact matches go first (they're more precise), then semantic matches fill the remaining slots.

**File:** [`app/agents/retrieval_agent.py`](file:///c:/Users/sushr/Downloads/autonomous-software-engineer-main/autonomous-software-engineer-main/app/agents/retrieval_agent.py)

```python
def _merge(exact, semantic, top_k):
    seen = set()
    merged = []

    # Phase 1: Exact matches first (higher precision)
    for ctx in exact:
        if ctx.symbol.name not in seen:
            seen.add(ctx.symbol.name)
            merged.append(ctx)

    # Phase 2: Semantic matches fill remaining slots
    for ctx in semantic:
        if ctx.symbol.name not in seen:
            seen.add(ctx.symbol.name)
            merged.append(ctx)

    return merged[:top_k]  # Cap at RETRIEVAL_TOP_K (default: 10)
```

**Why exact-first?** If someone specifically mentioned `validate_email` in their bug report, we *definitely* want that function in the results. Semantic search might miss it (or rank it lower) because it searches by meaning, not by name. By putting exact matches first, we guarantee that directly-referenced code is always included.

**Deduplication key:** `symbol.name`. If the same function appears in both exact and semantic results, the exact match version is kept (it's added first).

---

## 13. Agent Orchestration — LangGraph State Machine

**In plain English:** This is the "control centre" of the system — it defines the order in which steps run and the rules for what happens when things go wrong. It's built as a state machine (a flowchart) using a library called LangGraph.

> **What's a state machine?** A set of "states" (steps) with defined transitions between them. Like a board game: you start at one square, and depending on what happens (roll a 6? go forward. Land on a snake? go back), you move to a different square. The "state" is all the information accumulated so far — the shared notepad that every step can read and write to.

**File:** [`app/workflow/graph.py`](file:///c:/Users/sushr/Downloads/autonomous-software-engineer-main/autonomous-software-engineer-main/app/workflow/graph.py)

### How the Graph is Built

```python
# Create the flowchart with a shared notepad (AgentState)
graph = StateGraph(AgentState)

# Add the 6 steps (nodes)
graph.add_node("analyze_issue",    analyze_issue)     # Step 1: Understand the bug
graph.add_node("retrieve_context", retrieve_context)   # Step 2: Find relevant code
graph.add_node("generate_fix",     generate_fix)       # Step 3: Write a fix
graph.add_node("apply_patch",      apply_patch)        # Step 4: Apply the fix to files
graph.add_node("run_tests",        run_tests)          # Step 5: Run tests
graph.add_node("generate_pr",      generate_pr)        # Step 6: Create a pull request

# Define the starting point
graph.set_entry_point("analyze_issue")

# Connect steps in order (linear flow)
graph.add_edge("analyze_issue",    "retrieve_context")  # 1 → 2
graph.add_edge("retrieve_context", "generate_fix")      # 2 → 3
graph.add_edge("generate_fix",     "apply_patch")       # 3 → 4
graph.add_edge("apply_patch",      "run_tests")         # 4 → 5
graph.add_edge("generate_pr",      END)                 # 6 → Done!

# The critical decision point: what happens after tests run?
graph.add_conditional_edges("run_tests", route_after_tests)
```

### The Retry Loop — What Happens After Tests

This is the most interesting part of the flowchart:

```python
def route_after_tests(state: AgentState) -> str:
    # Test passed → proceed to PR
    if state.get("test_result") and state["test_result"].passed:
        return "generate_pr"

    # Max retries exceeded → abort
    if state.get("retry_count", 0) >= settings.max_retries:  # default: 3
        return END

    # Tests failed, retries remaining → loop back to analyze
    return "analyze_issue"
```

**Why go all the way back to `analyze_issue` instead of just `generate_fix`?** If the fix was wrong, it might be because the AI misidentified the root cause in the first place. Going back to the analysis step gives the AI a chance to reconsider the problem entirely, rather than just trying a different fix for the same (possibly wrong) diagnosis.

### Checkpointing — Saving Progress

```python
graph.compile(checkpointer=MemorySaver())
```

After each step completes, the current state (the "shared notepad") is saved in memory. This means:
- We can read the final result after the pipeline finishes.
- In the future, we could add step-by-step debugging and replay features.

### Thread IDs — Keeping Concurrent Runs Separate

Each workflow invocation gets a unique `thread_id`:
- Manual issues: `"issue-{issue_number or 'manual'}"`
- GitHub issues: `"gh-issue-{issue_number}"`

Thread IDs are required by `MemorySaver` and prevent state leakage between concurrent runs — each run has its own separate notepad.

### Module-Level Compilation

```python
compiled_graph = build_graph()  # Line 188 — runs at import time
```

The graph (and the LLM it creates) is instantiated **once** when the server starts. All requests share the same compiled graph but with different thread IDs for state isolation.

---

## 14. Agent Deep Dives

**In plain English:** Each step in the pipeline is handled by a specialised "agent" — a chunk of code designed to do one specific job well. This section goes into detail on each agent's inputs, outputs, and quirks.

### 14.1 `IssueAnalysisAgent` — Understanding the Bug

> **What it does:** Takes a bug report and (optionally) some relevant code, and produces a structured analysis: what's the root cause, how severe is it, and which files are affected.

**File:** [`app/agents/issue_analysis_agent.py`](file:///c:/Users/sushr/Downloads/autonomous-software-engineer-main/autonomous-software-engineer-main/app/agents/issue_analysis_agent.py)

**Input:** The bug report + any code snippets retrieved so far
**Output:** A structured analysis with 7 fields (root cause, reasoning, affected files, suggested approach, severity, confidence, and keywords)

**On first pass (no retrieval context yet):** The agent creates an empty `RetrievalResult` in the `analyze_issue` node function:
```python
context = state.get("retrieval") or RetrievalResult(
    query="", results=[], total_exact=0, total_semantic=0, merged_count=0
)
```
This means the first analysis is based purely on the issue text. On retry, the previous retrieval context is available, giving the AI more context.

**Context formatting:** Numbered blocks with symbol type, file path, line range, match type, score, and full source code in fenced code blocks.

**Error handling:** `json.JSONDecodeError`, `KeyError`, `ValueError` are caught and wrapped in a `ValueError` with the raw LLM output for debugging.

### 14.2 `CodeFixAgent` — Writing the Fix

> **What it does:** Takes the bug analysis, the relevant code snippets, and the original bug report, and produces a set of code changes (patches) that should fix the problem.

**File:** [`app/agents/code_fix_agent.py`](file:///c:/Users/sushr/Downloads/autonomous-software-engineer-main/autonomous-software-engineer-main/app/agents/code_fix_agent.py)

**Input:** Bug report + analysis + relevant code
**Output:** A list of patches, each specifying which file to change, what the old code looks like, and what the new code should be

**Example AI output:**
```json
[
  {
    "file_path": "app/auth.py",
    "operation": "replace",
    "original_code": "if email:\n    validate(email)",
    "new_code": "if email is not None:\n    validate(email)",
    "start_line": 12,
    "end_line": 13,
    "description": "Fix null check: use 'is not None' instead of truthy check"
  }
]
```

**Single-object fallback:** If the LLM returns a single object `{...}` instead of an array `[{...}]`, it's wrapped in a list:
```python
if not isinstance(patches_data, list):
    patches_data = [patches_data]
```

### 14.3 `PatchApplicator` — Applying Changes to Files

> **What it does:** Takes the patches generated by the AI and actually writes them into the code files on disk. Then it formats the code, creates a new Git branch, and commits the changes.

**File:** [`app/agents/patch_applicator.py`](file:///c:/Users/sushr/Downloads/autonomous-software-engineer-main/autonomous-software-engineer-main/app/agents/patch_applicator.py)

**How each type of patch operation works:**

| Operation | Algorithm | Edge Cases |
|-----------|-----------|------------|
| `REPLACE` | `content.replace(original_code, new_code, 1)` — replaces first occurrence only | Raises `ValueError` if `original_code` not found — this is the **hallucination guard**. The AI made up code that doesn't exist in the file. |
| `INSERT` | Splits into lines, inserts `new_code + "\n"` at `min(start_line, len(lines))` | Bounds-checked to prevent IndexError |
| `DELETE` | If `original_code` provided: `content.replace(original_code, "", 1)`. Otherwise: `del lines[start_line-1:end_line]` | Both paths handled — LLM may or may not provide original_code |

**Git workflow:**
1. `git checkout -b fix/auto-{timestamp}` — create a new branch from current HEAD
2. Apply all patches to disk
3. Run `post_patch_apply_hook` — `ruff --fix` then `black` on patched `.py` files
4. `git add -A` — stage everything
5. `git commit -m "fix: {description}\n\nApplied N patch(es) across M file(s)."`

**Commit message format:** Follows conventional commits (`fix:` prefix) for compatibility with changelog generators.

**Returned `PatchSet`:** A new `PatchSet` is constructed with `applied=True`, `applied_at` timestamp, and `branch_name` set.

### 14.4 `RetrievalAgent` — Finding Relevant Code

> **What it does:** Coordinates the exact matcher and semantic retriever to find the most relevant code for a given bug report.

**File:** [`app/agents/retrieval_agent.py`](file:///c:/Users/sushr/Downloads/autonomous-software-engineer-main/autonomous-software-engineer-main/app/agents/retrieval_agent.py)

The process:
1. **Load the index from disk** — always reads a fresh copy to pick up any repos that were indexed after the server started.
2. **Handle missing index gracefully** — if no index exists for this repo, return an empty result (retrieval is skipped, not treated as an error).
3. **Load the FAISS vector index** — similarly loaded fresh, with graceful error handling.
4. **Run both search strategies** (exact + semantic) and merge the results.

### 14.5 `PRGenerationAgent` — Writing the PR Description

> **What it does:** Uses the AI to write a professional pull request title and description, then creates the PR on GitHub.

**File:** [`app/agents/pr_generation_agent.py`](file:///c:/Users/sushr/Downloads/autonomous-software-engineer-main/autonomous-software-engineer-main/app/agents/pr_generation_agent.py)

**What it generates:**
- **Title:** A short, conventional commit-style title (e.g., `"fix: handle None email in registration flow"`)
- **Description:** A Markdown body with sections for Summary, Root Cause, and Changes
- **Root cause summary:** A one-sentence explanation
- **File summaries:** Per-file descriptions of what was changed

**Test results are included in the PR:**
```
✅ 12 tests passed   (if all tests passed)
❌ 3 tests failed    (if some tests failed)
```

After generating the text, it calls `PRBuilder.create_pr()` to actually create the pull request on GitHub.

---

## 15. Hook System — Validation & Formatting Gates

**In plain English:** Hooks are checkpoint guards placed at key moments in the pipeline. Before or after critical steps, they check "are we in a good state to proceed?" and block progress if something is wrong. Think of them like security checkpoints at an airport — you can't board the plane unless you've passed each check.

### What Each Hook Checks

Hooks are **synchronous validation functions** that raise `HookValidationError` to abort the current step if preconditions aren't met.

| Hook | When | File | Validates |
|------|------|------|-----------|
| `pre_code_generation_hook` | Before `generate_fix` | [`pre_code_generation.py`](file:///c:/Users/sushr/Downloads/autonomous-software-engineer-main/autonomous-software-engineer-main/app/hooks/pre_code_generation.py) | Issue title non-empty, description non-empty, `repository_path` set, retrieval results non-empty |
| `post_code_generation_hook` | After `generate_fix`, before disk write | [`post_code_generation.py`](file:///c:/Users/sushr/Downloads/autonomous-software-engineer-main/autonomous-software-engineer-main/app/hooks/post_code_generation.py) | PatchSet non-empty; `ast.parse()` on every Python `new_code` snippet |
| `post_patch_apply_hook` | After patches written to disk, before `git add` | [`post_code_generation.py`](file:///c:/Users/sushr/Downloads/autonomous-software-engineer-main/autonomous-software-engineer-main/app/hooks/post_code_generation.py) | Runs `ruff --fix` then `black` on patched `.py` files |
| `pre_test_hook` | Before `run_tests` | [`pre_test.py`](file:///c:/Users/sushr/Downloads/autonomous-software-engineer-main/autonomous-software-engineer-main/app/hooks/pre_test.py) | Repository path exists; Docker daemon is reachable (skipped if no test files) |
| `post_test_hook` | After `run_tests` | [`post_test.py`](file:///c:/Users/sushr/Downloads/autonomous-software-engineer-main/autonomous-software-engineer-main/app/hooks/post_test.py) | Raises `HookValidationError` if tests failed (blocks PR path) |
| `pre_pr_hook` | Before `generate_pr` | [`pre_pr.py`](file:///c:/Users/sushr/Downloads/autonomous-software-engineer-main/autonomous-software-engineer-main/app/hooks/pre_pr.py) | `patch_set.applied == True`, `branch_name` set, tests passed or skipped, branch exists in git |

### The Two-Stage Code Validation Flow

```
Stage 1: SYNTAX CHECK (in generate_fix node)
├─ post_code_generation_hook
├─ For each Python patch: ast.parse(new_code)
├─ Catches SyntaxError → HookValidationError
└─ Runs BEFORE anything is written to disk

Stage 2: FORMAT + LINT (in apply_patch, after disk write)
├─ post_patch_apply_hook
├─ ruff check --fix {files}    ← auto-fix lint issues
├─ black {files}               ← reformat
├─ Runs AFTER patches are on disk, BEFORE git add
└─ Failures here are logged as warnings, not fatal
```

**Design rationale for two stages:** Stage 1 prevents syntactically broken code from ever touching the filesystem. Stage 2 ensures the committed code matches the project's formatting standards. If Stage 2 formatting fails (e.g., `ruff` not installed in the target repo's environment), the pipeline continues — the code is syntactically valid but might not match style preferences.

---

## 16. Sandboxed Test Execution — Docker Runner

**In plain English:** After the AI applies a fix, we need to check if the fix actually works by running the project's existing tests. But we can't just run those tests directly on our machine — the project might have conflicting dependencies, or the tests might do dangerous things. So we run them inside a Docker container — a lightweight, isolated "mini-computer" that's thrown away after use.

> **What's Docker?** Docker lets you create lightweight, isolated environments (containers) that act like tiny virtual computers. Each container has its own set of installed software, independent of your main machine. When you're done, you just delete the container — nothing on your actual machine is affected.

**File:** [`app/docker_runner/runner.py`](file:///c:/Users/sushr/Downloads/autonomous-software-engineer-main/autonomous-software-engineer-main/app/docker_runner/runner.py)

### Container Setup

```
Image: python:3.11-slim
Mount: {repo_path} → /repo (read-write)
Working dir: /repo
Auto-remove: True
Timeout: 120 seconds (configurable via docker_timeout setting)
```

### What Runs Inside the Container

```bash
bash -c '
  pip install -q pytest;
  [ -f requirements.txt ] && pip install -q -r requirements.txt;
  [ -f setup.py ] && pip install -q .;
  ([ -f pyproject.toml ] && grep -q -E "^\[(project|build-system)\]" pyproject.toml) && pip install -q .;
  pytest -v --tb=short 2>&1
'
```

**Dependency installation order:**
1. `pytest` — always, guaranteed to be available
2. `requirements.txt` — if present, install pinned dependencies
3. `setup.py` — if present, install the package in editable mode
4. `pyproject.toml` — if present AND contains `[project]` or `[build-system]`, install the package

**Why the `grep` check for `pyproject.toml`?** Not all `pyproject.toml` files define a package. Some only configure tools (e.g., `[tool.ruff]`). Running `pip install .` on a non-package pyproject.toml would fail. The `grep` ensures we only try to install when there's an actual package definition.

### Output Parsing

```python
_PYTEST_SUMMARY_RE = re.compile(
    r"(?:(\d+) passed)?.*?(?:(\d+) failed)?.*?in [\d.]+s"
)
```

Parses the last matching line in the output (scanning in reverse) to extract pass/fail counts from pytest's summary line, e.g.: `"5 passed, 1 failed in 1.23s"`.

### Smart Shortcut — No Tests? No Problem.

```python
test_files = list(repo_path.rglob("test_*.py")) + list(repo_path.rglob("*_test.py"))
if not test_files:
    return TestResult(passed=True, exit_code=0, skipped=True, ...)
```

If the repository doesn't have any test files, the system skips Docker entirely and moves straight to PR creation. Many small repos don't have tests, and we shouldn't block the pipeline because of that.

### Error Handling

| Error | Handling |
|-------|----------|
| Docker daemon unavailable | `self._client = None` at init; `run_tests` returns `TestResult(passed=False)` |
| Container exits non-zero | Caught via `docker.errors.ContainerError`; stderr is captured |
| Docker API error | Caught via `docker.errors.APIError`; str(e) is used as output |
| Timeout | Docker's built-in timeout kills the container after `docker_timeout` seconds |

---

## 17. Data Models — Complete Schema Reference

**In plain English:** Data models define the *shape* of data flowing through the system. Think of them as templates or forms — they specify what fields each piece of data must have, what type each field should be, and what values are acceptable. This ensures that when Step A passes data to Step B, Step B gets exactly what it expects.

All models use Pydantic v2, which automatically validates data when it's created. If you try to create a model with invalid data (e.g., putting a string where a number should be), it throws an error immediately.

### `IssueInput` ([`app/models/issue.py`](file:///c:/Users/sushr/Downloads/autonomous-software-engineer-main/autonomous-software-engineer-main/app/models/issue.py))

**What it represents:** The incoming bug report from the user.

| Field | Type | Validation | Description |
|-------|------|------------|-------------|
| `title` | `str` | `min_length=1, max_length=500` | Issue title |
| `description` | `str` | `min_length=1` | Full issue body (may include markdown, comments) |
| `issue_number` | `int \| None` | Optional | GitHub issue number |
| `labels` | `list[str]` | Default: `[]` | GitHub labels (e.g., `["bug", "P1"]`) |
| `repository_path` | `str` | Default: `""` | Absolute local path, set after cloning |

### `IssueSeverity` (Enum)

Values: `low`, `medium`, `high`, `critical` — assessed by the LLM during analysis.

### `IssueAnalysis` ([`app/models/issue.py`](file:///c:/Users/sushr/Downloads/autonomous-software-engineer-main/autonomous-software-engineer-main/app/models/issue.py))

**What it represents:** The AI's structured analysis of what's wrong and how to fix it.

| Field | Type | Validation | Description |
|-------|------|------------|-------------|
| `root_cause` | `str` | — | LLM-identified root cause |
| `reasoning` | `str` | — | Chain-of-thought explanation |
| `affected_files` | `list[str]` | — | Files likely needing changes |
| `suggested_approach` | `str` | — | Recommended fix strategy |
| `severity` | `IssueSeverity` | Enum | Risk assessment |
| `confidence` | `float` | `ge=0.0, le=1.0` | LLM's self-assessed confidence |
| `keywords` | `list[str]` | Default: `[]` | Symbol names for retrieval guidance |

### `Symbol` — A Code Building Block

**What it represents:** A single function, class, or method found during code scanning.

| Field | Type | Description |
|-------|------|-------------|
| `name` | Text | The function or class name (e.g., `validate_email`) |
| `symbol_type` | `function`/`async_function`/`class`/`method` | What kind of code block this is |
| `file_path` | Text | Which file it's in |
| `start_line` | Number | Where it starts (line number) |
| `end_line` | Number | Where it ends (line number) |
| `source_code` | Text | The complete source code of this function/class |
| `language` | `python`/`javascript`/`typescript` | What programming language |
| `docstring` | Text or None | The function's documentation (Python only) |

### `SymbolIndex` — The Complete Code Catalogue

**What it represents:** All symbols extracted from a repository, plus metadata about the indexing run.

| Field | Type | Description |
|-------|------|-------------|
| `symbols` | List of Symbols | Every function/class found (order matches FAISS index slots) |
| `repository_path` | Text | Where the repository is on disk |
| `indexed_at` | Text | When the indexing was done (ISO 8601 timestamp) |
| `total_files` | Number | How many files were scanned |
| `total_symbols` | Number | How many functions/classes were found |

### `RetrievedContext` — A Search Result

**What it represents:** A single code symbol that matched a search query, along with how it was found.

| Field | Type | Description |
|-------|------|-------------|
| `symbol` | Symbol | The matched function/class |
| `score` | Number (0.0–1.0) | How confident we are in this match |
| `match_type` | `"exact"` or `"semantic"` | How this result was found — by name match or by meaning similarity |

### `RetrievalResult` — Combined Search Results

**What it represents:** The merged output of both exact and semantic search.

| Field | Type | Description |
|-------|------|-------------|
| `query` | Text | What we searched for |
| `results` | List of RetrievedContext | The top results after merging and deduplication |
| `total_exact` | Number | How many exact matches were found (before merging) |
| `total_semantic` | Number | How many semantic matches were found (before merging) |
| `merged_count` | Number | Final count after deduplication and capping |

### `FilePatch` — A Single Code Change

**What it represents:** One specific change to make to one file.

| Field | Type | Description |
|-------|------|-------------|
| `file_path` | Text | Which file to change |
| `operation` | `replace`/`insert`/`delete` | What kind of change |
| `original_code` | Text or None | The existing code to find (None for inserts) |
| `new_code` | Text | The new code to put in place |
| `start_line` | Number | Where the change starts |
| `end_line` | Number | Where the change ends |
| `description` | Text | Human-readable explanation of the change |

### `PatchSet` — All Changes for a Fix

**What it represents:** The complete set of changes the AI wants to make to fix the bug.

| Field | Type | Description |
|-------|------|-------------|
| `patches` | List of FilePatch | All individual changes |
| `total_files` | Number | How many files are affected |
| `description` | Text | Overall summary of the fix |
| `applied` | True/False | Have these changes been written to disk yet? |
| `applied_at` | Text or None | When they were applied (timestamp) |
| `branch_name` | Text or None | The Git branch name (e.g., `fix/auto-20260912`) |

### `TestResult` — Test Execution Outcome

**What it represents:** What happened when we ran the project's tests.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `passed` | True/False | — | Did all tests pass? |
| `exit_code` | Number | — | Container exit code (0 = success) |
| `output` | Text | — | The raw test output (what pytest printed) |
| `duration_seconds` | Number | — | How long the tests took to run |
| `total_tests` | Number | 0 | Total number of tests detected |
| `passed_tests` | Number | 0 | How many tests passed |
| `failed_tests` | Number | 0 | How many tests failed |
| `skipped` | True/False | False | True if no test files were found (Docker wasn't even run) |

### `PRDraft` — The Pull Request

**What it represents:** Everything needed to create a GitHub pull request.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `title` | Text | — | PR title (e.g., `"fix: handle None email in registration flow"`) |
| `description` | Text | — | Full Markdown PR body with Summary, Root Cause, and Changes sections |
| `root_cause_summary` | Text | — | One-sentence root cause explanation |
| `files_changed` | List of text | — | Which files were modified |
| `file_summaries` | Dict | — | Per-file descriptions of what changed |
| `base_branch` | Text | `"main"` | The branch the PR merges into |
| `head_branch` | Text | — | The branch with the fix (e.g., `fix/auto-20260912`) |
| `test_results_summary` | Text | — | e.g., `"✅ 12 tests passed"` |
| `pr_url` | Text or None | None | URL of the created GitHub PR (if created successfully) |
| `pr_number` | Number or None | None | PR number on GitHub |

### `AgentState` — The Shared Notepad

**What it represents:** The data that flows through the entire pipeline. Every step reads from and writes to this shared state.

| Field | Type | Who Sets It | Who Reads It |
|-------|------|------------|-------------|
| `issue` | IssueInput | API layer (at the start) | All steps |
| `analysis` | IssueAnalysis or None | Step 1 (analyze_issue) | Steps 3, 6 |
| `retrieval` | RetrievalResult or None | Step 2 (retrieve_context) | Steps 1 (on retry), 3 |
| `patch_set` | PatchSet or None | Step 3 (generate_fix), updated by Step 4 | Steps 4, 6 |
| `test_result` | TestResult or None | Step 5 (run_tests) | Route decision, Step 6 |
| `pr_draft` | PRDraft or None | Step 6 (generate_pr) | Final API response |
| `error` | Text or None | Any step that encounters an error | Final API response |
| `retry_count` | Number | Step 5 (when tests fail) | Route decision (should we retry?) |

---

## 18. Configuration System

**In plain English:** Configuration is how you customise the system's behaviour without changing any code. Everything is controlled through a `.env` file — a simple text file where each line is `KEY=VALUE`. This section lists every setting you can change.

**File:** [`app/config.py`](file:///c:/Users/sushr/Downloads/autonomous-software-engineer-main/autonomous-software-engineer-main/app/config.py)

Key design decisions:
- **All settings have defaults** — the app starts even with a completely empty `.env` file. You only need to set the values you want to customise.
- **Unknown settings are ignored** — if you add a random `FOO=bar` to your `.env` file, the app won't crash.

### Full Configuration Reference

| Setting | Environment Variable | Default | What It Controls |
|---------|---------------------|---------|-----------------|
| `google_api_key` | `GOOGLE_API_KEY` | `""` (empty) | Your Gemini AI API key. Get one free at aistudio.google.com |
| `hf_token` | `HF_TOKEN` | `""` | Your HuggingFace API token. Get one free at huggingface.co |
| `hf_model` | `HF_MODEL` | `Qwen/Qwen2.5-Coder-32B-Instruct` | Which HuggingFace model to use for code generation |
| `ollama_base_url` | `OLLAMA_BASE_URL` | `http://localhost:11434` | Where your Ollama server is running (for local AI) |
| `ollama_model` | `OLLAMA_MODEL` | `codellama:7b` | Which Ollama model to use |
| `github_token` | `GITHUB_TOKEN` | `""` | GitHub Personal Access Token (needs `repo` + `pull_request` permissions) |
| `github_repo_owner` | `GITHUB_REPO_OWNER` | `""` | GitHub username of the repo owner |
| `github_repo_name` | `GITHUB_REPO_NAME` | `""` | Repository name on GitHub |
| `workspace_dir` | `WORKSPACE_DIR` | `/tmp/ase_workspace` | Where to store downloaded repositories |
| `faiss_index_path` | `FAISS_INDEX_PATH` | `./data/faiss_index` | Where to store the default FAISS vector index |
| `symbol_index_path` | `SYMBOL_INDEX_PATH` | `./data/symbol_index.json` | Where to store the default symbol index |
| `docker_image_name` | `DOCKER_IMAGE_NAME` | `ase-test-runner` | Docker image name (note: currently hardcoded to `python:3.11-slim` internally) |
| `docker_timeout` | `DOCKER_TIMEOUT` | `120` | How many seconds to wait before killing a test run |
| `embedding_model` | `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Which embedding model to use for code search |
| `retrieval_top_k` | `RETRIEVAL_TOP_K` | `10` | Maximum number of code snippets to retrieve per search |
| `max_retries` | `MAX_RETRIES` | `3` | How many times to retry if tests fail |
| `log_level` | `LOG_LEVEL` | `INFO` | How verbose the logs should be (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `app_host` | `APP_HOST` | `0.0.0.0` | Network address the server listens on |
| `app_port` | `APP_PORT` | `8000` | Port number the server listens on |

### Logging

All log messages use a consistent format:
```
2026-09-12 14:30:00 | INFO | app.agents.code_fix_agent | Generated 2 patches for 1 file
```

Each component logs under its own name (e.g., `app.agents.code_fix_agent`), making it easy to filter logs and find where a message came from.

---

## 19. Dependency Injection

**In plain English:** Some things in the system are expensive to create — loading the AI embedding model, connecting to Docker, building the search index. We don't want to create these from scratch every time someone makes an API request. Dependency injection is a pattern where we create these expensive things *once* and then share them across all requests.

> **Analogy:** Instead of each restaurant customer bringing their own oven, the restaurant has one oven that everyone shares. Dependency injection is the system that makes sure every request gets access to the shared oven.

**File:** [`app/api/dependencies.py`](file:///c:/Users/sushr/Downloads/autonomous-software-engineer-main/autonomous-software-engineer-main/app/api/dependencies.py)

```python
# This decorator means "the first time this function is called, run it and save the result.
# Every subsequent call returns the saved result without running the function again."
@lru_cache(maxsize=1)
def get_faiss_store():
    store = FAISSStore(model_name=settings.embedding_model)  # Load the embedding model
    try:
        store.load(settings.faiss_index_path)  # Try to load an existing index from disk
    except FileNotFoundError:
        pass  # No existing index — that's fine, start fresh
    return store

@lru_cache(maxsize=1)
def get_indexing_agent():
    return RepositoryIndexingAgent()

@lru_cache(maxsize=1)
def get_test_runner():
    return DockerTestRunner()
```

**How it's used in API routes:**
```python
@router.post("")
async def index_repository(
    request: IndexRequest,
    agent: RepositoryIndexingAgent = Depends(get_indexing_agent),
    #     ↑ FastAPI automatically calls get_indexing_agent() and passes the result
):
    ...
```

FastAPI's `Depends()` system calls the function for you and provides the result to your endpoint. Combined with `@lru_cache`, this means the expensive objects are created once and reused forever.

---

## 20. Dashboard — Frontend UI

**In plain English:** The dashboard is a web page you can open in your browser to interact with the system visually — submit bug reports, track progress, and view results. It's built with the simplest possible tech stack: plain HTML, CSS, and JavaScript, with no build tools or frameworks required.

**Location:** [`dashboard/`](file:///c:/Users/sushr/Downloads/autonomous-software-engineer-main/autonomous-software-engineer-main/dashboard)

| File | Purpose |
|------|---------|
| [`index.html`](file:///c:/Users/sushr/Downloads/autonomous-software-engineer-main/autonomous-software-engineer-main/dashboard/index.html) | The HTML structure — sidebar navigation and main content area |
| [`style.css`](file:///c:/Users/sushr/Downloads/autonomous-software-engineer-main/autonomous-software-engineer-main/dashboard/style.css) | All the styling — dark theme with modern aesthetics |
| [`app.js`](file:///c:/Users/sushr/Downloads/autonomous-software-engineer-main/autonomous-software-engineer-main/dashboard/app.js) | All the logic — rendering views, making API calls, handling forms |

### Features:
- **4 views:**
  - **Overview** — Stats and system status
  - **Submit Issue** — A form to submit new bug reports
  - **Task History** — Live progress tracking for submitted tasks (polls the API automatically)
  - **Repositories** — List of indexed repositories
- **Live step tracking:** When a task is running, the dashboard polls the status API and shows a real-time progress bar through all 8 pipeline steps
- **Health indicator:** A green or red dot in the sidebar showing whether the server is healthy
- **Clean typography:** Uses Inter and JetBrains Mono fonts from Google Fonts
- **Simple routing:** Uses URL hash (`#overview`, `#submit`, `#history`, `#repositories`) to switch between views

### Architecture:
- **No build step needed** — no webpack, no npm, no framework. Just open the HTML file (or navigate to `/dashboard` on the running server).
- Views are rendered by JavaScript and injected into the page dynamically.
- All API calls use relative URLs, so the dashboard works because it's served by the same FastAPI server that provides the API.

---

## 21. Testing Strategy

**In plain English:** Testing is how we make sure the system works correctly. We have automated tests that verify each component does what it's supposed to. This section explains what's tested, how, and what patterns we use.

**Location:** [`tests/`](file:///c:/Users/sushr/Downloads/autonomous-software-engineer-main/autonomous-software-engineer-main/tests)

### Test Files

| File | # of Tests | What It Checks |
|------|-----------|----------------|
| [`test_api.py`](file:///c:/Users/sushr/Downloads/autonomous-software-engineer-main/autonomous-software-engineer-main/tests/test_api.py) | 7 | Health endpoint works, indexing handles errors gracefully, async tasks work correctly, step tracking updates properly, unknown task IDs return 404, indices endpoint works |
| [`test_parsers.py`](file:///c:/Users/sushr/Downloads/autonomous-software-engineer-main/autonomous-software-engineer-main/tests/test_parsers.py) | 8 | Python functions/classes are parsed correctly, async functions are detected, source code is captured accurately, docstrings are extracted, unsupported file types are ignored, full repo scanning works, line numbers are correct |
| [`test_retrieval.py`](file:///c:/Users/sushr/Downloads/autonomous-software-engineer-main/autonomous-software-engineer-main/tests/test_retrieval.py) | 6 | Exact name matching works, camelCase splitting works, empty results for no matches, scoring is correct, match types are labelled correctly, multiple symbols can be matched |

### How Tests Work:

- **API tests** simulate a real client calling our API endpoints — but without actually starting a web server. They use a special test client that talks directly to the app in-process. This makes tests fast and reliable.
- **Background task tests** use mocking (replacing real code with fake versions) to avoid needing real Git repositories. They submit a task and then poll for status in a loop until it finishes.
- **Parser tests** create temporary files with known code content and verify the parser extracts the right symbols.
- **Retrieval tests** create a known set of symbols and verify the exact matcher's tokenisation and scoring logic produces the expected results.

### Configuration:
```toml
# In pyproject.toml:
asyncio_mode = "auto"    # Tests can use async/await without extra annotations
testpaths = ["tests"]    # Only look for tests in the tests/ folder
```

---

## 22. CI/CD Pipeline

**In plain English:** CI/CD stands for "Continuous Integration / Continuous Deployment." It means every time someone pushes code changes to GitHub, an automated system checks that the code is correct — running lint checks (code quality) and tests. If anything fails, the developer is notified before the bad code gets merged.

**File:** [`.github/workflows/ci.yml`](file:///c:/Users/sushr/Downloads/autonomous-software-engineer-main/autonomous-software-engineer-main/.github/workflows/ci.yml)

### What happens on every push and pull request to `main`:

```
1. Check out the code from GitHub
2. Set up Python 3.11
3. Install all dependencies (including dev/test dependencies)
4. Run ruff (lint check — catches code quality issues)
5. Run pytest (run all tests)
```

### What's NOT in CI (and why):
- **Docker tests** — Would require running Docker inside the CI container (Docker-in-Docker), which adds complexity
- **Integration tests with real AI models** — Would require API keys as secrets and would cost money / be flaky
- **Type checking (MyPy)** — Configured in the project but not yet added to the CI pipeline

### Linting Rules:

The project uses Ruff with these rule sets:

| Rule Set | What It Checks |
|----------|---------------|
| E | Basic code style errors (PEP 8) |
| F | Common programming mistakes (unused imports, undefined names) |
| I | Import ordering (are imports sorted consistently?) |
| N | Naming conventions (do variable/function names follow Python standards?) |
| UP | Python version upgrades (are you using modern Python syntax?) |
| B | Bug-prone patterns (common sources of bugs) |
| SIM | Simplification opportunities (can this code be written more simply?) |

---

## 23. Deployment & Containerisation

**In plain English:** This section explains how to package the entire application into a Docker container and run it. Containerisation means bundling the app and all its dependencies into a single, self-contained package that runs the same way on any machine.

### Dockerfile

**File:** [`Dockerfile`](file:///c:/Users/sushr/Downloads/autonomous-software-engineer-main/autonomous-software-engineer-main/Dockerfile)

```dockerfile
FROM python:3.11-slim              # Start with a minimal Python environment
WORKDIR /app                       # All commands run from /app
RUN apt-get update && apt-get install -y --no-install-recommends build-essential git
#   ↑ Install build tools (needed by Tree-Sitter's C extensions) and git (needed by GitPython)
COPY pyproject.toml .              # Copy just the dependency file first
RUN pip install --no-cache-dir -e ".[dev]"  # Install all dependencies
COPY . .                           # Copy the rest of the source code
EXPOSE 8000                        # Tell Docker the app listens on port 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
#   ↑ Start the web server
```

**Why copy `pyproject.toml` before the source code?** Docker builds in layers. If nothing in `pyproject.toml` changed, Docker reuses the cached dependency installation layer — saving minutes of build time. The source code changes more frequently, so it's copied last.

### Docker Compose

**File:** [`docker-compose.yml`](file:///c:/Users/sushr/Downloads/autonomous-software-engineer-main/autonomous-software-engineer-main/docker-compose.yml)

```yaml
services:
  app:
    build: .                                           # Build from the Dockerfile
    ports: ["8000:8000"]                               # Expose port 8000
    env_file: [.env]                                   # Load environment variables
    volumes:
      - .:/app                                         # Live code reloading (changes on your
                                                       # machine are reflected immediately)
      - /var/run/docker.sock:/var/run/docker.sock      # Allow the app to spawn Docker containers
                                                       # (needed for running tests in sandboxes)
  test-runner:
    image: python:3.11-slim
    profiles: [testing]    # Only started when explicitly requested, not by default
```

**What's the Docker socket mount?** The line `/var/run/docker.sock:/var/run/docker.sock` lets the ASE app (which is itself running inside Docker) create *additional* Docker containers for running tests. This is like giving someone inside a building the ability to build new rooms — it's called "Docker-in-Docker" and is a standard pattern for CI tools and test runners.

---

## 24. Error Handling & Resilience Patterns

**In plain English:** Things go wrong — APIs fail, AI models hallucinate, files go missing. This section explains how the system handles errors at every level, and the design philosophy behind its resilience. The guiding principle is: **keep going whenever safely possible, and fail gracefully when you can't.**

### How Each Layer Handles Errors

| Layer | What Can Go Wrong | What Happens |
|-------|-------------------|-------------|
| **API Routes** | Unexpected exception | Returns a 500 error with an error message |
| **Background Task** | Anything fails | Task is marked as "failed", error message is saved for the client to see |
| **Pipeline Steps** | AI returns garbage, file not found, etc. | Error is stored in the shared state, pipeline continues if possible |
| **AI Calls** | Rate limit or temporary server error | Automatically retried up to 5 times with smart waiting |
| **AI Calls** | AI returns invalid JSON | Wrapped in a descriptive error, reported to the pipeline step |
| **Patch Application** | AI hallucinated code that doesn't exist in the file | Patch is rejected immediately — prevents corrupting files |
| **Docker Tests** | Docker isn't installed/running | Returns "test failed" result — pipeline will retry or give up after max retries |
| **GitHub API** | PR creation fails (auth error, etc.) | PR draft is kept locally without a URL — pipeline still completes |
| **File Reading** | Permission denied, missing file | Warning logged, file skipped, everything else continues |
| **Index Loading** | Index file doesn't exist yet | Returns empty results — retrieval is skipped, not an error |

### Key Design Principles

1. **Graceful degradation:** The system works with as little configuration as possible. No GitHub token? PRs are drafted but not pushed. No Docker? Tests return "not available." No Gemini API key? Falls back to HuggingFace or Ollama. You can start with zero configuration and add features as you go.

2. **Retry with fresh perspective:** When tests fail, the pipeline doesn't just try the same fix again — it goes back to the *analysis* step to reconsider the root cause. This gives the AI a chance to try a completely different approach.

3. **Hallucination guards:** The `PatchApplicator` checks that the code the AI claims is in the file *actually exists* in the file before making any changes. If the AI made something up, the patch fails fast instead of silently corrupting the codebase.

4. **Two-stage validation:** Code is checked for syntax errors *before* being written to disk (catch problems early), and then formatted *after* being written to disk (make it look nice). If formatting fails, the code is still valid — it just might not match style preferences.

---

## 25. Security Considerations

**In plain English:** This section outlines the security aspects of the system — what's currently in place, what risks exist, and what you'd want to change before using this in production.

| Concern | Current State | What You'd Want in Production |
|---------|--------------|-------------------------------|
| **Who can access the API?** | Anyone — no authentication | Add API key authentication or OAuth |
| **Cross-Origin Requests (CORS)** | Allowed from everywhere (`*`) | Restrict to only your frontend's domain |
| **GitHub Token** | Stored in a `.env` file on disk | Use GitHub App authentication with minimal permissions |
| **Docker Containers** | Run as root user | Use a non-root user and read-only file mounts where possible |
| **Code Execution** | Tests run inside Docker (sandboxed) | Add resource limits (memory, CPU, network isolation) to prevent abuse |
| **Input Validation** | Pydantic checks data structure | Add rate limiting and input size caps to prevent abuse |
| **Task Storage** | In-memory dictionary (lost on restart) | Use a real database (PostgreSQL, Redis) |
| **Pickle Files** | FAISS symbols stored as Python pickle files | Ensure only trusted data is loaded (pickle can execute arbitrary code) |

---

## 26. Known Limitations & Future Improvements

**In plain English:** No system is perfect. This section honestly lists what doesn't work well yet and what we'd like to improve.

### Current Limitations

1. **Data is lost on restart:** All task information is stored in memory. If the server restarts, all progress and history is gone.
2. **Single server only:** The task tracker doesn't work across multiple server instances. You can't scale by running multiple copies of the server.
3. **No branch pushing:** The fix is committed to a local Git branch, but the branch isn't pushed to GitHub. The PR creation assumes the branch is already on GitHub (which only works in specific setups).
4. **Python-only formatting:** Code formatting tools (`ruff`, `black`) only run on Python files. JavaScript and TypeScript patches don't get auto-formatted.
5. **Full re-index every time:** Every indexing run scans the entire repository from scratch. There's no "only scan files that changed" optimisation.
6. **Doesn't scale to huge repos:** The search index uses brute-force search, which is fine for small-to-medium repos but would slow down for repositories with millions of functions.
7. **No streaming AI responses:** The dashboard waits for each entire pipeline step to finish before showing updates. You can't see the AI "thinking" in real-time.
8. **Python tests only:** Only `pytest` (Python) is supported for running tests. JavaScript test frameworks (Jest, Mocha) aren't supported yet.

### Potential Improvements

- **Persistent storage:** Use Redis or PostgreSQL to keep task data across restarts
- **Webhook integration:** Auto-trigger the pipeline when a new GitHub issue is created (instead of requiring manual submission)
- **Incremental indexing:** Only re-parse files that have changed since the last indexing
- **Multi-language test runners:** Detect and run the appropriate test framework (pytest for Python, Jest for JS, etc.)
- **Code review feedback loop:** If the PR gets review comments, automatically re-analyse and update the fix
- **Documentation search:** Index README files, docs, and code comments for even richer context
- **Real-time streaming:** Use WebSockets or Server-Sent Events for live progress updates (instead of polling)

---

## 27. Complete Directory Structure

**In plain English:** This is a map of every file in the project and what it does. Use it as a reference when you want to find where something lives.

```
autonomous-software-engineer/
├── .env.example                          # Template — copy to .env and fill in your API keys
├── .github/
│   └── workflows/
│       └── ci.yml                        # Automated lint + test on every push/PR
├── .gitignore
├── .python-version                       # Specifies Python 3.11
├── ARCHITECTURE.md                       # ← You are here!
├── CLAUDE.md                             # AI assistant instructions
├── DIAGRAM.md                            # Visual diagrams
├── Dockerfile                            # Container build instructions
├── README.md                             # User-facing setup and usage guide
├── docker-compose.yml                    # Run with Docker Compose
├── pyproject.toml                        # Dependencies, build config, tool settings
│
├── app/                                  # === THE MAIN APPLICATION CODE ===
│   ├── __init__.py
│   ├── main.py                           # Server startup — registers all routes, serves dashboard
│   ├── config.py                         # Settings — reads .env file, configures logging
│   ├── llm.py                            # AI model factory — tries Gemini → HuggingFace → Ollama
│   │
│   ├── agents/                           # === THE PIPELINE STEPS ===
│   │   ├── code_fix_agent.py             # Asks AI to generate code patches
│   │   ├── indexing_agent.py             # Scans code → builds search index
│   │   ├── issue_analysis_agent.py       # Asks AI to analyse the bug
│   │   ├── patch_applicator.py           # Writes patches to files, formats, commits
│   │   ├── pr_generation_agent.py        # Asks AI to write PR title + description
│   │   └── retrieval_agent.py            # Finds relevant code (exact + semantic search)
│   │
│   ├── api/                              # === HTTP ENDPOINTS ===
│   │   ├── dependencies.py              # Shared singletons (DI)
│   │   ├── __init__.py
│   │   └── routes/
│   │       ├── github_issues.py          # POST /process-github-issue (sync mode)
│   │       ├── indexing.py               # POST /index-repository
│   │       ├── indices.py                # GET /indices (list indexed repos)
│   │       ├── issues.py                 # POST /process-issue (async) + GET status
│   │       ├── pr.py                     # POST /generate-pr (standalone)
│   │       └── testing.py                # POST /run-tests (standalone)
│   │
│   ├── docker_runner/                    # === TEST EXECUTION ===
│   │   └── runner.py                     # Runs pytest inside Docker containers
│   │
│   ├── github/                           # === GITHUB INTEGRATION ===
│   │   ├── client.py                     # Fetches issue data from GitHub API
│   │   ├── cloner.py                     # Downloads/updates repository code
│   │   └── pr_builder.py                 # Creates pull requests on GitHub
│   │
│   ├── hooks/                            # === VALIDATION CHECKPOINTS ===
│   │   ├── __init__.py                   # Re-exports all hooks
│   │   ├── post_code_generation.py       # Syntax check + auto-formatting
│   │   ├── post_test.py                  # Blocks PR if tests failed
│   │   ├── pre_code_generation.py        # Validates inputs before AI generates code
│   │   ├── pre_pr.py                     # Validates everything before creating PR
│   │   └── pre_test.py                   # Checks Docker is available
│   │
│   ├── models/                           # === DATA SHAPES (SCHEMAS) ===
│   │   ├── __init__.py                   # Re-exports all models
│   │   ├── issue.py                      # Bug report + analysis models
│   │   ├── patch.py                      # Code change models
│   │   ├── pr.py                         # Pull request model
│   │   ├── retrieval.py                  # Search result models
│   │   ├── state.py                      # Pipeline shared state
│   │   ├── symbol.py                     # Code symbol (function/class) models
│   │   └── test_result.py                # Test execution result model
│   │
│   ├── parsers/                          # === CODE ANALYSIS ===
│   │   └── tree_sitter_parser.py         # Extracts functions/classes from code files
│   │
│   ├── retrieval/                        # === CODE SEARCH ===
│   │   ├── exact_matcher.py              # Search by function/class name
│   │   └── semantic_retriever.py         # Search by meaning (vector similarity)
│   │
│   ├── utils/                            # === UTILITIES ===
│   │   └── retry.py                      # Auto-retry for failed AI calls
│   │
│   ├── vectorstore/                      # === SEARCH ENGINE ===
│   │   └── faiss_store.py                # Vector storage + similarity search
│   │
│   └── workflow/                         # === PIPELINE ORCHESTRATION ===
│       └── graph.py                      # The 6-step flowchart with retry logic
│
├── dashboard/                            # === WEB INTERFACE ===
│   ├── index.html                        # Page structure and navigation
│   ├── style.css                         # Dark theme styling
│   └── app.js                            # All UI logic and API communication
│
└── tests/                                # === AUTOMATED TESTS ===
    ├── __init__.py
    ├── test_api.py                       # 7 tests for API endpoints
    ├── test_parsers.py                   # 8 tests for code parser
    └── test_retrieval.py                 # 6 tests for search system
```

---

## 28. Interview FAQ — Common Deep-Dive Questions

**In plain English:** If you're preparing for an interview about this project, here are the most commonly asked questions and comprehensive answers that demonstrate deep understanding.

### Q: "Walk me through what happens when a user submits an issue."

**A:** The user sends a POST request with a bug title, description, and GitHub URL. The server immediately responds with a tracking ID (202 Accepted) and kicks off the work in the background. First, it clones (or updates) the repository. Then it scans all code files and builds a searchable index. Then the 6-step AI pipeline runs: analyse the bug → find relevant code → generate a fix → apply the fix to files → run tests → create a PR. If tests fail, it loops back to re-analyse (up to 3 times). The client can poll for progress at any time using the tracking ID. See [Section 2](#2-end-to-end-request-lifecycle) for the full visual walkthrough.

### Q: "Why LangGraph and not just calling functions sequentially?"

**A:** Four reasons: (1) **Conditional branching** — the retry loop after test failure needs to decide whether to go back to analysis or give up. With plain sequential code, this would require messy nested loops and if-statements. (2) **Shared typed state** — all steps automatically have access to a common data store (`AgentState`) without passing dozens of parameters around. (3) **Checkpointing** — intermediate state is saved automatically, enabling debugging and future replay features. (4) **Streaming** — the `astream()` API fires events when each step completes, which powers the dashboard's live progress tracker.

### Q: "How does your retrieval work? Why hybrid?"

**A:** We use two search strategies and combine them. *Exact matching* catches functions mentioned by name in the bug report (very precise, but misses related code that wasn't mentioned). *Semantic search* finds code that's conceptually similar to the bug description (broader coverage, but fuzzier). Merging them — with exact matches first — gives the best of both: directly-referenced code is always included, and conceptually-related code fills the remaining slots. See [Section 12](#12-hybrid-retrieval-engine--exact--semantic-search).

### Q: "How do you prevent the LLM from generating broken code?"

**A:** Three layers of protection: (1) **Prompt engineering** — we explicitly tell the AI to copy the original code verbatim and generate syntactically valid replacements. (2) **Pre-write syntax check** — Python's `ast.parse()` validates syntax *before* anything is written to disk. (3) **Post-write formatting** — `ruff` and `black` clean up the code style. Plus the **hallucination guard** — if the AI claims to replace code that doesn't actually exist in the file, the patch is rejected with a clear error instead of silently corrupting the codebase.

### Q: "What happens when tests fail?"

**A:** The routing function after the test step checks the retry counter against the maximum (default: 3). If retries remain, the pipeline loops all the way back to `analyze_issue` for a *fresh* root cause analysis — not just re-generating the same fix. This gives the AI a chance to try a completely different approach. After 3 failures, the pipeline stops — no PR is created, and the error details are saved in the task status.

### Q: "Why do you embed source code and not just function signatures?"

**A:** Because the AI needs to *read and understand* the full function body to fix bugs in it. If we only embedded signatures (just the function name and parameters), the search would find the right functions, but the AI wouldn't have enough code to understand the implementation or write a correct fix. The `all-MiniLM-L6-v2` model handles up to 256 word pieces per input, and most functions fit comfortably within that limit.

### Q: "How do you handle rate limits?"

**A:** The `@llm_retry` decorator uses the Tenacity library. When an AI call fails, it checks the error message: rate limit errors (429, "quota exceeded", etc.) get a random 45–90 second wait (because Gemini's free tier has per-minute quotas), while other temporary errors (server 500s, timeouts) get exponential backoff (2s, 4s, 8s, 15s) with random jitter. Maximum 5 attempts total. See [Section 9](#9-llm-retry--rate-limit-handling).

### Q: "How would you scale this?"

**A:** Key bottlenecks and solutions: (1) **In-memory task storage** — replace with Redis or PostgreSQL so multiple server instances can share state. (2) **Single AI model instance** — add a request queue with a worker pool. (3) **Brute-force FAISS search** — switch to an approximate index (IVF or HNSW) for repos with 100K+ symbols. (4) **Synchronous indexing** — make indexing async or use a job queue. (5) **Single Docker test runner** — use Kubernetes with resource quotas for better isolation and scaling.

### Q: "What's the most critical failure mode?"

**A:** The AI hallucinating the `original_code` in a REPLACE patch. If the hallucinated code happens to match a *different* part of the file (not the part we intended to fix), `str.replace()` would modify the wrong location. Our current guard catches "not found" errors, but doesn't verify that the match is at the intended line range. A stronger guard would validate that the match position corresponds to the `start_line`/`end_line` the AI specified.

### Q: "Why Tree-Sitter and not Python's `ast` module?"

**A:** Three reasons: (1) **Multi-language support** — Tree-Sitter handles Python, JavaScript, and TypeScript with a single consistent API. Python's `ast` module only works with Python code. (2) **Error resilience** — Tree-Sitter can parse broken or incomplete files and still produce useful partial results. Python's `ast.parse()` would crash on any syntax error. (3) **Code simplicity** — one parsing pipeline for all languages means less code to maintain and test.

### Q: "Why FAISS IndexFlatIP and not an approximate index?"

**A:** At our expected scale (hundreds to a few thousand code symbols per repo), brute-force exact search takes less than 1 millisecond. Approximate indices like IVF or HNSW would add tuning complexity (how many clusters? how many probes?), a training step, and recall trade-offs — all for zero meaningful speed improvement at this scale. If we ever needed to index a massive monorepo with millions of symbols, we'd switch to `IndexIVFFlat` with tuned `nprobe` parameters.

### Q: "How does the system handle a repo it's never seen before?"

**A:** Every pipeline run starts with a clone-or-update step followed by a full indexing step. So even if the system has never seen a repository before, it downloads the code and builds a fresh search index before the AI workflow begins. The index is saved to disk, so it persists across server restarts. The retrieval step always loads the index from disk (not from memory), ensuring it picks up the latest version.
