# Architecture Diagrams

---

## 1. End-to-End System Flow

```mermaid
flowchart TD
    Client(["🖥️ Client / API Consumer"])

    Client -->|"POST /process-issue"| API["FastAPI\n/process-issue"]
    API -->|"202 Accepted + task_id"| Client
    API -->|"Spawns background task"| BG["BackgroundTasks\nrun_workflow_in_background()"]

    Client -->|"GET /process-issue/{task_id}"| POLL["FastAPI\n/process-issue/{task_id}"]
    POLL -->|"status: pending | running | completed | failed"| Client

    BG --> CLONER["RepoCloner\nclone_or_pull()"]
    CLONER --> INDEXER["RepositoryIndexingAgent\nindex_repository()"]
    INDEXER --> GRAPH["LangGraph\nStateGraph Workflow"]
    GRAPH --> RESULT["TasksDB\nIn-memory result store"]
    RESULT --> POLL
```

---

## 2. Git Workspace Manager — Clone / Pull Logic

```mermaid
flowchart TD
    Start(["clone_or_pull(github_url)"])

    Start --> Check{"Workspace\nfolder exists?"}
    Check -->|No| Clone["git clone\ngithub_url → workspace/owner_repo"]
    Check -->|Yes| VerifyURL{"Remote origin\nURL matches?"}

    VerifyURL -->|No| Wipe["shutil.rmtree()\nDelete stale directory"] --> Clone
    VerifyURL -->|Yes| Reset["git reset --hard\n(discard uncommitted changes)"]

    Reset --> Clean["git clean -fdx\n(remove untracked files & patches)"]
    Clean --> Checkout["git checkout main\n(or master fallback)"]
    Checkout --> Pull["git pull\n(fetch latest commits)"]

    Pull --> Success{"Pull\nsucceeded?"}
    Success -->|Yes| Done(["✅ workspace/owner_repo ready"])
    Success -->|No| Wipe2["shutil.rmtree()\nFallback: delete & re-clone"] --> Clone

    Clone --> Done
```

---

## 3. Indexing Pipeline — Tree-Sitter + FAISS

```mermaid
flowchart TD
    Repo(["📂 Repository Path\nworkspace/owner_repo"])

    Repo --> Parser["TreeSitterParser\nparse_directory()"]
    Parser -->|"Recursively scans .py / .js / .ts"| AST["AST Symbol Extraction\n• classes\n• functions\n• methods"]

    AST --> Symbols["SymbolIndex\nList[Symbol]\n(name, type, file, lines, source_code)"]

    Symbols --> Embed["FAISSStore\nembed_and_add()"]
    Embed -->|"all-MiniLM-L6-v2\n384-dim vectors"| FAISS["FAISS Index\n(L2-normalized)"]

    Symbols -->|"JSON serialized"| SymFile["data/indices/{repo_name}/\nsymbol_index.json"]
    FAISS -->|"Binary serialized"| FaissFile["data/indices/{repo_name}/\nfaiss.index"]
```

---

## 4. Hybrid Retrieval Engine

```mermaid
flowchart TD
    Issue(["📋 IssueInput\ntitle + description"])

    Issue --> Exact["ExactMatcher\ntokenize_issue_text()"]
    Issue --> Semantic["SemanticRetriever\nembed query → FAISS.search()"]

    Exact -->|"Token match on\nclass/function names"| ExactResults["Exact Matches\nscore: 1.0 (class) / 0.7 (function)"]
    Semantic -->|"Top-K cosine similarity"| SemanticResults["Semantic Matches\nscore: 1 - L2 distance"]

    ExactResults --> Merge["Merge & Deduplicate\n• Exact results first\n• Fill remaining slots\n  with semantic results\n• Dedup by symbol name\n• Cap at retrieval_top_k"]
    SemanticResults --> Merge

    Merge --> RetrievalResult["RetrievalResult\nList[RetrievedSymbol]\n(merged_count, total_exact, total_semantic)"]
```

---

## 5. LangGraph State Machine — Full Agent Orchestration

```mermaid
stateDiagram-v2
    [*] --> analyze_issue

    analyze_issue --> retrieve_context
    retrieve_context --> generate_fix
    generate_fix --> apply_patch
    apply_patch --> run_tests

    run_tests --> generate_pr : tests passed
    run_tests --> analyze_issue : tests failed AND retry_count < max_retries
    run_tests --> [*] : tests failed AND retry_count >= max_retries (abort)

    generate_pr --> [*]
```

---

## 6. LangGraph Node Detail — Hooks & Agents

```mermaid
flowchart TD
    Entry(["🚀 Entry Point\nAgentState{ issue, retry_count=0 }"])

    Entry --> N1

    subgraph N1["NODE: analyze_issue"]
        A1["IssueAnalysisAgent.analyze()\n• Root cause\n• Suggested approach\n• Affected files\n• Severity\n• Keywords"]
    end

    N1 --> N2

    subgraph N2["NODE: retrieve_context"]
        A2["RepositoryIndexingAgent.load_symbol_index()\n+ FAISSStore.load()\n→ RetrievalAgent.retrieve()\n(ExactMatcher + SemanticRetriever)"]
    end

    N2 --> N3

    subgraph N3["NODE: generate_fix"]
        H1["🪝 pre_code_generation_hook\n(validate issue + retrieval inputs)"]
        A3["CodeFixAgent.generate_fix()\n• Produces PatchSet\n• List of FilePatch operations\n  (replace / insert / delete)"]
        H2["🪝 post_code_generation_hook\n• ast.parse() each snippet\n• Validates Python syntax\n  before touching disk"]
        H1 --> A3 --> H2
    end

    N3 --> N4

    subgraph N4["NODE: apply_patch"]
        A4a["PatchApplicator\n• Create branch: fix/auto-{timestamp}\n• Write file changes to disk"]
        H3["🪝 post_patch_apply_hook\n• Run: ruff --fix\n• Run: black\n  on patched files"]
        A4b["git add -A\ngit commit"]
        A4a --> H3 --> A4b
    end

    N4 --> N5

    subgraph N5["NODE: run_tests"]
        H4["🪝 pre_test_hook\n(check docker is reachable)"]
        A5["DockerTestRunner.run_tests()\n• Scan for requirements.txt\n• Scan for setup.py\n• Scan for pyproject.toml\n• pip install dependencies\n• pytest"]
        H5["🪝 post_test_hook\n(log result summary)"]
        H4 --> A5 --> H5
    end

    N5 --> Router{"route_after_tests()"}

    Router -->|"test_result.passed == True"| N6
    Router -->|"failed + retry_count < 3"| RetryInc["retry_count += 1"] --> N1
    Router -->|"failed + retry_count >= 3"| Abort(["❌ END\n(max retries reached)"])

    subgraph N6["NODE: generate_pr"]
        H6["🪝 pre_pr_hook\n(validate patch + test passed)"]
        A6["PRGenerationAgent.generate_pr()\n• Draft PR title + body via LLM\n• PyGithub: create PR\n• Returns PRDraft"]
        H6 --> A6
    end

    N6 --> Success(["✅ END\nAgentState{ pr_draft, pr_url }"])
```

---

## 7. Docker Sandbox Test Runner

```mermaid
flowchart TD
    Start(["run_tests(repository_path)"])

    Start --> Scan["Scan repo root for\ndependency manifests"]

    Scan --> Req{"requirements.txt\nexists?"}
    Scan --> Setup{"setup.py\nexists?"}
    Scan --> Pyproject{"pyproject.toml with\n[build-system] exists?"}

    Req -->|Yes| InstallReq["pip install -r requirements.txt"]
    Setup -->|Yes| InstallSetup["pip install -e ."]
    Pyproject -->|Yes| InstallPyproject["pip install -e ."]

    InstallReq --> Pytest
    InstallSetup --> Pytest
    InstallPyproject --> Pytest
    Scan -->|"No manifests found"| Pytest

    Pytest["pytest\n(inside python:3.11-slim container\nwith workspace mounted)"]

    Pytest --> Parse["Parse stdout/stderr\n• exit code\n• passed / failed counts"]
    Parse --> TestResult["TestResult\n{ passed, total_tests,\n  passed_tests, failed_tests,\n  output }"]
```

---

## 8. Shared Agent State — Data Flow

```mermaid
flowchart LR
    subgraph AgentState["AgentState  (TypedDict — shared across all nodes)"]
        F1["issue\nIssueInput"]
        F2["analysis\nIssueAnalysis"]
        F3["retrieval\nRetrievalResult"]
        F4["patch_set\nPatchSet"]
        F5["test_result\nTestResult"]
        F6["pr_draft\nPRDraft"]
        F7["error\nstr | None"]
        F8["retry_count\nint"]
    end

    analyze_issue -->|"writes"| F2
    retrieve_context -->|"writes"| F3
    generate_fix -->|"reads F2,F3\nwrites"| F4
    apply_patch -->|"reads+writes"| F4
    run_tests -->|"writes"| F5
    run_tests -->|"increments"| F8
    generate_pr -->|"reads F2,F4,F5\nwrites"| F6
```
