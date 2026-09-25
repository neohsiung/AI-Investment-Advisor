"""
AST Security Auditor for Autonomous Code Generation
====================================================
針對系統自主生成的量化因子與策略代碼執行深度抽象語法樹 (AST) 靜態安全稽核。

核心原則：
1. 嚴格白名單 (Strict Whitelist): 僅放行純量化與向量計算函式庫 (numpy, pandas, math, scipy, typing)。
2. 零特權 (Zero-Privilege): 嚴禁任何檔案系統 I/O、網路通信、進程控制、系統環境變數與動態代碼執行。
3. 終止性與複雜度保證 (Termination Guard): 禁止無窮迴圈 (While)、遞迴調用與深層嵌套。
4. Constraint #0 合規: 嚴格檢查異常處理邏輯，絕不允許靜默吞噬錯誤。
"""
from __future__ import annotations

import ast
import hashlib
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Set

logger = logging.getLogger("ASTSecurityAuditor")


@dataclass
class AuditResult:
    """
    Result of AST static code security audit.
    AST 靜態代碼安全審計結果。
    """
    passed: bool
    violations: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    ast_hash: str = ""
    metrics: Dict[str, Any] = field(default_factory=dict)

    @property
    def summary(self) -> str:
        status = "PASSED" if self.passed else "FAILED"
        return f"[{status}] Violations: {len(self.violations)}, Warnings: {len(self.warnings)}"


class ASTSecurityAuditor:
    """
    Comprehensive AST static code security auditor.
    全方位 AST 靜態代碼安全審計器。
    """

    ALLOWED_MODULES: Set[str] = {
        "numpy",
        "np",
        "pandas",
        "pd",
        "math",
        "scipy",
        "typing",
        "datetime",  # Safe pure-data datetime operations
    }

    FORBIDDEN_CALLS: Set[str] = {
        "open",
        "exec",
        "eval",
        "compile",
        "__import__",
        "globals",
        "locals",
        "getattr",
        "setattr",
        "delattr",
        "input",
        "breakpoint",
        "exit",
        "quit",
        "help",
        "vars",
        "memoryview",
        "id",
    }

    FORBIDDEN_ATTRIBUTES: Set[str] = {
        "__subclasses__",
        "__bases__",
        "__mro__",
        "__globals__",
        "__builtins__",
        "__code__",
        "__dict__",
        "__class__",
    }

    MAX_CODE_LINES: int = 200
    MAX_LOOP_NESTING_DEPTH: int = 2

    def audit(self, source_code: str) -> AuditResult:
        """
        Audit Python source code for security, purity, and complexity.
        審計 Python 代碼之安全性、純函式特性與結構複雜度。
        """
        violations: List[str] = []
        warnings: List[str] = []
        metrics: Dict[str, Any] = {
            "total_lines": 0,
            "total_nodes": 0,
            "max_loop_depth": 0,
            "functions": [],
            "imports": [],
        }

        # 1. 基礎長度與語法解析檢查
        lines = source_code.splitlines()
        metrics["total_lines"] = len(lines)
        if len(lines) > self.MAX_CODE_LINES:
            violations.append(
                f"Code exceeds maximum allowed lines ({len(lines)} > {self.MAX_CODE_LINES})"
            )

        try:
            tree = ast.parse(source_code)
        except SyntaxError as e:
            violations.append(f"Python SyntaxError: {e.msg} at line {e.lineno}")
            return AuditResult(
                passed=False,
                violations=violations,
                warnings=warnings,
                ast_hash=hashlib.sha256(source_code.encode("utf-8")).hexdigest(),
                metrics=metrics,
            )

        # 計算 AST 語意雜湊 (以 dump 形式排除排版差異)
        ast_dump = ast.dump(tree, annotate_fields=False)
        ast_hash = hashlib.sha256(ast_dump.encode("utf-8")).hexdigest()

        # 2. 節點遍歷與安全掃描
        visitor = _SecurityVisitor(
            allowed_modules=self.ALLOWED_MODULES,
            forbidden_calls=self.FORBIDDEN_CALLS,
            forbidden_attributes=self.FORBIDDEN_ATTRIBUTES,
            max_loop_depth=self.MAX_LOOP_NESTING_DEPTH,
        )
        visitor.visit(tree)

        violations.extend(visitor.violations)
        warnings.extend(visitor.warnings)

        metrics["total_nodes"] = visitor.total_nodes
        metrics["max_loop_depth"] = visitor.max_loop_depth
        metrics["functions"] = visitor.discovered_functions
        metrics["imports"] = visitor.discovered_imports

        # 3. 確保至少定義了一個可調用的頂層計算函式
        if not visitor.discovered_functions:
            violations.append("Source code must define at least one top-level calculation function")

        passed = len(violations) == 0
        if not passed:
            logger.warning(
                "Autonomous code failed security audit: %d violations found: %s",
                len(violations),
                violations,
            )

        return AuditResult(
            passed=passed,
            violations=violations,
            warnings=warnings,
            ast_hash=ast_hash,
            metrics=metrics,
        )


class _SecurityVisitor(ast.NodeVisitor):
    """
    Internal AST visitor to inspect nodes.
    """

    def __init__(
        self,
        allowed_modules: Set[str],
        forbidden_calls: Set[str],
        forbidden_attributes: Set[str],
        max_loop_depth: int,
    ):
        self.allowed_modules = allowed_modules
        self.forbidden_calls = forbidden_calls
        self.forbidden_attributes = forbidden_attributes
        self.max_loop_depth_allowed = max_loop_depth

        self.violations: List[str] = []
        self.warnings: List[str] = []
        self.total_nodes: int = 0
        self.max_loop_depth: int = 0
        self.current_loop_depth: int = 0
        self.current_function_name: str = ""
        self.discovered_functions: List[str] = []
        self.discovered_imports: List[str] = []

    def generic_visit(self, node: ast.AST):
        self.total_nodes += 1
        super().generic_visit(node)

    # --- 模組導入檢查 (Module Import Inspection) ---
    def visit_Import(self, node: ast.Import):
        self.total_nodes += 1
        for alias in node.names:
            root_module = alias.name.split(".")[0]
            self.discovered_imports.append(alias.name)
            if root_module not in self.allowed_modules:
                self.violations.append(
                    f"Line {node.lineno}: Forbidden module import '{alias.name}'. "
                    f"Allowed modules: {sorted(list(self.allowed_modules))}"
                )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        self.total_nodes += 1
        if node.module:
            root_module = node.module.split(".")[0]
            self.discovered_imports.append(node.module)
            if root_module not in self.allowed_modules:
                self.violations.append(
                    f"Line {node.lineno}: Forbidden module import 'from {node.module}'. "
                    f"Allowed modules: {sorted(list(self.allowed_modules))}"
                )
        self.generic_visit(node)

    # --- 函式定義與遞迴檢查 (Function Def & Recursion) ---
    def visit_FunctionDef(self, node: ast.FunctionDef):
        self.total_nodes += 1
        previous_func = self.current_function_name
        self.current_function_name = node.name
        self.discovered_functions.append(node.name)

        # 檢查型別標註 (Type Annotations)
        if not node.returns:
            self.warnings.append(
                f"Line {node.lineno}: Function '{node.name}' is missing return type annotation"
            )
        for arg in node.args.args:
            if not arg.annotation and arg.arg != "self":
                self.warnings.append(
                    f"Line {node.lineno}: Argument '{arg.arg}' in '{node.name}' is missing type annotation"
                )

        self.generic_visit(node)
        self.current_function_name = previous_func

    # --- 禁用的控制流結構 (Forbidden Control Flows) ---
    def visit_While(self, node: ast.While):
        self.total_nodes += 1
        self.violations.append(
            f"Line {node.lineno}: 'while' loops are strictly forbidden to prevent infinite loops. "
            "Use vectorized pandas/numpy operations or bounded 'for' loops."
        )
        self.generic_visit(node)

    def visit_For(self, node: ast.For):
        self.total_nodes += 1
        self.current_loop_depth += 1
        if self.current_loop_depth > self.max_loop_depth:
            self.max_loop_depth = self.current_loop_depth
        if self.current_loop_depth > self.max_loop_depth_allowed:
            self.violations.append(
                f"Line {node.lineno}: Nested loop depth ({self.current_loop_depth}) exceeds "
                f"maximum allowed depth ({self.max_loop_depth_allowed})"
            )
        self.generic_visit(node)
        self.current_loop_depth -= 1

    def visit_Global(self, node: ast.Global):
        self.total_nodes += 1
        self.violations.append(
            f"Line {node.lineno}: 'global' statement is forbidden. Code must be pure functions."
        )
        self.generic_visit(node)

    def visit_Nonlocal(self, node: ast.Nonlocal):
        self.total_nodes += 1
        self.violations.append(
            f"Line {node.lineno}: 'nonlocal' statement is forbidden."
        )
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        self.total_nodes += 1
        self.violations.append(
            f"Line {node.lineno}: 'async def' is forbidden. Quantitative factor functions must be synchronous pure functions."
        )
        self.generic_visit(node)

    def visit_Yield(self, node: ast.Yield):
        self.total_nodes += 1
        self.violations.append(f"Line {node.lineno}: 'yield' is forbidden in factor functions.")
        self.generic_visit(node)

    def visit_YieldFrom(self, node: ast.YieldFrom):
        self.total_nodes += 1
        self.violations.append(f"Line {node.lineno}: 'yield from' is forbidden.")
        self.generic_visit(node)

    # --- 函式調用檢查 (Call Inspection) ---
    def visit_Call(self, node: ast.Call):
        self.total_nodes += 1

        # 1. 檢查直接呼叫危險內建函式
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
            if func_name in self.forbidden_calls:
                self.violations.append(
                    f"Line {node.lineno}: Forbidden function call '{func_name}()'"
                )
            # 檢查自我遞迴調用 (Direct recursion check)
            if self.current_function_name and func_name == self.current_function_name:
                self.violations.append(
                    f"Line {node.lineno}: Self-recursion detected in '{func_name}()'. Recursion is strictly forbidden."
                )

        # 2. 檢查方法調用 (如 obj.__subclasses__())
        elif isinstance(node.func, ast.Attribute):
            attr_name = node.func.attr
            if attr_name in self.forbidden_attributes or attr_name in self.forbidden_calls:
                self.violations.append(
                    f"Line {node.lineno}: Forbidden method or attribute call '.{attr_name}()'"
                )

        self.generic_visit(node)

    # --- 屬性存取檢查 (Attribute Access Inspection) ---
    def visit_Attribute(self, node: ast.Attribute):
        self.total_nodes += 1
        if node.attr in self.forbidden_attributes:
            self.violations.append(
                f"Line {node.lineno}: Forbidden attribute access '.{node.attr}'"
            )
        self.generic_visit(node)

    # --- Constraint #0: 靜默失敗檢查 (Fail-Silent Prevention) ---
    def visit_ExceptHandler(self, node: ast.ExceptHandler):
        self.total_nodes += 1
        # 檢查 bare except 或吞噬異常模式
        # 若 except handler 只有 pass 或回傳固定預設值，且沒有 re-raise 或記錄，違反 Constraint #0
        has_reraise = False
        returns_plausible = False
        for sub in ast.walk(node):
            if isinstance(sub, ast.Raise):
                has_reraise = True
            elif isinstance(sub, ast.Return):
                # 如果回傳具體數值 (非 None)，視為可能產出虛假讀數
                val = sub.value
                if val is not None and not (isinstance(val, ast.Constant) and val.value is None):
                    returns_plausible = True

        # 若只有 pass (空 body) 且無 re-raise
        if len(node.body) == 1 and isinstance(node.body[0], ast.Pass) and not has_reraise:
            self.violations.append(
                f"Line {node.lineno}: Bare 'except: pass' without re-raising or logging violates Constraint #0 (Fail-Silent Prevention)."
            )
        elif returns_plausible and not has_reraise:
            self.warnings.append(
                f"Line {node.lineno}: Exception handler returns a plausible value. Ensure fallback is explicitly flagged."
            )

        self.generic_visit(node)
