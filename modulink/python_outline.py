"""Pure Python source outline helper (no Qt / ModuLink dependency).

Used by host strategy editors and ModuLink StrategyModule (independent parse
of stored scripts). Safe to reuse in other projects.
"""

from __future__ import annotations

import ast
from typing import Any


def _end_lineno(node: ast.AST) -> int:
    end = getattr(node, "end_lineno", None)
    if isinstance(end, int) and end > 0:
        return end
    last = getattr(node, "lineno", 1) or 1
    for child in ast.walk(node):
        child_ln = getattr(child, "lineno", None)
        if isinstance(child_ln, int) and child_ln > last:
            last = child_ln
    return last


def _expr_to_str(node: ast.AST | None, limit: int = 48) -> str:
    if node is None:
        return ""
    try:
        text = ast.unparse(node)
    except Exception:
        text = getattr(node, "id", None) or type(node).__name__
    text = " ".join(str(text).split())
    if len(text) > limit:
        return text[: max(0, limit - 1)] + "…"
    return text


def _is_constant_name(name: str) -> bool:
    if not name or not name.isupper():
        return False
    return any(c.isalpha() for c in name)


def _format_arguments(args: ast.arguments) -> str:
    """Return a compact "(a, b=1, *args, **kwargs)" string for outline labels."""

    def _arg_piece(arg: ast.arg, default=None, *, has_default: bool = False) -> str:
        piece = arg.arg
        ann = _expr_to_str(arg.annotation, limit=18)
        if ann:
            piece = f"{piece}: {ann}"
        if has_default:
            piece = f"{piece}={_expr_to_str(default, limit=18)}"
        return piece

    try:
        parts: list[str] = []
        positional = list(args.posonlyargs or []) + list(args.args or [])
        defaults = list(args.defaults or [])
        default_offset = len(positional) - len(defaults)
        for i, arg in enumerate(positional):
            has_default = i >= default_offset
            default = defaults[i - default_offset] if has_default else None
            parts.append(_arg_piece(arg, default, has_default=has_default))
            if args.posonlyargs and i == len(args.posonlyargs) - 1:
                parts.append("/")

        if args.vararg is not None:
            parts.append("*" + _arg_piece(args.vararg))
        elif args.kwonlyargs:
            parts.append("*")

        kw_defaults = list(args.kw_defaults or [])
        for i, arg in enumerate(args.kwonlyargs or []):
            default = kw_defaults[i] if i < len(kw_defaults) else None
            # kw_defaults uses None for required keyword-only args.
            has_default = i < len(kw_defaults) and default is not None
            parts.append(_arg_piece(arg, default, has_default=has_default))

        if args.kwarg is not None:
            parts.append("**" + _arg_piece(args.kwarg))

        return "(" + ", ".join(parts) + ")"
    except Exception:
        return "()"


def _decorator_names(node: ast.AST) -> list[str]:
    names: list[str] = []
    for dec in getattr(node, "decorator_list", None) or []:
        text = _expr_to_str(dec, limit=32)
        if text:
            names.append(text)
    return names


def _target_names(target: ast.AST) -> list[str]:
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, (ast.Tuple, ast.List)):
        names: list[str] = []
        for elt in target.elts:
            names.extend(_target_names(elt))
        return names
    if isinstance(target, ast.Attribute):
        return [_expr_to_str(target, limit=40)]
    if isinstance(target, ast.Starred):
        return _target_names(target.value)
    return []


def _make_entry(
    *,
    kind: str,
    name: str,
    lineno: int,
    end_lineno: int | None = None,
    qualified: str = "",
    depth: int = 0,
    signature: str = "",
    decorators: list[str] | None = None,
    bases: list[str] | None = None,
    annotation: str = "",
    detail: str = "",
    children: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "kind": kind,
        "name": name,
        "qualified": qualified or name,
        "lineno": int(lineno or 1),
        "end_lineno": int(end_lineno or lineno or 1),
        "depth": int(depth),
        "signature": signature or "",
        "decorators": list(decorators or []),
        "bases": list(bases or []),
        "annotation": annotation or "",
        "detail": detail or "",
        "children": list(children or []),
    }


def flatten_outline(entries: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Depth-first flatten of a nested outline (children dropped on each row)."""
    flat: list[dict[str, Any]] = []

    def _walk(nodes: list[dict[str, Any]], depth: int = 0):
        for node in nodes or []:
            row = dict(node)
            kids = row.pop("children", []) or []
            row["depth"] = depth
            flat.append(row)
            _walk(kids, depth + 1)

    _walk(entries or [])
    return flat


def build_python_outline(source: str, *, nested: bool = True) -> list[dict[str, Any]]:
    """
    Return a structural index of the module.

    Nested mode (default) yields a tree via ``children``. Flat mode yields a
    depth-first list with a ``depth`` field (no ``children``).

    Entry kinds:
      class, function, async_function, method, async_method,
      variable, constant, import, import_from, error

    Extra fields (when available):
      qualified, lineno, end_lineno, depth, signature, decorators,
      bases, annotation, detail, children
    """
    if source is None:
        return []
    text = source if isinstance(source, str) else str(source)
    if not text.strip():
        return []
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        msg = (exc.msg or "invalid syntax").strip()
        line = int(exc.lineno or 1)
        return [
            _make_entry(
                kind="error",
                name=msg,
                lineno=line,
                end_lineno=line,
                detail=f"SyntaxError at line {line}",
            )
        ]
    except Exception:
        return []

    def _walk(nodes, *, prefix: str = "", depth: int = 0, in_class: bool = False):
        entries: list[dict[str, Any]] = []
        for node in nodes or []:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                is_async = isinstance(node, ast.AsyncFunctionDef)
                if in_class:
                    kind = "async_method" if is_async else "method"
                else:
                    kind = "async_function" if is_async else "function"
                name = node.name
                qualified = f"{prefix}{name}" if prefix else name
                child_entries = _walk(
                    node.body,
                    prefix=f"{qualified}.",
                    depth=depth + 1,
                    in_class=False,
                )
                # Nested outline inside functions: keep nested defs/classes only
                # (skip local variables — too noisy for navigation).
                child_entries = [
                    c
                    for c in child_entries
                    if c.get("kind")
                    in {
                        "class",
                        "function",
                        "async_function",
                        "method",
                        "async_method",
                    }
                ]
                entries.append(
                    _make_entry(
                        kind=kind,
                        name=name,
                        qualified=qualified,
                        lineno=int(node.lineno or 1),
                        end_lineno=_end_lineno(node),
                        depth=depth,
                        signature=_format_arguments(node.args),
                        decorators=_decorator_names(node),
                        annotation=_expr_to_str(getattr(node, "returns", None), limit=24),
                        children=child_entries,
                    )
                )
            elif isinstance(node, ast.ClassDef):
                name = node.name
                qualified = f"{prefix}{name}" if prefix else name
                bases = [_expr_to_str(b, limit=28) for b in (node.bases or [])]
                child_entries = _walk(
                    node.body,
                    prefix=f"{qualified}.",
                    depth=depth + 1,
                    in_class=True,
                )
                entries.append(
                    _make_entry(
                        kind="class",
                        name=name,
                        qualified=qualified,
                        lineno=int(node.lineno or 1),
                        end_lineno=_end_lineno(node),
                        depth=depth,
                        decorators=_decorator_names(node),
                        bases=bases,
                        children=child_entries,
                    )
                )
            elif isinstance(node, (ast.Import, ast.ImportFrom)) and depth == 0:
                lineno = int(getattr(node, "lineno", 1) or 1)
                end = _end_lineno(node)
                if isinstance(node, ast.Import):
                    for alias in node.names or []:
                        label = alias.name
                        if alias.asname:
                            label = f"{alias.name} as {alias.asname}"
                        entries.append(
                            _make_entry(
                                kind="import",
                                name=label,
                                qualified=label,
                                lineno=lineno,
                                end_lineno=end,
                                depth=depth,
                                detail="import",
                            )
                        )
                else:
                    module = node.module or ""
                    level = getattr(node, "level", 0) or 0
                    dots = "." * int(level)
                    mod_label = f"{dots}{module}" if module or dots else "."
                    for alias in node.names or []:
                        imported = alias.name
                        if alias.asname:
                            imported = f"{alias.name} as {alias.asname}"
                        label = (
                            f"{imported}"
                            if mod_label in ("", ".")
                            else f"{imported} ← {mod_label}"
                        )
                        entries.append(
                            _make_entry(
                                kind="import_from",
                                name=label,
                                qualified=label,
                                lineno=lineno,
                                end_lineno=end,
                                depth=depth,
                                detail=f"from {mod_label}",
                            )
                        )
            elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)) and (
                depth == 0 or in_class
            ):
                lineno = int(getattr(node, "lineno", 1) or 1)
                end = _end_lineno(node)
                annotation = ""
                detail = ""
                names: list[str] = []
                if isinstance(node, ast.AnnAssign):
                    names = _target_names(node.target)
                    annotation = _expr_to_str(node.annotation, limit=24)
                    if node.value is not None:
                        detail = _expr_to_str(node.value, limit=32)
                elif isinstance(node, ast.AugAssign):
                    names = _target_names(node.target)
                    detail = _expr_to_str(node.value, limit=32)
                else:
                    for target in node.targets:
                        names.extend(_target_names(target))
                    detail = _expr_to_str(node.value, limit=32)

                for name in names:
                    if not name or name == "_":
                        continue
                    # Skip dunder / private class plumbing noise a bit
                    if in_class and name.startswith("__") and name.endswith("__"):
                        continue
                    kind = "constant" if _is_constant_name(name) else "variable"
                    qualified = f"{prefix}{name}" if prefix else name
                    entries.append(
                        _make_entry(
                            kind=kind,
                            name=name,
                            qualified=qualified,
                            lineno=lineno,
                            end_lineno=end,
                            depth=depth,
                            annotation=annotation,
                            detail=detail,
                        )
                    )
        return entries

    nested_entries = _walk(getattr(tree, "body", []) or [], prefix="", depth=0, in_class=False)
    if nested:
        return nested_entries
    return flatten_outline(nested_entries)


def build_strategies_outline(strategies: dict | None) -> dict[str, list[dict[str, Any]]]:
    """Build {script_name: outline_entries} for a strategies dict (nested trees)."""
    result: dict[str, list[dict[str, Any]]] = {}
    if not isinstance(strategies, dict):
        return result
    for name, code in strategies.items():
        key = str(name)
        result[key] = build_python_outline("" if code is None else str(code), nested=True)
    return result
