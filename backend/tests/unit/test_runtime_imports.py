"""The app must import without dev-only packages.

The runtime image installs no dev dependencies, but the test environment
does, so a stray runtime import of a dev package passes every other test
and only fails in the container. This test re-imports the app in a fresh
interpreter where dev-only modules are blocked.
"""

import subprocess
import sys
import textwrap

# Top-level modules that exist only through the dev dependency group.
DEV_ONLY_MODULES = ("mypy_boto3_s3", "mypy_boto3_builtins", "pytest", "mypy", "ruff")


def test_app_imports_without_dev_dependencies() -> None:
    script = textwrap.dedent(
        f"""
        import importlib.abc, sys

        class BlockDevOnly(importlib.abc.MetaPathFinder):
            def find_spec(self, name, path=None, target=None):
                if name.split(".")[0] in {DEV_ONLY_MODULES!r}:
                    raise ModuleNotFoundError(f"dev-only module imported at runtime: {{name}}")
                return None

        sys.meta_path.insert(0, BlockDevOnly())
        import app.main  # noqa: F401
        """
    )
    result = subprocess.run(  # noqa: S603 - fixed interpreter, script built above
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr
