# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM project
"""Reject hashlib/hmac calls that raise when Python runs on a FIPS host.

Under a FIPS-enforcing OpenSSL (e.g. RHEL 9 with `fips=1`), the system Python
behaves as follows (verified on AlmaLinux 9 in FIPS mode, Python 3.12):

* `hashlib.md5()`, `hashlib.blake2b()`, `hashlib.blake2s()` and
  `hashlib.new("md5")` raise unless `usedforsecurity=False` is passed.
* `hashlib.blake2b/blake2s` are routed through OpenSSL and accept only `data`
  and `usedforsecurity`: `digest_size=`, `key=`, `person=` etc. raise
  `TypeError` even with `usedforsecurity=False`.
* `hmac` cannot opt out, so an MD5 digestmod always raises.

Each of these is a crash at the call site, typically deep inside a request.
"""

import ast
import sys

FIPS_REJECTED = {"md5", "md4", "blake2b", "blake2s", "ripemd160", "sm3", "md5-sha1"}
BLAKE2 = {"blake2b", "blake2s"}

# (path, enclosing function) pairs that are FIPS-safe by construction.
ALLOWED = {
    # Tries md5 with the caller's usedforsecurity and falls back to sha256.
    ("vllm/utils/hashing.py", "safe_hash"),
}


def _dotted(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted(node.value)
        return f"{base}.{node.attr}" if base else None
    return None


def _not_for_security(call: ast.Call) -> bool:
    return any(
        kw.arg == "usedforsecurity"
        and isinstance(kw.value, ast.Constant)
        and kw.value.value is False
        for kw in call.keywords
    )


def _algo_name(node: ast.AST | None, aliases: dict[str, str]) -> str | None:
    """Resolve a hash name given as a string or a hashlib constructor."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value.lower()
    name = _dotted(node) if node is not None else None
    if name is None:
        return None
    name = aliases.get(name, name)
    if name.startswith("hashlib."):
        return name.removeprefix("hashlib.")
    return None


class _Checker(ast.NodeVisitor):
    def __init__(self, path: str):
        self.path = path
        self.aliases: dict[str, str] = {}
        self.func_stack: list[str] = []
        self.errors: list[str] = []

    def _error(self, node: ast.AST, msg: str) -> None:
        self.errors.append(f"{self.path}:{node.lineno}: {msg}")

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module == "hashlib":
            for a in node.names:
                self.aliases[a.asname or a.name] = f"hashlib.{a.name}"
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.func_stack.append(node.name)
        self.generic_visit(node)
        self.func_stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]

    def visit_Call(self, node: ast.Call) -> None:
        self.generic_visit(node)
        if any(
            (self.path == path or self.path.endswith(f"/{path}"))
            and func in self.func_stack
            for path, func in ALLOWED
        ):
            return
        name = _dotted(node.func)
        if name is None:
            return
        name = self.aliases.get(name, name)

        if name.startswith("hashlib."):
            algo = name.removeprefix("hashlib.")
            if algo == "new":
                algo = _algo_name(node.args[0] if node.args else None, {})
                if algo in FIPS_REJECTED and not _not_for_security(node):
                    self._error(
                        node,
                        f'hashlib.new("{algo}") raises on FIPS hosts; '
                        "pass usedforsecurity=False or use sha256",
                    )
                return
            if algo in BLAKE2 and (
                len(node.args) > 1
                or any(kw.arg != "usedforsecurity" for kw in node.keywords)
            ):
                self._error(
                    node,
                    f"hashlib.{algo}() parameters raise TypeError on FIPS "
                    "hosts; use hashlib.sha256 (truncate if needed)",
                )
            elif algo in FIPS_REJECTED and not _not_for_security(node):
                self._error(
                    node,
                    f"hashlib.{algo}() raises on FIPS hosts; "
                    "pass usedforsecurity=False or use sha256",
                )
        elif name in ("hmac.new", "hmac.digest", "hmac.HMAC"):
            kwarg = "digest" if name == "hmac.digest" else "digestmod"
            digestmod = next(
                (kw.value for kw in node.keywords if kw.arg == kwarg),
                node.args[2] if len(node.args) > 2 else None,
            )
            algo = _algo_name(digestmod, self.aliases)
            if algo in FIPS_REJECTED:
                self._error(node, f"HMAC-{algo} raises on FIPS hosts")


def check_file(path: str) -> list[str]:
    with open(path, encoding="utf-8") as f:
        source = f.read()
    try:
        tree = ast.parse(source, path)
    except SyntaxError:
        return []
    checker = _Checker(path.replace("\\", "/"))
    checker.visit(tree)
    return checker.errors


def main(argv: list[str]) -> int:
    errors = [e for path in argv for e in check_file(path)]
    for e in errors:
        print(e)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
