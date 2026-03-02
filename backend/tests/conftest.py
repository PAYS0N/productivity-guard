"""Shared pytest fixtures for productivity-guard backend tests.

The most critical fixture here is `set_config_env`, which writes a temporary
YAML config and sets PG_CONFIG *before* any test module imports main.py.
main.py runs `open(CONFIG_PATH)` at module level, so this must be in place
before the first import of `main`.
"""

import os
import yaml
import pytest

from tests.helpers.fake_config import FAKE_CONFIG


@pytest.fixture(scope="session", autouse=True)
def set_config_env(tmp_path_factory):
    """Write a temporary test config and point PG_CONFIG at it.

    This fixture is autouse + session-scoped, so it runs once before any test
    in the session and is guaranteed to be active before main.py is imported.
    """
    config_dir = tmp_path_factory.mktemp("config")
    config_file = config_dir / "config.yaml"
    config_file.write_text(yaml.dump(FAKE_CONFIG))
    os.environ["PG_CONFIG"] = str(config_file)
    yield
    # Clean up
    os.environ.pop("PG_CONFIG", None)
