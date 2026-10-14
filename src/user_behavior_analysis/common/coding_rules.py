"""Check PDF-specific source rules not fully enforced by the standard tools."""

import ast
import io
import tokenize
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CodingIssue:
    """Describe one actionable coding-standard finding.

    Attributes:
        path: Reviewed Python file.
        line: One-based line number.
        message: Violated coding rule.
    """

    path: str
    line: int
    message: str


def _definition_issues(node: ast.AST, path: Path) -> list[CodingIssue]:
    issues: list[CodingIssue] = []
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return issues
    if node.name.startswith("_"):
        return issues
    if not ast.get_docstring(node):
        issues.append(
            CodingIssue(str(path), node.lineno, "Public definition needs a docstring")
        )
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        parameters = [
            argument
            for argument in node.args.posonlyargs
            + node.args.args
            + node.args.kwonlyargs
            if argument.arg not in {"self", "cls"}
        ]
        parameters += [
            argument for argument in (node.args.vararg, node.args.kwarg) if argument
        ]
        if len(parameters) > 5:
            issues.append(
                CodingIssue(
                    str(path), node.lineno, "Public function exceeds five parameters"
                )
            )
        if node.returns is None or any(
            argument.annotation is None for argument in parameters
        ):
            issues.append(
                CodingIssue(
                    str(path), node.lineno, "Public API needs complete type annotations"
                )
            )
        docstring = ast.get_docstring(node) or ""
        if parameters and "Args:" not in docstring:
            issues.append(
                CodingIssue(str(path), node.lineno, "Google docstring needs Args")
            )
        if node.returns and not (
            isinstance(node.returns, ast.Constant) and node.returns.value is None
        ):
            if "Returns:" not in docstring and "Yields:" not in docstring:
                issues.append(
                    CodingIssue(
                        str(path),
                        node.lineno,
                        "Google docstring needs Returns or Yields",
                    )
                )
    return issues


def _node_issues(tree: ast.Module, path: Path) -> list[CodingIssue]:
    issues: list[CodingIssue] = []
    for node in ast.walk(tree):
        issues.extend(_definition_issues(node, path))
        if isinstance(node, ast.Import) and len(node.names) > 1:
            issues.append(
                CodingIssue(str(path), node.lineno, "Use one import per line")
            )
        if isinstance(node, ast.ImportFrom) and (
            node.level or any(alias.name == "*" for alias in node.names)
        ):
            issues.append(
                CodingIssue(
                    str(path), node.lineno, "Use absolute imports without wildcards"
                )
            )
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            issues.append(
                CodingIssue(str(path), node.lineno, "Bare except is forbidden")
            )
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            defaults = node.args.defaults + [
                item for item in node.args.kw_defaults if item
            ]
            if any(
                isinstance(item, (ast.List, ast.Dict, ast.Set)) for item in defaults
            ):
                issues.append(
                    CodingIssue(
                        str(path), node.lineno, "Mutable defaults are forbidden"
                    )
                )
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in {"eval", "exec"}:
                issues.append(
                    CodingIssue(
                        str(path), node.lineno, "Dynamic execution is forbidden"
                    )
                )
            if "tests" in path.parts and node.func.id == "print":
                issues.append(
                    CodingIssue(
                        str(path), node.lineno, "Tests must assert instead of printing"
                    )
                )
    return issues


def audit_source(path: Path) -> list[CodingIssue]:
    """Inspect a Python source file against the document-specific hard rules.

    Args:
        path: Python source file to inspect.

    Returns:
        Explicit violations with source locations; an empty list means success.

    Raises:
        SyntaxError: The file is not valid Python.
    """
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    issues = _node_issues(tree, path)
    if not ast.get_docstring(tree):
        issues.append(CodingIssue(str(path), 1, "Module needs a docstring"))
    if not source.endswith("\n") or source.endswith("\n\n"):
        issues.append(CodingIssue(str(path), 1, "Use exactly one final newline"))
    for number, line in enumerate(source.splitlines(), start=1):
        if len(line) > 88 or "\t" in line:
            issues.append(
                CodingIssue(
                    str(path), number, "Use at most 88 characters and spaces only"
                )
            )
    previous: tokenize.TokenInfo | None = None
    ignored = {tokenize.NL, tokenize.COMMENT, tokenize.INDENT, tokenize.DEDENT}
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type in ignored:
            continue
        if (
            token.type == tokenize.STRING
            and previous
            and previous.type == tokenize.STRING
        ):
            issues.append(
                CodingIssue(
                    str(path),
                    token.start[0],
                    "Implicit string concatenation is forbidden",
                )
            )
        previous = token
    if len(source.splitlines()) > 500:
        issues.append(CodingIssue(str(path), 1, "Split modules longer than 500 lines"))
    return issues
