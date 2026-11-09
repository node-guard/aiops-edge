"""Lint guards for tenant isolation (S2-A2). No database required.

The guard has three parts:

* every public repository function must take ``tenant_id`` as a required
  keyword argument (no default, so a caller cannot omit it);
* raw ``select()`` inside the repository module is allowed only on tables that
  have no ``tenant_id`` of their own (``incident_links``), and only after the
  parent has been tenant-checked;
* no module outside ``central/db`` may build a query itself.

These are static checks: they catch the omission pattern. The behavioural proof
that a tenant cannot read or update another tenant's rows lives in
``tests/integration/test_repositories.py``, which runs against PostgreSQL.
"""

from __future__ import annotations

import ast
import uuid
from pathlib import Path

import pytest

from aiops.central.db import repositories
from aiops.central.db.models import Incident

ROOT = Path(__file__).resolve().parents[2]
CENTRAL = ROOT / "src" / "aiops" / "central"
REPOSITORIES = CENTRAL / "db" / "repositories.py"

# Tables without a tenant_id column; queries on them must follow a parent check.
NON_TENANT_TABLES = {"IncidentLink"}


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text())


def _functions(tree: ast.Module) -> list[ast.FunctionDef]:
    return [node for node in tree.body if isinstance(node, ast.FunctionDef)]


def _public_functions() -> list[ast.FunctionDef]:
    return [node for node in _functions(_tree(REPOSITORIES)) if not node.name.startswith("_")]


def test_there_is_something_to_guard() -> None:
    names = {node.name for node in _public_functions()}
    assert {"create_event", "get_incident", "link_incident", "tenant_select"} <= names


def test_every_public_function_requires_tenant_id_by_keyword() -> None:
    for node in _public_functions():
        positional = [argument.arg for argument in node.args.posonlyargs + node.args.args]
        assert "tenant_id" not in positional, node.name

        keyword_only = {
            argument.arg: default
            for argument, default in zip(node.args.kwonlyargs, node.args.kw_defaults, strict=True)
        }
        assert "tenant_id" in keyword_only, node.name
        assert keyword_only["tenant_id"] is None, f"{node.name} must not give tenant_id a default"


def test_raw_select_is_limited_to_tables_without_a_tenant_column() -> None:
    for function in _functions(_tree(REPOSITORIES)):
        if function.name == "tenant_select":
            continue
        for node in ast.walk(function):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "select"
            ):
                assert node.args, function.name
                target = node.args[0]
                assert isinstance(target, ast.Name), (function.name, ast.dump(target))
                assert (
                    target.id in NON_TENANT_TABLES
                ), f"{function.name} builds a raw select on {target.id}; use tenant_select instead"


def test_repository_never_uses_unscoped_session_shortcuts() -> None:
    for function in _functions(_tree(REPOSITORIES)):
        for node in ast.walk(function):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if not isinstance(node.func.value, ast.Name) or node.func.value.id != "session":
                continue
            assert node.func.attr not in {"get", "execute"}, (
                f"{function.name} uses session.{node.func.attr}; "
                "queries must start from tenant_select"
            )


def test_no_query_building_outside_the_repository_package() -> None:
    offenders: list[str] = []
    for path in CENTRAL.rglob("*.py"):
        if "db" in path.relative_to(CENTRAL).parts:
            continue
        source = path.read_text()
        for marker in ("select(", "session.get(", "session.execute("):
            if marker in source:
                offenders.append(f"{path.relative_to(ROOT)}: {marker}")
    assert not offenders, offenders


def test_tenant_select_compiles_with_the_tenant_predicate() -> None:
    tenant_id = uuid.uuid4()
    statement = repositories.tenant_select(Incident, tenant_id=tenant_id)
    sql = str(statement.compile())

    assert "incidents.tenant_id = " in sql


def test_tenant_id_none_is_rejected() -> None:
    with pytest.raises(ValueError, match="tenant_id is required"):
        repositories._require_tenant_id(None)
