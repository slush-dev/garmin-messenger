"""Tests for the device-metadata command."""

from __future__ import annotations

from uuid import UUID

from garmin_messenger.models import MessageDeviceMetadataV2

from garmin_messenger_cli.main import cli

from .conftest import CONV_ID, MODULE, MSG_ID


class TestDeviceMetadataHappyPath:
    """device-metadata shows satellite device info for messages."""

    def test_device_text(
        self, cli_runner, mock_auth_class, mock_api_class, sample_device_metadata_result
    ):
        _, api = mock_api_class
        api.get_message_device_metadata.return_value = sample_device_metadata_result
        result = cli_runner.invoke(cli, ["device-metadata", CONV_ID, MSG_ID])
        assert result.exit_code == 0
        assert "inReach Mini 2" in result.output

    def test_imei_shown(
        self, cli_runner, mock_auth_class, mock_api_class, sample_device_metadata_result
    ):
        _, api = mock_api_class
        api.get_message_device_metadata.return_value = sample_device_metadata_result
        result = cli_runner.invoke(cli, ["device-metadata", CONV_ID, MSG_ID])
        assert "300234063904190" in result.output

    def test_mtmsn_shown(
        self, cli_runner, mock_auth_class, mock_api_class, sample_device_metadata_result
    ):
        _, api = mock_api_class
        api.get_message_device_metadata.return_value = sample_device_metadata_result
        result = cli_runner.invoke(cli, ["device-metadata", CONV_ID, MSG_ID])
        assert "42" in result.output

    def test_message_id_shown(
        self, cli_runner, mock_auth_class, mock_api_class, sample_device_metadata_result
    ):
        _, api = mock_api_class
        api.get_message_device_metadata.return_value = sample_device_metadata_result
        result = cli_runner.invoke(cli, ["device-metadata", CONV_ID, MSG_ID])
        assert MSG_ID in result.output

    def test_multiple_message_ids(
        self, cli_runner, mock_auth_class, mock_api_class, sample_device_metadata_result
    ):
        _, api = mock_api_class
        api.get_message_device_metadata.return_value = sample_device_metadata_result
        second_id = "22222222-3333-4444-5555-666666666666"
        result = cli_runner.invoke(cli, ["device-metadata", CONV_ID, MSG_ID, second_id])
        assert result.exit_code == 0
        # Should have called with 2 IDs
        call_args = api.get_message_device_metadata.call_args[0][0]
        assert len(call_args) == 2

    def test_api_called_with_correct_ids(
        self, cli_runner, mock_auth_class, mock_api_class, sample_device_metadata_result
    ):
        _, api = mock_api_class
        api.get_message_device_metadata.return_value = sample_device_metadata_result
        result = cli_runner.invoke(cli, ["device-metadata", CONV_ID, MSG_ID])
        assert result.exit_code == 0
        call_args = api.get_message_device_metadata.call_args[0][0]
        assert len(call_args) == 1
        assert str(call_args[0].messageId) == MSG_ID
        assert str(call_args[0].conversationId) == CONV_ID


class TestDeviceMetadataNoSatelliteInfo:
    """API returns entry but deviceMessageMetadata is None (non-satellite message)."""

    def test_no_satellite_label(
        self, cli_runner, mock_auth_class, mock_api_class,
        sample_device_metadata_no_device_result,
    ):
        _, api = mock_api_class
        api.get_message_device_metadata.return_value = sample_device_metadata_no_device_result
        result = cli_runner.invoke(cli, ["device-metadata", CONV_ID, MSG_ID])
        assert result.exit_code == 0
        assert "no satellite device info" in result.output

    def test_shows_message_id_from_response(
        self, cli_runner, mock_auth_class, mock_api_class,
        sample_device_metadata_no_device_result,
    ):
        _, api = mock_api_class
        api.get_message_device_metadata.return_value = sample_device_metadata_no_device_result
        result = cli_runner.invoke(cli, ["device-metadata", CONV_ID, MSG_ID])
        assert MSG_ID in result.output

    def test_does_not_show_device_fields(
        self, cli_runner, mock_auth_class, mock_api_class,
        sample_device_metadata_no_device_result,
    ):
        _, api = mock_api_class
        api.get_message_device_metadata.return_value = sample_device_metadata_no_device_result
        result = cli_runner.invoke(cli, ["device-metadata", CONV_ID, MSG_ID])
        assert "Device:" not in result.output
        assert "IMEI:" not in result.output

    def test_falls_back_to_cli_arg_when_no_metadata(
        self, cli_runner, mock_auth_class, mock_api_class
    ):
        """When deviceMetadata is entirely None, fall back to CLI argument."""
        _, api = mock_api_class
        api.get_message_device_metadata.return_value = [MessageDeviceMetadataV2()]
        result = cli_runner.invoke(cli, ["device-metadata", CONV_ID, MSG_ID])
        assert MSG_ID in result.output
        assert "no satellite device info" in result.output


class TestDeviceMetadataEmpty:
    """No metadata returned at all."""

    def test_empty_message(
        self, cli_runner, mock_auth_class, mock_api_class
    ):
        _, api = mock_api_class
        api.get_message_device_metadata.return_value = []
        result = cli_runner.invoke(cli, ["device-metadata", CONV_ID, MSG_ID])
        assert "No device metadata found" in result.output
        assert result.exit_code == 0


class TestDeviceMetadataAuth:
    """Auth failures."""

    def test_no_session_exits(self, cli_runner, mock_auth_class):
        _, instance = mock_auth_class
        instance.resume.side_effect = RuntimeError("No saved session")
        result = cli_runner.invoke(cli, ["device-metadata", CONV_ID, MSG_ID])
        assert result.exit_code == 1
        assert "Run 'garmin-messenger login'" in result.stderr


class TestDeviceMetadataHelp:
    def test_help(self, cli_runner):
        result = cli_runner.invoke(cli, ["device-metadata", "--help"])
        assert result.exit_code == 0
        assert "satellite device metadata" in result.output


class TestDeviceMetadataMissingArgs:
    def test_no_message_id(self, cli_runner, mock_auth_class):
        result = cli_runner.invoke(cli, ["device-metadata", CONV_ID])
        assert result.exit_code != 0

    def test_no_args(self, cli_runner, mock_auth_class):
        result = cli_runner.invoke(cli, ["device-metadata"])
        assert result.exit_code != 0


class TestDeviceMetadataApiError:
    def test_api_exception(self, cli_runner, mock_auth_class, mock_api_class):
        _, api = mock_api_class
        api.get_message_device_metadata.side_effect = RuntimeError("API error")
        result = cli_runner.invoke(cli, ["device-metadata", CONV_ID, MSG_ID])
        assert result.exit_code != 0
