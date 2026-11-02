"""Tests for exact matcher and retrieval merging."""
import pytest
from datetime import datetime

from app.models.symbol import Symbol, SymbolIndex, SymbolType
from app.models.issue import IssueInput
from app.retrieval.exact_matcher import ExactMatcher


def make_symbol(name: str, source: str = None) -> Symbol:
    return Symbol(
        name=name,
        symbol_type=SymbolType.FUNCTION,
        file_path=f"app/{name}.py",
        start_line=1,
        end_line=5,
        source_code=source or f"def {name}(): pass",
        language="python",
    )


@pytest.fixture
def symbol_index():
    symbols = [
        make_symbol("register_user"),
        make_symbol("validate_email"),
        make_symbol("create_account"),
        make_symbol("send_notification"),
    ]
    return SymbolIndex(
        symbols=symbols,
        repository_path="/tmp/repo",
        indexed_at=datetime.utcnow().isoformat(),
        total_files=4,
        total_symbols=4,
    )


@pytest.fixture
def matcher(symbol_index):
    return ExactMatcher(symbol_index)


def test_exact_match_function_name(matcher):
    results = matcher.match("register_user fails when email is null")
    names = [r.symbol.name for r in results]
    assert "register_user" in names


def test_exact_match_camel_case(matcher):
    # "registerUser" should split to "register" + "user" → finds register_user
    results = matcher.match("registerUser endpoint is broken")
    names = [r.symbol.name for r in results]
    assert "register_user" in names


def test_no_match_returns_empty(matcher):
    results = matcher.match("the database connection pool is exhausted")
    assert results == []


def test_exact_match_score_is_high(matcher):
    results = matcher.match("validate_email returns wrong result")
    email_results = [r for r in results if r.symbol.name == "validate_email"]
    assert len(email_results) == 1
    assert email_results[0].score == 1.0


def test_match_type_is_exact(matcher):
    results = matcher.match("validate_email is broken")
    for r in results:
        assert r.match_type == "exact"


def test_multiple_symbols_matched(matcher):
    results = matcher.match("register_user calls validate_email")
    names = [r.symbol.name for r in results]
    assert "register_user" in names
    assert "validate_email" in names
