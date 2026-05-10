"""Code validator tool: Syntax checking and hallucination detection."""

import ast
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)


class CodeValidator:
    """Validates generated code and detects hallucinations."""
    
    @staticmethod
    def validate_python_syntax(code: str) -> tuple[bool, Optional[str]]:
        """
        Validate Python code syntax.
        
        Args:
            code: Python code to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            ast.parse(code)
            return (True, None)
        except SyntaxError as e:
            error_msg = f"Syntax error at line {e.lineno}: {e.msg}"
            logger.debug(f"Python syntax error: {error_msg}")
            return (False, error_msg)
        except Exception as e:
            error_msg = f"Parse error: {str(e)}"
            logger.debug(f"Python parse error: {error_msg}")
            return (False, error_msg)
    
    @staticmethod
    def validate_javascript_syntax(code: str) -> tuple[bool, Optional[str]]:
        """
        Basic JavaScript syntax validation (regex-based).
        
        Full validation would require a JS parser.
        
        Args:
            code: JavaScript code to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        issues = []
        
        # Check for unmatched braces
        brace_count = code.count("{") - code.count("}")
        paren_count = code.count("(") - code.count(")")
        bracket_count = code.count("[") - code.count("]")
        
        if brace_count != 0:
            issues.append(f"Unmatched braces (diff: {brace_count})")
        if paren_count != 0:
            issues.append(f"Unmatched parentheses (diff: {paren_count})")
        if bracket_count != 0:
            issues.append(f"Unmatched brackets (diff: {bracket_count})")
        
        # Check for missing semicolons on function declarations (loose check)
        function_pattern = r'function\s+\w+\s*\([^)]*\)\s*\{'
        for match in re.finditer(function_pattern, code):
            # Just a basic check, JS can work without semicolons
            pass
        
        if issues:
            error_msg = "; ".join(issues)
            logger.debug(f"JavaScript issues: {error_msg}")
            return (False, error_msg)
        
        return (True, None)
    
    @staticmethod
    def detect_hallucinations(code: str, language: str) -> list[str]:
        """
        Detect common hallucinations in generated test code.
        
        Args:
            code: Generated test code
            language: Programming language (python, javascript, etc.)
            
        Returns:
            List of detected hallucination issues
        """
        issues = []
        
        if language == "python":
            # Check for imports that might not exist
            import_lines = [
                line.strip() for line in code.split("\n")
                if line.strip().startswith(("import ", "from "))
            ]
            
            # Known suspicious patterns
            suspicious_imports = {
                "pytest": [],
                "unittest": [],
                "mock": ["unittest.mock"],
                "hypothesis": [],
            }
            
            for imp_line in import_lines:
                # Check if mock is imported but unittest.mock is not
                if "mock" in imp_line.lower() and "unittest.mock" not in imp_line:
                    if "from mock import" in imp_line or "import mock" in imp_line:
                        if "unittest.mock" not in code and "from unittest.mock" not in code:
                            issues.append("Uses 'mock' library but doesn't import from unittest.mock")
            
            # Check for references to fixtures/functions that might not be defined
            if "@pytest.fixture" in code and "pytest" not in code and "import pytest" not in code:
                issues.append("Uses pytest fixtures without importing pytest")
            
            if "Mock(" in code and "Mock" not in import_lines[0] if import_lines else True:
                mock_imported = any("Mock" in line for line in import_lines)
                if not mock_imported:
                    issues.append("Uses Mock() without proper import")
            
            # Check for undefined test functions
            test_functions = re.findall(r"def (test_\w+)\(", code)
            if not test_functions:
                issues.append("No test functions defined (should start with 'test_')")
            
            # Check for overly generic assertions
            assertions = re.findall(r"assert\s+(\w+)", code)
            if assertions and all(a in ["True", "False"] for a in assertions):
                issues.append("All assertions are trivial (True/False)")
        
        elif language == "javascript":
            # Check for test framework functions without imports
            if ("describe(" in code or "it(" in code) and ("mocha" not in code and "jest" not in code):
                if "describe" not in code.split("function"):
                    issues.append("Uses describe/it without importing test framework (mocha/jest)")
            
            if "expect(" in code and "expect" not in code.split("function"):
                if "chai" not in code and "jest" not in code:
                    issues.append("Uses expect() without importing assertion library")
        
        return issues
    
    @staticmethod
    def validate_and_score(
        code: str,
        language: str = "python"
    ) -> dict:
        """
        Comprehensive validation and scoring of generated code.
        
        Args:
            code: Code to validate
            language: Programming language
            
        Returns:
            Dict with validation results:
            {
                "is_valid": bool,
                "syntax_error": Optional[str],
                "hallucinations": list[str],
                "confidence_penalty": float (0.0-1.0, amount to reduce from 1.0),
                "warnings": list[str]
            }
        """
        result = {
            "is_valid": True,
            "syntax_error": None,
            "hallucinations": [],
            "confidence_penalty": 0.0,
            "warnings": []
        }
        
        # Syntax validation
        if language == "python":
            is_valid, error = CodeValidator.validate_python_syntax(code)
        elif language == "javascript":
            is_valid, error = CodeValidator.validate_javascript_syntax(code)
        else:
            # Unknown language, just return
            result["warnings"].append(f"Unknown language: {language}")
            return result
        
        if not is_valid:
            result["is_valid"] = False
            result["syntax_error"] = error
            result["confidence_penalty"] += 0.5
        
        # Hallucination detection
        hallucinations = CodeValidator.detect_hallucinations(code, language)
        if hallucinations:
            result["hallucinations"] = hallucinations
            result["confidence_penalty"] += min(0.3, len(hallucinations) * 0.1)
        
        # Additional checks
        code_length = len(code.strip())
        if code_length < 50:
            result["warnings"].append("Code is very short (might be incomplete)")
            result["confidence_penalty"] += 0.1
        
        # Code quality checks
        comment_ratio = code.count("#") / max(code.count("\n"), 1) if language == "python" else 0
        if comment_ratio < 0.1 and code_length > 200:
            result["warnings"].append("Very few comments for code length")
        
        return result


async def validate_code(
    code: str,
    language: str = "python"
) -> dict:
    """
    Async wrapper for code validation.
    
    Use in LangGraph nodes for test code validation.
    
    Args:
        code: Code to validate
        language: Programming language
        
    Returns:
        Validation result dict
    """
    result = CodeValidator.validate_and_score(code, language)
    
    severity = "error" if result["syntax_error"] else "warning" if result["hallucinations"] else "info"
    logger.log(
        logging.ERROR if severity == "error" else logging.WARNING if severity == "warning" else logging.INFO,
        f"Code validation ({language}): {severity} - "
        f"valid={result['is_valid']}, hallucinations={len(result['hallucinations'])}, "
        f"penalty={result['confidence_penalty']:.2f}"
    )
    
    return result
