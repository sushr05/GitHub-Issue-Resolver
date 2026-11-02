"""Tests for the Tree-sitter parser."""
import pytest
from pathlib import Path
import tempfile

from app.parsers.tree_sitter_parser import TreeSitterParser
from app.models.symbol import SymbolType


SAMPLE_PYTHON = '''
def add(a, b):
    """Add two numbers."""
    return a + b

async def fetch_user(user_id: int):
    return {"id": user_id}

class UserService:
    def get_user(self, user_id: int):
        return None

    async def create_user(self, email: str):
        pass
'''


@pytest.fixture
def parser():
    return TreeSitterParser()


@pytest.fixture
def sample_py_file(tmp_path):
    f = tmp_path / "sample.py"
    f.write_text(SAMPLE_PYTHON)
    return f


def test_parse_python_functions(parser, sample_py_file):
    symbols = parser.parse_file(sample_py_file)
    names = [s.name for s in symbols]
    assert "add" in names
    assert "fetch_user" in names


def test_parse_python_class(parser, sample_py_file):
    symbols = parser.parse_file(sample_py_file)
    names = [s.name for s in symbols]
    assert "UserService" in names


def test_async_function_type(parser, sample_py_file):
    symbols = parser.parse_file(sample_py_file)
    async_syms = [s for s in symbols if s.name == "fetch_user"]
    assert len(async_syms) == 1
    assert async_syms[0].symbol_type == SymbolType.ASYNC_FUNCTION


def test_source_code_captured(parser, sample_py_file):
    symbols = parser.parse_file(sample_py_file)
    add_sym = next(s for s in symbols if s.name == "add")
    assert "return a + b" in add_sym.source_code


def test_docstring_extracted(parser, sample_py_file):
    symbols = parser.parse_file(sample_py_file)
    add_sym = next(s for s in symbols if s.name == "add")
    assert add_sym.docstring is not None
    assert "Add two numbers" in add_sym.docstring


def test_unsupported_extension_returns_empty(parser, tmp_path):
    f = tmp_path / "data.csv"
    f.write_text("a,b,c")
    assert parser.parse_file(f) == []


def test_scan_repository(parser, tmp_path):
    (tmp_path / "module.py").write_text(SAMPLE_PYTHON)
    subdir = tmp_path / "sub"
    subdir.mkdir()
    (subdir / "utils.py").write_text("def helper(): pass")

    symbols = parser.scan_repository(tmp_path)
    names = [s.name for s in symbols]
    assert "add" in names
    assert "helper" in names


def test_line_numbers(parser, sample_py_file):
    symbols = parser.parse_file(sample_py_file)
    add_sym = next(s for s in symbols if s.name == "add")
    assert add_sym.start_line >= 1
    assert add_sym.end_line >= add_sym.start_line
