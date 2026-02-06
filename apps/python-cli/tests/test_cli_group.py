"""Tests for the root CLI group, _configure_logging, and _get_auth."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest

from garmin_messenger_cli.main import _configure_logging, _get_auth, cli

MODULE = "garmin_messenger_cli.main"


class TestConfigureLogging:
    """_configure_logging sets the correct log level."""

    def test_verbose_sets_debug(self):
        with patch("logging.basicConfig") as mock_bc:
            _configure_logging(verbose=True)
            mock_bc.assert_called_once()
            assert mock_bc.call_args.kwargs["level"] == logging.DEBUG

    def test_default_sets_warning(self):
        with patch("logging.basicConfig") as mock_bc:
            _configure_logging(verbose=False)
            mock_bc.assert_called_once()
            assert mock_bc.call_args.kwargs["level"] == logging.WARNING


class TestGetAuth:
    """_get_auth resumes a session or exits with helpful message."""

    def test_happy_path(self, tmp_path, mock_auth_class):
        MockCls, instance = mock_auth_class
        auth = _get_auth(str(tmp_path))
        MockCls.assert_called_once_with(session_dir=str(tmp_path))
        instance.resume.assert_called_once()
        assert auth is instance

    def test_session_dir_passthrough(self, mock_auth_class):
        MockCls, _ = mock_auth_class
        _get_auth("/custom/session/dir")
        MockCls.assert_called_once_with(session_dir="/custom/session/dir")

    def test_resume_failure_exits(self, mock_auth_class):
        _, instance = mock_auth_class
        instance.resume.side_effect = RuntimeError("No saved session")
        with pytest.raises(SystemExit) as exc_info:
            _get_auth("/tmp/test")
        assert exc_info.value.code == 1


class TestCliGroup:
    """Root CLI group options and --help."""

    def test_help(self, cli_runner):
        result = cli_runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "Unofficial Garmin Messenger" in result.output

    def test_default_session_dir(self, cli_runner, mock_auth_class):
        """Invoking a subcommand without --session-dir uses the default."""
        MockCls, instance = mock_auth_class
        with patch(f"{MODULE}.HermesAPI") as MockAPI:
            api_inst = MagicMock()
            api_inst.__enter__ = MagicMock(return_value=api_inst)
            api_inst.__exit__ = MagicMock(return_value=False)
            api_inst.get_conversations.return_value = MagicMock(conversations=[])
            MockAPI.return_value = api_inst
            cli_runner.invoke(cli, ["conversations"])
        # _get_auth should have been called with the default path
        call_kwargs = MockCls.call_args
        assert ".garmin-messenger" in str(call_kwargs)

    def test_custom_session_dir(self, cli_runner, mock_auth_class):
        MockCls, instance = mock_auth_class
        with patch(f"{MODULE}.HermesAPI") as MockAPI:
            api_inst = MagicMock()
            api_inst.__enter__ = MagicMock(return_value=api_inst)
            api_inst.__exit__ = MagicMock(return_value=False)
            api_inst.get_conversations.return_value = MagicMock(conversations=[])
            MockAPI.return_value = api_inst
            cli_runner.invoke(
                cli, ["--session-dir", "/tmp/custom", "conversations"]
            )
        MockCls.assert_called_once_with(session_dir="/tmp/custom")

    def test_envvar_session_dir(self, cli_runner, mock_auth_class):
        MockCls, instance = mock_auth_class
        with patch(f"{MODULE}.HermesAPI") as MockAPI:
            api_inst = MagicMock()
            api_inst.__enter__ = MagicMock(return_value=api_inst)
            api_inst.__exit__ = MagicMock(return_value=False)
            api_inst.get_conversations.return_value = MagicMock(conversations=[])
            MockAPI.return_value = api_inst
            cli_runner.invoke(
                cli,
                ["conversations"],
                env={"GARMIN_SESSION_DIR": "/env/session"},
            )
        MockCls.assert_called_once_with(session_dir="/env/session")

    def test_verbose_flag(self, cli_runner, mock_auth_class):
        _, instance = mock_auth_class
        with patch(f"{MODULE}.HermesAPI") as MockAPI:
            api_inst = MagicMock()
            api_inst.__enter__ = MagicMock(return_value=api_inst)
            api_inst.__exit__ = MagicMock(return_value=False)
            api_inst.get_conversations.return_value = MagicMock(conversations=[])
            MockAPI.return_value = api_inst
            result = cli_runner.invoke(cli, ["--verbose", "conversations"])
        assert result.exit_code == 0
