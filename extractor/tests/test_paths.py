import os
import sys

import pytest

SCRIPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import paths


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    """Cada teste decide seu próprio ambiente — herdar TIBIA_IDLE_DIR da
    máquina de quem roda faria a suíte passar aqui e falhar no CI."""
    monkeypatch.delenv(paths.TIBIA_IDLE.env_var, raising=False)
    monkeypatch.delenv(paths.CANARY.env_var, raising=False)


def test_flag_wins_over_env_var(monkeypatch, tmp_path):
    from_flag = tmp_path / "from-flag"
    from_env = tmp_path / "from-env"
    from_flag.mkdir()
    from_env.mkdir()
    monkeypatch.setenv(paths.TIBIA_IDLE.env_var, str(from_env))

    assert paths.TIBIA_IDLE.resolve(str(from_flag)) == str(from_flag)


def test_env_var_wins_over_sibling_fallback(monkeypatch, tmp_path):
    from_env = tmp_path / "from-env"
    from_env.mkdir()
    monkeypatch.setenv(paths.TIBIA_IDLE.env_var, str(from_env))

    assert paths.TIBIA_IDLE.resolve(None) == str(from_env)
    assert paths.TIBIA_IDLE.resolve(None) != paths.TIBIA_IDLE.sibling_default()


def test_sibling_fallback_when_nothing_is_set():
    assert paths.TIBIA_IDLE.resolve(None) == paths.TIBIA_IDLE.sibling_default()


def test_sibling_fallback_is_the_workspace_neighbour():
    """O default antigo apontava para <workspace>/tibia-idle/tibia-idle, uma
    pasta aninhada que nunca existiu. O irmão real é <workspace>/tibia-idle."""
    workspace = os.path.dirname(paths.REPO_DIR)
    assert paths.TIBIA_IDLE.sibling_default() == os.path.join(workspace, "tibia-idle")
    assert paths.CANARY.sibling_default() == os.path.join(workspace, "canary")


def test_missing_dir_names_the_path_the_env_var_and_the_flag(tmp_path):
    missing = str(tmp_path / "nao-existe")

    with pytest.raises(paths.MissingRepoError) as excinfo:
        paths.TIBIA_IDLE.require(missing)

    message = str(excinfo.value)
    assert missing in message
    assert "TIBIA_IDLE_DIR" in message
    assert "--tibia-idle-dir" in message


def test_missing_dir_error_is_a_message_not_a_traceback(tmp_path):
    """O ticket pede erro alto e legível: nunca um FileNotFoundError cru vindo
    de dentro do pipeline."""
    with pytest.raises(paths.MissingRepoError) as excinfo:
        paths.CANARY.require(str(tmp_path / "nao-existe"))

    assert not isinstance(excinfo.value, FileNotFoundError)
    assert "canary" in str(excinfo.value).lower()


def test_require_returns_the_dir_when_it_exists(tmp_path):
    existing = tmp_path / "canary"
    existing.mkdir()

    assert paths.CANARY.require(str(existing)) == str(existing)


def test_require_falls_back_through_the_same_precedence(monkeypatch, tmp_path):
    from_env = tmp_path / "canary-env"
    from_env.mkdir()
    monkeypatch.setenv(paths.CANARY.env_var, str(from_env))

    assert paths.CANARY.require(None) == str(from_env)


def test_no_windows_path_survives_in_the_repo():
    """`C:\\canary-3.2.1` era o default num fluxo Linux-only."""
    assert "C:" not in paths.CANARY.sibling_default()
