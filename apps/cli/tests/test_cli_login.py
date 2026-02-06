"""Tests for the login command."""

from __future__ import annotations

from garmin_messenger_cli.main import cli

from .conftest import INSTANCE_ID


class TestLoginHappyPath:
    """login with --phone and interactive prompt."""

    def test_phone_option(self, cli_runner, mock_auth_class):
        _, instance = mock_auth_class
        result = cli_runner.invoke(
            cli, ["login", "--phone", "+15551234567"], input="123456\n"
        )
        assert result.exit_code == 0
        instance.request_otp.assert_called_once_with(
            "+15551234567", device_name="garmin-messenger"
        )
        instance.confirm_otp.assert_called_once()

    def test_interactive_prompt(self, cli_runner, mock_auth_class):
        _, instance = mock_auth_class
        result = cli_runner.invoke(
            cli, ["login"], input="+15559999999\n123456\n"
        )
        assert result.exit_code == 0
        instance.request_otp.assert_called_once_with(
            "+15559999999", device_name="garmin-messenger"
        )
        instance.confirm_otp.assert_called_once()

    def test_custom_device_name(self, cli_runner, mock_auth_class):
        _, instance = mock_auth_class
        result = cli_runner.invoke(
            cli,
            ["login", "--phone", "+15551234567", "--device-name", "my-device"],
            input="123456\n",
        )
        assert result.exit_code == 0
        instance.request_otp.assert_called_once_with(
            "+15551234567", device_name="my-device"
        )

    def test_outputs_instance_id(self, cli_runner, mock_auth_class):
        _, instance = mock_auth_class
        result = cli_runner.invoke(
            cli, ["login", "--phone", "+15551234567"], input="123456\n"
        )
        assert INSTANCE_ID in result.output

    def test_outputs_session_saved(self, cli_runner, mock_auth_class):
        result = cli_runner.invoke(
            cli, ["login", "--phone", "+15551234567"], input="123456\n"
        )
        assert "Session saved" in result.output

    def test_passes_session_dir(self, cli_runner, mock_auth_class):
        MockCls, _ = mock_auth_class
        cli_runner.invoke(
            cli,
            ["--session-dir", "/custom/dir", "login", "--phone", "+1"],
            input="123456\n",
        )
        MockCls.assert_called_once_with(session_dir="/custom/dir")

    def test_confirm_receives_otp_code(self, cli_runner, mock_auth_class):
        _, instance = mock_auth_class
        result = cli_runner.invoke(
            cli, ["login", "--phone", "+15551234567"], input="654321\n"
        )
        assert result.exit_code == 0
        args = instance.confirm_otp.call_args
        assert args[0][1] == "654321"


class TestLoginAuthFailure:
    """login fails when no access_token or exception."""

    def test_no_access_token(self, cli_runner, mock_auth_class):
        _, instance = mock_auth_class
        instance.access_token = None
        result = cli_runner.invoke(
            cli, ["login", "--phone", "+15551234567"], input="123456\n"
        )
        assert result.exit_code == 1
        assert "Authentication failed" in result.stderr

    def test_request_otp_exception(self, cli_runner, mock_auth_class):
        _, instance = mock_auth_class
        instance.request_otp.side_effect = RuntimeError("SMS send failed")
        result = cli_runner.invoke(
            cli, ["login", "--phone", "+15551234567"], input="123456\n"
        )
        assert result.exit_code != 0


class TestLoginOptions:
    """login --help, verbose, custom session-dir."""

    def test_help(self, cli_runner):
        result = cli_runner.invoke(cli, ["login", "--help"])
        assert result.exit_code == 0
        assert "Authenticate via SMS OTP" in result.output

    def test_verbose(self, cli_runner, mock_auth_class):
        result = cli_runner.invoke(
            cli, ["--verbose", "login", "--phone", "+15551234567"],
            input="123456\n",
        )
        assert result.exit_code == 0

    def test_custom_session_dir(self, cli_runner, mock_auth_class):
        MockCls, _ = mock_auth_class
        cli_runner.invoke(
            cli,
            ["--session-dir", "/tmp/sess", "login", "--phone", "+1"],
            input="123456\n",
        )
        MockCls.assert_called_once_with(session_dir="/tmp/sess")
