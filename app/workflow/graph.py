"""
LangGraph workflow graph.

Defines the full autonomous software engineering pipeline as a StateGraph:

  analyze_issue → retrieve_context → generate_fix → apply_patch
       ↑                                                   ↓
       └──────────── (retry, max 3) ──────── run_tests ───┘
                                                  ↓ (pass)
                                            generate_pr → END

All agents communicate through AgentState — a shared TypedDict that each
node reads from and writes to.
"""
import logging

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from app.agents.code_fix_agent import CodeFixAgent
from app.agents.indexing_agent import RepositoryIndexingAgent
from app.agents.issue_analysis_agent import IssueAnalysisAgent
from app.agents.patch_applicator import PatchApplicator
from app.agents.pr_generation_agent import PRGenerationAgent
from app.agents.retrieval_agent import RetrievalAgent
from app.config import settings
from app.docker_runner.runner import DockerTestRunner
from app.hooks.post_code_generation import post_code_generation_hook
from app.hooks.post_test import post_test_hook
from app.hooks.pre_code_generation import HookValidationError as PreCodeError
from app.hooks.pre_code_generation import pre_code_generation_hook
from app.hooks.pre_pr import pre_pr_hook
from app.hooks.pre_test import pre_test_hook
from app.llm import get_llm
from app.models.state import AgentState
from app.vectorstore.faiss_store import FAISSStore

logger = logging.getLogger(__name__)


def build_graph() -> StateGraph:
    """Construct and compile the LangGraph StateGraph."""

    # ── Shared services ──────────────────────────────────────────────────────
    llm = get_llm()
    analysis_agent = IssueAnalysisAgent(llm)
    fix_agent = CodeFixAgent(llm)
    applicator = PatchApplicator()
    test_runner = DockerTestRunner()
    pr_agent = PRGenerationAgent(llm)

    # ── Node functions ────────────────────────────────────────────────────────

    def analyze_issue(state: AgentState) -> AgentState:
        logger.info("[NODE] analyze_issue")
        try:
            from app.models.retrieval import RetrievalResult
            context = state.get("retrieval") or RetrievalResult(
                query="", results=[], total_exact=0, total_semantic=0, merged_count=0
            )
            analysis = analysis_agent.analyze(state["issue"], context)
            return {**state, "analysis": analysis, "error": None}
        except Exception as e:
            logger.error("analyze_issue failed: %s", e)
            return {**state, "error": str(e)}

    def retrieve_context(state: AgentState) -> AgentState:
        logger.info("[NODE] retrieve_context")
        try:
            from app.models.retrieval import RetrievalResult
            # Always reload from disk — picks up repos indexed after server start
            current_symbol_index = None
            try:
                current_symbol_index = RepositoryIndexingAgent.load_symbol_index()
            except FileNotFoundError:
                pass

            if current_symbol_index is None:
                logger.warning("No symbol index — skipping retrieval")
                return {**state, "retrieval": RetrievalResult(
                    query="", results=[], total_exact=0, total_semantic=0, merged_count=0
                )}

            current_faiss = FAISSStore(model_name=settings.embedding_model)
            try:
                current_faiss.load(settings.faiss_index_path)
            except FileNotFoundError:
                pass

            agent = RetrievalAgent(current_symbol_index, current_faiss)
            result = agent.retrieve(state["issue"], top_k=settings.retrieval_top_k)
            return {**state, "retrieval": result}
        except Exception as e:
            logger.error("retrieve_context failed: %s", e)
            return {**state, "error": str(e)}

    def generate_fix(state: AgentState) -> AgentState:
        logger.info("[NODE] generate_fix")
        try:
            pre_code_generation_hook(state["issue"], state["retrieval"])
            patch_set = fix_agent.generate_fix(
                state["issue"], state["analysis"], state["retrieval"]
            )
            post_code_generation_hook(patch_set, state["issue"].repository_path)
            return {**state, "patch_set": patch_set}
        except PreCodeError as e:
            logger.error("Pre-code-gen hook failed: %s", e)
            return {**state, "error": str(e)}
        except Exception as e:
            logger.error("generate_fix failed: %s", e)
            return {**state, "error": str(e)}

    def apply_patch(state: AgentState) -> AgentState:
        logger.info("[NODE] apply_patch")
        try:
            applied = applicator.apply(state["patch_set"], state["issue"].repository_path)
            return {**state, "patch_set": applied}
        except Exception as e:
            logger.error("apply_patch failed: %s", e)
            return {**state, "error": str(e)}

    def run_tests(state: AgentState) -> AgentState:
        logger.info("[NODE] run_tests")
        try:
            pre_test_hook(state["issue"].repository_path)
            result = test_runner.run_tests(state["issue"].repository_path)
            post_test_hook(result)
            return {**state, "test_result": result}
        except Exception as e:
            logger.error("run_tests failed: %s", e)
            retry_count = state.get("retry_count", 0) + 1
            return {**state, "error": str(e), "retry_count": retry_count}

    def generate_pr(state: AgentState) -> AgentState:
        logger.info("[NODE] generate_pr")
        try:
            pre_pr_hook(state["patch_set"], state["test_result"], state["issue"].repository_path)
            pr_draft = pr_agent.generate_pr(
                state["issue"],
                state["analysis"],
                state["patch_set"],
                state["test_result"],
            )
            return {**state, "pr_draft": pr_draft}
        except Exception as e:
            logger.error("generate_pr failed: %s", e)
            return {**state, "error": str(e)}

    # ── Routing ───────────────────────────────────────────────────────────────

    def route_after_tests(state: AgentState) -> str:
        """After tests: go to PR if passed, retry if failed, end if max retries hit."""
        if state.get("test_result") and state["test_result"].passed:
            return "generate_pr"
        if state.get("retry_count", 0) >= settings.max_retries:
            logger.warning("Max retries (%d) reached — aborting", settings.max_retries)
            return END
        logger.info("Tests failed — retrying (attempt %d)", state.get("retry_count", 0))
        return "analyze_issue"

    # ── Graph assembly ────────────────────────────────────────────────────────

    graph = StateGraph(AgentState)

    graph.add_node("analyze_issue", analyze_issue)
    graph.add_node("retrieve_context", retrieve_context)
    graph.add_node("generate_fix", generate_fix)
    graph.add_node("apply_patch", apply_patch)
    graph.add_node("run_tests", run_tests)
    graph.add_node("generate_pr", generate_pr)

    graph.set_entry_point("analyze_issue")

    graph.add_edge("analyze_issue", "retrieve_context")
    graph.add_edge("retrieve_context", "generate_fix")
    graph.add_edge("generate_fix", "apply_patch")
    graph.add_edge("apply_patch", "run_tests")
    graph.add_conditional_edges("run_tests", route_after_tests)
    graph.add_edge("generate_pr", END)

    return graph.compile(checkpointer=MemorySaver())


# Module-level compiled graph — imported by FastAPI routes
compiled_graph = build_graph()
