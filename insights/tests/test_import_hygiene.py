# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Import-graph invariants that keep the app safe under concurrent requests.

Production reported, repeatedly:

    insights.api.ml.sales_intelligence did not complete -- the server returned
    a gateway error instead of a response

with `_DeadlockError: deadlock detected by _ModuleLock(...)` in the log. Cause:
package `__init__` files that re-exported their own subtree eagerly.
`insights/ml/__init__.py` was the worst -- being the parent of every ML module,
any `from insights.ml.X import ...` initialised it first and it pulled in
eleven model classes while holding its own module lock. A second concurrent
request either blocked behind the whole chain or deadlocked against it.

Measured on the pre-fix tree with eight endpoints called concurrently on a cold
module cache: 26 of 32 requests failed. After: 40 of 40 passed.

These are static checks on purpose. The real failure needs two threads racing
inside importlib, which makes a runtime reproduction timing-dependent and
flaky in CI. The structural precondition is exact, cheap and deterministic, so
that is what gets asserted.
"""

import ast
import os
import unittest
from collections import defaultdict

import frappe

PACKAGE = "insights"

# `insights.api.ml` imports `.utils` eagerly and documents why: no circular
# refs, no heavy dependencies, and it is needed to resolve the lazy map. The
# module imports nothing from `insights.api.ml`, so it cannot close a loop.
ALLOWED_EAGER = {("insights.api.ml", "insights.api.ml.utils")}

SKIP_DIRS = ("__pycache__", "/tests/", "/patches/", "/node_modules/")


def _app_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _module_name(path: str, root: str) -> str:
    rel = os.path.relpath(path, os.path.dirname(root))
    parts = rel[: -len(".py")].split(os.sep)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _build_graph():
    """Top-level intra-package imports only -- those hold the module lock."""
    root = _app_root()
    edges = defaultdict(set)
    files = {}

    for dirpath, _dirnames, filenames in os.walk(root):
        for filename in filenames:
            if not filename.endswith(".py"):
                continue
            full = os.path.join(dirpath, filename)
            if any(skip in full for skip in SKIP_DIRS):
                continue
            name = _module_name(full, root)
            files[name] = full
            try:
                with open(full, encoding="utf-8") as handle:
                    tree = ast.parse(handle.read())
            except (SyntaxError, UnicodeDecodeError):
                continue
            for node in tree.body:  # module level only
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.startswith(PACKAGE):
                            edges[name].add(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    if node.level:
                        base = (
                            name.rsplit(".", node.level)[0]
                            if node.level <= name.count(".")
                            else PACKAGE
                        )
                        target = f"{base}.{node.module}" if node.module else base
                    else:
                        target = node.module or ""
                    if target.startswith(PACKAGE):
                        edges[name].add(target)
                        for alias in node.names:
                            edges[name].add(f"{target}.{alias.name}")

    known = set(files)
    graph = {m: {t for t in ts if t in known and t != m} for m, ts in edges.items()}
    return graph, files


class TestImportHygiene(unittest.TestCase):
    def test_no_circular_imports(self):
        """A cycle between two modules is a deadlock waiting for a second thread.

        Single-threaded, Python resolves these fine -- module locks are
        reentrant per thread, which is why the app booted and every one-request
        probe passed. Two concurrent requests is all it takes for each thread to
        hold the lock the other needs.
        """
        graph, _files = _build_graph()
        cycles, seen, visited = [], set(), set()

        def walk(node, stack, onstack):
            for nxt in sorted(graph.get(node, ())):
                if nxt in onstack:
                    cycle = stack[stack.index(nxt) :] + [nxt]
                    key = frozenset(cycle)
                    if key not in seen:
                        seen.add(key)
                        cycles.append(cycle)
                elif nxt not in visited:
                    walk(nxt, stack + [nxt], onstack | {nxt})
            visited.add(node)

        for module in sorted(graph):
            if module not in visited:
                walk(module, [module], {module})

        self.assertEqual(
            [],
            [" -> ".join(c) for c in cycles],
            "circular imports deadlock under concurrent requests",
        )

    def test_packages_do_not_eagerly_import_their_own_subtree(self):
        """A package `__init__` must not import its own submodules at import time.

        This is the precondition that actually caused the outage, and it bites
        even with no cycle at all: `insights/ml/strategic_finance/__init__.py`
        had none, and still deadlocked, because holding the package lock while
        loading a subtree is enough on its own. Any thread importing a submodule
        directly closes the loop.

        Use the lazy `__getattr__` map -- see `insights/ml/__init__.py`.
        """
        graph, files = _build_graph()
        offenders = []
        for module, targets in sorted(graph.items()):
            if not files.get(module, "").endswith("__init__.py"):
                continue
            for target in sorted(targets):
                if target.startswith(module + ".") and (module, target) not in ALLOWED_EAGER:
                    offenders.append(f"{module} eagerly imports {target}")

        self.assertEqual(
            [], offenders, "package __init__ holding its lock while loading a subtree"
        )

    def test_no_from_package_import_submodule(self):
        """`from <pkg> import <submodule>` waits for the package to finish.

        It cannot resolve until `<pkg>.__init__` has completed, so it blocks
        against whichever thread is initialising the package. Import the
        submodule by path instead -- that only needs the parent present in
        sys.modules, not finished.
        """
        _graph, files = _build_graph()
        packages = {m for m, p in files.items() if p.endswith("__init__.py")}
        offenders = []

        for module, path in sorted(files.items()):
            if any(skip in path for skip in SKIP_DIRS):
                continue
            try:
                with open(path, encoding="utf-8") as handle:
                    tree = ast.parse(handle.read())
            except (SyntaxError, UnicodeDecodeError):
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.ImportFrom) or node.level:
                    continue
                target = node.module or ""
                if target not in packages:
                    continue
                for alias in node.names:
                    candidate = f"{target}.{alias.name}"
                    if candidate in files and (target, candidate) not in ALLOWED_EAGER:
                        offenders.append(
                            f"{module}:{node.lineno} from {target} import {alias.name}"
                        )

        self.assertEqual(
            [], offenders, "use `import pkg.sub as x`, not `from pkg import sub`"
        )


if __name__ == "__main__":
    frappe.init(site=frappe.local.site if hasattr(frappe.local, "site") else "jkm")
    unittest.main()
