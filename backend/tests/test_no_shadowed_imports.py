"""Guard against function-local imports that shadow module-level ones.

Python treats any `import X` inside a function body as a *local* binding for
the entire function scope. The dangerous case is when the local `import X`
is inside a CONDITIONAL block (if/try/for/while/with) — then `X` is local
to the whole function, but the import only binds it on the executed path.
Any reference to `X` from a path where the import didn't run raises
`UnboundLocalError: cannot access local variable 'X' where it is not
associated with a value`.

This bit Kahani's TTS pipeline at variant_endpoints.py:1017 (asyncio
shadowed by an `import asyncio` ~15 lines below inside an `if` block) —
silently disabled the post-scene TTS polish scheduling, which surfaced as
long delays when hitting Play.

This test flags only the dangerous nested-import pattern. Unconditional
function-local imports (e.g. at the top of the function body) are redundant
when the name is already module-level but cannot cause UnboundLocalError,
so they're not flagged here.
"""
import ast
from pathlib import Path
from typing import List, Tuple


BACKEND_ROOT = Path(__file__).resolve().parent.parent
APP_DIR = BACKEND_ROOT / "app"

# AST node types that introduce a control-flow branch — an import inside
# any of these only executes when the branch is taken.
CONDITIONAL_PARENT_TYPES = (
    ast.If,
    ast.Try,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.With,
    ast.AsyncWith,
    ast.ExceptHandler,
)


def _module_level_names(tree: ast.Module) -> set:
    """Names imported at the top level of `tree`."""
    names: set = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                names.add(alias.asname or alias.name)
    return names


def _import_names(node: ast.AST) -> List[str]:
    """Names introduced by an Import/ImportFrom node."""
    if isinstance(node, ast.Import):
        return [(alias.asname or alias.name).split(".")[0] for alias in node.names]
    if isinstance(node, ast.ImportFrom):
        return [alias.asname or alias.name for alias in node.names]
    return []


def _function_bodies(tree: ast.Module):
    """Yield (function_node, function_body_root_set) for every function/method."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield node


def _walk_with_parents(root: ast.AST):
    """Yield (node, [ancestor_chain]) for every node under `root` (exclusive)."""
    stack: List[Tuple[ast.AST, List[ast.AST]]] = []
    for child in ast.iter_child_nodes(root):
        stack.append((child, [root]))
    while stack:
        node, ancestors = stack.pop()
        yield node, ancestors
        for child in ast.iter_child_nodes(node):
            stack.append((child, ancestors + [node]))


def _enclosing_conditional(ancestors: List[ast.AST], fn: ast.AST) -> ast.AST:
    """Return the outermost conditional/with/loop/try node in `ancestors` that
    lives INSIDE the function `fn` (not above it). None if no such ancestor.

    `ancestors` is in root→leaf order; we want ancestors *under* `fn` only,
    skipping `fn` itself and anything above it, and skipping any other
    nested function definitions (those introduce their own scope so an
    import inside them shadows only within that inner scope, which is
    handled when we visit that function separately)."""
    # Find fn in the ancestor chain; everything BEFORE it is outside fn.
    try:
        fn_idx = ancestors.index(fn)
    except ValueError:
        # fn isn't in the ancestor chain — we're walking a different scope.
        return None
    inner = ancestors[fn_idx + 1:]
    out = None
    for anc in inner:
        # Crossing into another function = different scope; stop here so the
        # nested function gets analyzed in its own pass.
        if isinstance(anc, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            return None
        if isinstance(anc, CONDITIONAL_PARENT_TYPES):
            out = anc
    return out


def _references_outside(
    fn: ast.AST, name: str, exclude_subtree: ast.AST
) -> List[int]:
    """Return line numbers where `name` is referenced inside `fn` but OUTSIDE
    the subtree rooted at `exclude_subtree` (which is the conditional block
    that contains the local import). A reference outside that subtree is
    what triggers UnboundLocalError when the import didn't run."""
    excluded_ids = set()
    for node in ast.walk(exclude_subtree):
        excluded_ids.add(id(node))

    lines: List[int] = []
    for node in ast.walk(fn):
        if id(node) in excluded_ids:
            continue
        if isinstance(node, ast.Name) and node.id == name:
            lines.append(node.lineno)
        elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == name:
            lines.append(node.lineno)
    return lines


def _scan_file(path: Path) -> List[str]:
    """Return human-readable findings for `path`.

    Flags only the exact UnboundLocalError-producing pattern:
    1. Name X is imported at module level.
    2. Function `fn` has a local `import X` inside a conditional/loop/with/try block.
    3. `fn` references X somewhere OUTSIDE that conditional block.

    Cases 1+2 without 3 are merely redundant; safe at runtime.
    """
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return []

    module_names = _module_level_names(tree)
    if not module_names:
        return []

    findings: List[str] = []
    for fn in _function_bodies(tree):
        for node, ancestors in _walk_with_parents(fn):
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            enclosing = _enclosing_conditional(ancestors, fn)
            if enclosing is None:
                continue
            for name in _import_names(node):
                if name not in module_names:
                    continue
                outside_refs = _references_outside(fn, name, enclosing)
                if outside_refs:
                    findings.append(
                        f"{path.relative_to(BACKEND_ROOT)}:{node.lineno}: "
                        f"conditional `import {name}` inside `{fn.name}()` "
                        f"shadows module-level `import {name}`; `{name}` is "
                        f"also referenced at line(s) {outside_refs[:3]}{'...' if len(outside_refs) > 3 else ''} "
                        f"outside the conditional — UnboundLocalError risk"
                    )
    return findings


def test_no_shadowed_conditional_imports():
    """Fail if any .py under app/ has the exact pattern that triggers
    UnboundLocalError at runtime: a conditional `import X` shadowing a
    module-level `import X`, while the function also references X
    outside that conditional."""
    all_findings: List[str] = []
    for py_file in APP_DIR.rglob("*.py"):
        all_findings.extend(_scan_file(py_file))
    assert not all_findings, (
        f"{len(all_findings)} dangerous shadowed import(s) found:\n"
        + "\n".join("  " + f for f in all_findings)
    )
