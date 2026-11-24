import importlib.metadata

import resume_engine


def test_version_matches_installed_metadata() -> None:
    # Guards against bumping one version string and forgetting the other.
    assert resume_engine.__version__ == importlib.metadata.version("resume-engine")
