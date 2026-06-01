"""
Tests for the CLI interface (isrt/cli.py).
"""

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from isrt.cli import cli
from isrt.rcon import AuthenticationError
from isrt.rcon import ConnectionError as RCONConnectionError


@pytest.fixture()
def runner():
    return CliRunner(mix_stderr=False)


@pytest.fixture(autouse=True)
def isolated_config(tmp_path):
    """Redirect config file so tests don't touch the real ~/.isrt directory."""
    import isrt.config as cfg

    config_dir = tmp_path / ".isrt"
    config_file = config_dir / "config.json"
    with patch.object(cfg, "CONFIG_DIR", config_dir), patch.object(
        cfg, "CONFIG_FILE", config_file
    ):
        yield


# ---------------------------------------------------------------------------
# exec command
# ---------------------------------------------------------------------------


class TestExecCommand:
    def _mock_client(self, response="OK"):
        client = MagicMock()
        client.__enter__ = MagicMock(return_value=client)
        client.__exit__ = MagicMock(return_value=False)
        client.execute.return_value = response
        client.connected = True
        return client

    def test_exec_prints_response(self, runner):
        mock_client = self._mock_client("Player1")
        with patch("isrt.cli._make_client", return_value=mock_client):
            result = runner.invoke(
                cli,
                ["exec", "--host", "127.0.0.1", "--password", "pw", "AdminListPlayers"],
            )
        assert result.exit_code == 0
        assert "Player1" in result.output

    def test_exec_connection_error_exits_nonzero(self, runner):
        with patch(
            "isrt.cli._make_client",
            side_effect=SystemExit(1),
        ):
            result = runner.invoke(
                cli,
                ["exec", "--host", "127.0.0.1", "--password", "pw", "AdminListPlayers"],
            )
        assert result.exit_code != 0

    def test_exec_requires_command(self, runner):
        result = runner.invoke(cli, ["exec", "--host", "127.0.0.1", "--password", "pw"])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# profile subcommand
# ---------------------------------------------------------------------------


class TestProfileCommands:
    def test_profile_save_and_list(self, runner):
        result = runner.invoke(
            cli,
            [
                "profile",
                "save",
                "test",
                "--host",
                "1.2.3.4",
                "--port",
                "27015",
                "--password",
                "pw",
            ],
        )
        assert result.exit_code == 0
        assert "saved" in result.output

        result = runner.invoke(cli, ["profile", "list"])
        assert result.exit_code == 0
        assert "test" in result.output
        assert "1.2.3.4" in result.output

    def test_profile_list_empty(self, runner):
        result = runner.invoke(cli, ["profile", "list"])
        assert result.exit_code == 0
        assert "No profiles" in result.output

    def test_profile_delete_existing(self, runner):
        runner.invoke(
            cli,
            ["profile", "save", "del_me", "--host", "1.1.1.1", "--password", "pw"],
        )
        result = runner.invoke(cli, ["profile", "delete", "del_me"])
        assert result.exit_code == 0
        assert "deleted" in result.output

    def test_profile_delete_nonexistent(self, runner):
        result = runner.invoke(cli, ["profile", "delete", "ghost"])
        assert result.exit_code != 0

    def test_profile_default_command(self, runner):
        runner.invoke(
            cli,
            ["profile", "save", "main", "--host", "1.1.1.1", "--password", "pw"],
        )
        result = runner.invoke(cli, ["profile", "default", "main"])
        assert result.exit_code == 0

    def test_profile_default_nonexistent_fails(self, runner):
        result = runner.invoke(cli, ["profile", "default", "ghost"])
        assert result.exit_code != 0

    def test_profile_set_default_flag(self, runner):
        result = runner.invoke(
            cli,
            [
                "profile",
                "save",
                "flagtest",
                "--host",
                "5.5.5.5",
                "--password",
                "pw",
                "--set-default",
            ],
        )
        assert result.exit_code == 0

        import isrt.config as cfg

        assert cfg.get_default_profile() == "flagtest"


# ---------------------------------------------------------------------------
# players shortcut
# ---------------------------------------------------------------------------


class TestPlayersCommand:
    def test_players_shows_output(self, runner):
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.execute.return_value = "Player1\nPlayer2"

        with patch("isrt.cli._make_client", return_value=mock_client):
            result = runner.invoke(
                cli, ["players", "--host", "127.0.0.1", "--password", "pw"]
            )
        assert result.exit_code == 0
        assert "Player1" in result.output


# ---------------------------------------------------------------------------
# broadcast shortcut
# ---------------------------------------------------------------------------


class TestBroadcastCommand:
    def test_broadcast_sends_command(self, runner):
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.execute.return_value = ""

        with patch("isrt.cli._make_client", return_value=mock_client):
            result = runner.invoke(
                cli,
                ["broadcast", "--host", "127.0.0.1", "--password", "pw", "Hello", "all"],
            )
        assert result.exit_code == 0
        mock_client.execute.assert_called_once_with("AdminBroadcast Hello all")


# ---------------------------------------------------------------------------
# map shortcut
# ---------------------------------------------------------------------------


class TestMapCommand:
    def test_map_change(self, runner):
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.execute.return_value = ""

        with patch("isrt.cli._make_client", return_value=mock_client):
            result = runner.invoke(
                cli,
                ["map", "--host", "127.0.0.1", "--password", "pw", "PowerPlant"],
            )
        assert result.exit_code == 0
        mock_client.execute.assert_called_once_with("AdminChangeLevel PowerPlant")


# ---------------------------------------------------------------------------
# kick / ban shortcuts
# ---------------------------------------------------------------------------


class TestKickBanCommands:
    def _mock_client(self):
        c = MagicMock()
        c.__enter__ = MagicMock(return_value=c)
        c.__exit__ = MagicMock(return_value=False)
        c.execute.return_value = ""
        return c

    def test_kick_sends_command(self, runner):
        mock_client = self._mock_client()
        with patch("isrt.cli._make_client", return_value=mock_client):
            result = runner.invoke(
                cli,
                ["kick", "--host", "127.0.0.1", "--password", "pw", "BadPlayer", "cheating"],
            )
        assert result.exit_code == 0
        mock_client.execute.assert_called_once_with("AdminKick BadPlayer cheating")

    def test_ban_sends_command(self, runner):
        mock_client = self._mock_client()
        with patch("isrt.cli._make_client", return_value=mock_client):
            result = runner.invoke(
                cli,
                ["ban", "--host", "127.0.0.1", "--password", "pw", "HaxPlayer", "hacking"],
            )
        assert result.exit_code == 0
        mock_client.execute.assert_called_once_with("AdminBan HaxPlayer hacking 0")


# ---------------------------------------------------------------------------
# --version flag
# ---------------------------------------------------------------------------


class TestVersionFlag:
    def test_version_flag(self, runner):
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "1.0.0" in result.output
