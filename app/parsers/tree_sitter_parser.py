"""
Tree-sitter based source code parser.

Walks a repository, parses Python/JS/TS files, and extracts functions
and classes as Symbol objects. Each Symbol contains the full source code
of the function/class — this source code is later embedded into FAISS.

Uses manual AST walking instead of the Query API for compatibility
across tree-sitter 0.23.x versions.
"""
import logging
from pathlib import Path

import tree_sitter_javascript as tsjavascript
import tree_sitter_python as tspython
import tree_sitter_typescript as tstypescript
from tree_sitter import Language, Node, Parser

from app.models.symbol import Symbol, SymbolType

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
}

SKIP_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    "env", "dist", "build", ".mypy_cache", ".pytest_cache",
}

# Node types that represent a named callable/class per language
_DEFINITION_TYPES: dict[str, set[str]] = {
    "python": {"function_definition", "class_definition"},
    "javascript": {"function_declaration", "class_declaration", "method_definition"},
    "typescript": {"function_declaration", "class_declaration", "method_definition"},
}


def _build_languages() -> dict[str, Language]:
    return {
        "python": Language(tspython.language()),
        "javascript": Language(tsjavascript.language()),
        "typescript": Language(tstypescript.language_typescript()),
    }


def _walk(node: Node, target_types: set[str]):
    """Yield all descendant nodes whose type is in target_types."""
    if node.type in target_types:
        yield node
    for child in node.children:
        yield from _walk(child, target_types)


def _get_name(node: Node) -> str:
    """Return the identifier name child of a definition node."""
    for child in node.children:
        if child.type in ("identifier", "property_identifier"):
            return child.text.decode("utf-8", errors="replace")
    return ""


class TreeSitterParser:
    def __init__(self) -> None:
        self._languages = _build_languages()
        self._parsers: dict[str, Parser] = {}
        for lang_name, language in self._languages.items():
            self._parsers[lang_name] = Parser(language)

    def parse_file(self, file_path: Path) -> list[Symbol]:
        ext = file_path.suffix.lower()
        lang = SUPPORTED_EXTENSIONS.get(ext)
        if lang is None:
            return []

        try:
            source = file_path.read_bytes()
        except (OSError, PermissionError) as e:
            logger.warning("Cannot read %s: %s", file_path, e)
            return []

        tree = self._parsers[lang].parse(source)
        source_str = source.decode("utf-8", errors="replace")
        lines = source_str.splitlines()

        target_types = _DEFINITION_TYPES[lang]
        symbols: list[Symbol] = []
        seen: set[tuple[int, int]] = set()

        for node in _walk(tree.root_node, target_types):
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1

            if (start_line, end_line) in seen:
                continue
            seen.add((start_line, end_line))

            name = _get_name(node)
            if not name:
                name = f"anonymous_{start_line}"

            source_code = "\n".join(lines[start_line - 1: end_line])
            symbol_type = self._infer_type(node)
            docstring = self._extract_docstring(source_code, lang)

            symbols.append(Symbol(
                name=name,
                symbol_type=symbol_type,
                file_path=str(file_path),
                start_line=start_line,
                end_line=end_line,
                source_code=source_code,
                language=lang,
                docstring=docstring,
            ))

        return symbols

    def _infer_type(self, node: Node) -> SymbolType:
        if "class" in node.type:
            return SymbolType.CLASS
        if "method" in node.type:
            return SymbolType.METHOD
        # async functions have "async" as first named child
        if node.children and node.children[0].type == "async":
            return SymbolType.ASYNC_FUNCTION
        return SymbolType.FUNCTION

    def _extract_docstring(self, source_code: str, lang: str) -> str | None:
        if lang != "python":
            return None
        lines = source_code.strip().splitlines()
        in_doc = False
        doc_lines: list[str] = []
        for line in lines[1:]:
            stripped = line.strip()
            if not in_doc and (stripped.startswith('"""') or stripped.startswith("'''")):
                in_doc = True
                doc_lines.append(stripped)
                if stripped.count('"""') >= 2 or stripped.count("'''") >= 2:
                    break
            elif in_doc:
                doc_lines.append(line)
                if '"""' in stripped or "'''" in stripped:
                    break
        return "\n".join(doc_lines) if doc_lines else None

    def scan_repository(self, repo_path: Path) -> list[Symbol]:
        all_symbols: list[Symbol] = []
        scanned_files = 0

        for file_path in repo_path.rglob("*"):
            if not file_path.is_file():
                continue
            if any(skip in file_path.parts for skip in SKIP_DIRS):
                continue
            if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue

            all_symbols.extend(self.parse_file(file_path))
            scanned_files += 1

        logger.info("Scanned %d files, %d symbols from %s", scanned_files, len(all_symbols), repo_path)
        return all_symbols
