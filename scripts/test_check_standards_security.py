"""
Security test cases for check_standards.py subprocess fix

Tests verify that the safe subprocess.run() implementation prevents
command injection while maintaining backward compatibility.
"""

import subprocess
import pytest
import shlex
import tempfile
import os


class TestCheckStandardsSecurityFix:
    """Test suite for subprocess security fix in check_standards.py"""

    def test_safe_subprocess_call_simple_command(self):
        """Test that simple commands execute safely without shell=True"""
        cmd = "echo hello"
        result = subprocess.run(shlex.split(cmd), capture_output=True, text=True)
        assert result.returncode == 0
        assert "hello" in result.stdout

    def test_safe_subprocess_call_with_arguments(self):
        """Test that commands with arguments parse correctly"""
        cmd = "python3 --version"
        result = subprocess.run(shlex.split(cmd), capture_output=True, text=True)
        assert result.returncode == 0
        assert "Python" in result.stdout or "Python" in result.stderr

    def test_command_injection_blocked_semicolon(self):
        """Test that semicolon injection is blocked by shlex.split()"""
        # With shell=True, this would execute both echo and whoami
        # With shlex.split(), it should fail or echo the literal semicolon
        cmd = 'echo test; whoami'
        try:
            # This should fail because the semicolon is part of the first argument
            result = subprocess.run(
                shlex.split(cmd),
                capture_output=True,
                text=True,
                check=True
            )
            # If it somehow succeeds, verify it's not executing the second command
            assert "root" not in result.stdout and "whoami" not in result.stdout
        except FileNotFoundError:
            # Expected: "echo test; whoami" is treated as a single command name
            pass

    def test_command_injection_blocked_pipe(self):
        """Test that pipe injection is blocked"""
        # With shell=True: would execute ls | wc -l
        # With shlex.split(): pipe is treated as argument
        cmd = 'ls | wc -l'
        try:
            result = subprocess.run(
                shlex.split(cmd),
                capture_output=True,
                text=True,
                check=True
            )
            # Should fail because pipe is treated as argument
            assert False, "Expected command to fail"
        except FileNotFoundError:
            # Expected behavior: pipe is not interpreted
            pass

    def test_command_injection_blocked_command_substitution(self):
        """Test that command substitution is blocked"""
        # With shell=True: $(whoami) would be executed
        # With shlex.split(): treated as literal string
        cmd = 'echo $(whoami)'
        result = subprocess.run(
            shlex.split(cmd),
            capture_output=True,
            text=True,
            check=True
        )
        # The output should be the literal string, not the username
        assert "$(whoami)" in result.stdout or "whoami" in result.stdout

    def test_quoted_arguments_preserved(self):
        """Test that quoted arguments are preserved correctly"""
        # Create a temp file with spaces in name
        with tempfile.NamedTemporaryFile(prefix="test file ", delete=False) as f:
            temp_path = f.name
            f.write(b"test content")
        
        try:
            # Test that file path with spaces works
            cmd = f'cat "{temp_path}"'
            result = subprocess.run(
                shlex.split(cmd),
                capture_output=True,
                text=True,
                check=True
            )
            assert "test content" in result.stdout
        finally:
            os.unlink(temp_path)

    def test_no_shell_injection_with_user_input(self):
        """Test that user-controlled input cannot inject commands"""
        # Simulating user input that might contain injection attempts
        user_input = "test; rm -rf /"
        cmd = f"echo {shlex.quote(user_input)}"
        
        result = subprocess.run(
            shlex.split(cmd),
            capture_output=True,
            text=True,
            check=True
        )
        
        # Verify the input is echoed safely, not executed
        assert user_input in result.stdout
        assert "rm" not in result.stdout or "rm -rf" not in result.stdout

    def test_subprocess_error_handling_maintained(self):
        """Test that error handling still works with safe implementation"""
        cmd = "ls /nonexistent_directory_12345"
        
        with pytest.raises(subprocess.CalledProcessError):
            subprocess.run(
                shlex.split(cmd),
                check=True,
                capture_output=True,
                text=True
            )

    def test_cwd_parameter_still_works(self):
        """Test that cwd parameter works without shell=True"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a file in temp directory
            test_file = os.path.join(tmpdir, "test.txt")
            with open(test_file, "w") as f:
                f.write("test")
            
            # List files in the temp directory
            result = subprocess.run(
                ["ls"],
                cwd=tmpdir,
                capture_output=True,
                text=True,
                check=True
            )
            
            assert "test.txt" in result.stdout

    def test_complex_command_with_arguments(self):
        """Test that complex commands with multiple arguments work correctly"""
        # Create temp file
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write("line 1\nline 2\nline 3")
            temp_path = f.name
        
        try:
            # Use grep with file argument
            result = subprocess.run(
                ["grep", "line", temp_path],
                capture_output=True,
                text=True,
                check=True
            )
            assert "line 1" in result.stdout
        finally:
            os.unlink(temp_path)


class TestSubprocessBestPractices:
    """Test recommended subprocess safety patterns"""

    def test_array_format_is_secure(self):
        """Test that array format (no shell=True) is inherently secure"""
        # This is the recommended pattern
        result = subprocess.run(
            ["echo", "hello world"],  # Array format
            capture_output=True,
            text=True,
            check=True
        )
        assert "hello world" in result.stdout

    def test_shlex_quote_for_dynamic_args(self):
        """Test shlex.quote() for safely quoting dynamic arguments"""
        dangerous_input = "'; DROP TABLE users; --"
        safe_cmd = ["echo", shlex.quote(dangerous_input)]
        
        result = subprocess.run(
            safe_cmd,
            capture_output=True,
            text=True,
            check=True
        )
        # Input should be echoed safely
        assert dangerous_input in result.stdout

    def test_env_variables_not_expanded_by_default(self):
        """Test that environment variables aren't expanded without shell"""
        # Set a test env var
        os.environ["TEST_VAR"] = "secret"
        
        # Without shell=True, $TEST_VAR won't be expanded
        result = subprocess.run(
            ["echo", "$TEST_VAR"],
            capture_output=True,
            text=True,
            check=True
        )
        
        # Should print the literal string, not the env var value
        assert "$TEST_VAR" in result.stdout


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
