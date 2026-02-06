"""Tests for the network command."""

from __future__ import annotations

from garmin_messenger.models import NetworkPropertiesResponse

from garmin_messenger_cli.main import cli


class TestNetworkHappyPath:
    """network shows network properties."""

    def test_data_constrained(
        self, cli_runner, mock_auth_class, mock_api_class, sample_network_result
    ):
        _, api = mock_api_class
        api.get_network_properties.return_value = sample_network_result
        result = cli_runner.invoke(cli, ["network"])
        assert "Data constrained: False" in result.output

    def test_premium_messaging(
        self, cli_runner, mock_auth_class, mock_api_class, sample_network_result
    ):
        _, api = mock_api_class
        api.get_network_properties.return_value = sample_network_result
        result = cli_runner.invoke(cli, ["network"])
        assert "Premium messaging: True" in result.output

    def test_exit_code_zero(
        self, cli_runner, mock_auth_class, mock_api_class, sample_network_result
    ):
        _, api = mock_api_class
        api.get_network_properties.return_value = sample_network_result
        result = cli_runner.invoke(cli, ["network"])
        assert result.exit_code == 0

    def test_all_true(self, cli_runner, mock_auth_class, mock_api_class):
        _, api = mock_api_class
        api.get_network_properties.return_value = NetworkPropertiesResponse(
            dataConstrained=True, enablesPremiumMessaging=True,
        )
        result = cli_runner.invoke(cli, ["network"])
        assert "Data constrained: True" in result.output
        assert "Premium messaging: True" in result.output

    def test_all_false(self, cli_runner, mock_auth_class, mock_api_class):
        _, api = mock_api_class
        api.get_network_properties.return_value = NetworkPropertiesResponse()
        result = cli_runner.invoke(cli, ["network"])
        assert "Data constrained: False" in result.output
        assert "Premium messaging: False" in result.output


class TestNetworkAuth:
    """Auth failures."""

    def test_no_session_exits(self, cli_runner, mock_auth_class):
        _, instance = mock_auth_class
        instance.resume.side_effect = RuntimeError("No saved session")
        result = cli_runner.invoke(cli, ["network"])
        assert result.exit_code == 1
        assert "Run 'garmin-messenger login'" in result.stderr


class TestNetworkHelp:
    def test_help(self, cli_runner):
        result = cli_runner.invoke(cli, ["network", "--help"])
        assert result.exit_code == 0
        assert "Show network properties" in result.output


class TestNetworkApiError:
    def test_api_exception(self, cli_runner, mock_auth_class, mock_api_class):
        _, api = mock_api_class
        api.get_network_properties.side_effect = RuntimeError("API error")
        result = cli_runner.invoke(cli, ["network"])
        assert result.exit_code != 0
