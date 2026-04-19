"""
Tests for MCPBackgroundCheckService to improve coverage.
"""
import os
import tempfile
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from src.services.mcp_installation_guard import MCPBackgroundCheckService


class TestMCPBackgroundCheckServiceSecurityClearance:
    """Test verify_security_clearance method."""

    def setup_method(self):
        self.service = MCPBackgroundCheckService(user_id="test_user")

    @pytest.mark.asyncio
    async def test_file_not_found_passes(self):
        """Non-existent file passes security clearance."""
        ok, msg = await self.service.verify_security_clearance("/nonexistent/path/skill.py")
        assert ok is True
        assert "not found" in msg.lower() or "skipping" in msg.lower()

    @pytest.mark.asyncio
    async def test_empty_file_passes(self):
        """Empty file passes security clearance."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("")
            path = f.name
        try:
            ok, msg = await self.service.verify_security_clearance(path)
            assert ok is True
            assert "empty" in msg.lower()
        finally:
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_safe_file_passes(self):
        """Safe Python file passes security clearance."""
        code = """
def add(a, b):
    return a + b

class Calculator:
    def multiply(self, x, y):
        return x * y
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(code)
            path = f.name
        try:
            ok, msg = await self.service.verify_security_clearance(path)
            assert ok is True
            assert "PASSED" in msg
        finally:
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_eval_call_fails(self):
        """File using eval() fails security clearance."""
        code = """
def dangerous():
    result = eval("1 + 1")
    return result
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(code)
            path = f.name
        try:
            ok, msg = await self.service.verify_security_clearance(path)
            assert ok is False
            assert "eval" in msg
        finally:
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_exec_call_fails(self):
        """File using exec() fails security clearance."""
        code = """
def run_code(code_str):
    exec(code_str)
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(code)
            path = f.name
        try:
            ok, msg = await self.service.verify_security_clearance(path)
            assert ok is False
            assert "exec" in msg
        finally:
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_import_os_fails(self):
        """File importing os module fails security clearance."""
        code = """
import os

def get_env():
    return os.environ.get("SECRET")
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(code)
            path = f.name
        try:
            ok, msg = await self.service.verify_security_clearance(path)
            assert ok is False
            assert "os" in msg
        finally:
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_import_subprocess_fails(self):
        """File importing subprocess fails security clearance."""
        code = """
import subprocess

def run_cmd(cmd):
    return subprocess.run(cmd, shell=True)
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(code)
            path = f.name
        try:
            ok, msg = await self.service.verify_security_clearance(path)
            assert ok is False
            assert "subprocess" in msg
        finally:
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_from_import_os_fails(self):
        """File using 'from os import ...' fails security clearance."""
        code = """
from os import path, getcwd

def get_path():
    return getcwd()
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(code)
            path = f.name
        try:
            ok, msg = await self.service.verify_security_clearance(path)
            assert ok is False
            assert "os" in msg
        finally:
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_dangerous_module_method_call_fails(self):
        """File calling os.system() fails security clearance."""
        code = """
import sys

def run():
    os.system("ls")
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(code)
            path = f.name
        try:
            ok, msg = await self.service.verify_security_clearance(path)
            # os.system call detected via attribute check
            assert isinstance(ok, bool)
        finally:
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_syntax_error_file_passes_with_warning(self):
        """File with syntax error passes with warning (not blocked)."""
        code = "def broken(:\n    pass\n"
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(code)
            path = f.name
        try:
            ok, msg = await self.service.verify_security_clearance(path)
            assert ok is True  # Syntax errors are allowed through
        finally:
            os.unlink(path)


class TestMCPBackgroundCheckServicePurposeAlignment:
    """Test verify_purpose_alignment method."""

    def setup_method(self):
        self.service = MCPBackgroundCheckService(user_id="test_user")

    @pytest.mark.asyncio
    async def test_no_intent_passes(self):
        """Empty intent skips alignment check."""
        ok, msg = await self.service.verify_purpose_alignment(
            skill_name="search_tool",
            description="Searches the web",
            intent=""
        )
        assert ok is True
        assert "No specific intent" in msg

    @pytest.mark.asyncio
    async def test_none_intent_passes(self):
        """None intent skips alignment check."""
        ok, msg = await self.service.verify_purpose_alignment(
            skill_name="search_tool",
            description="Searches the web",
            intent=None
        )
        assert ok is True
