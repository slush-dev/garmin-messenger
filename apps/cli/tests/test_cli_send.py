"""Tests for the send command."""

from __future__ import annotations

import pytest

from garmin_messenger_cli.main import cli

from garmin_messenger.models import MediaType, UserLocation

from .conftest import CONV_ID, MODULE, MSG_ID, RECIPIENT_ID


class TestSendHappyPath:
    """send --to RECIPIENT --message TEXT."""

    def test_outputs_message_id(
        self, cli_runner, mock_auth_class, mock_api_class, sample_send_result
    ):
        _, api = mock_api_class
        api.send_message.return_value = sample_send_result
        result = cli_runner.invoke(
            cli, ["send", "--to", RECIPIENT_ID, "--message", "Hello"]
        )
        assert MSG_ID in result.output

    def test_outputs_conversation_id(
        self, cli_runner, mock_auth_class, mock_api_class, sample_send_result
    ):
        _, api = mock_api_class
        api.send_message.return_value = sample_send_result
        result = cli_runner.invoke(
            cli, ["send", "--to", RECIPIENT_ID, "--message", "Hello"]
        )
        assert CONV_ID in result.output

    def test_passes_recipient(
        self, cli_runner, mock_auth_class, mock_api_class, sample_send_result
    ):
        _, api = mock_api_class
        api.send_message.return_value = sample_send_result
        cli_runner.invoke(
            cli, ["send", "--to", RECIPIENT_ID, "--message", "Hello"]
        )
        call_kwargs = api.send_message.call_args
        assert call_kwargs.kwargs["to"] == [RECIPIENT_ID]

    def test_passes_message_body(
        self, cli_runner, mock_auth_class, mock_api_class, sample_send_result
    ):
        _, api = mock_api_class
        api.send_message.return_value = sample_send_result
        cli_runner.invoke(
            cli, ["send", "--to", RECIPIENT_ID, "--message", "Hello world"]
        )
        call_kwargs = api.send_message.call_args
        assert call_kwargs.kwargs["message_body"] == "Hello world"

    def test_recipient_wrapped_in_list(
        self, cli_runner, mock_auth_class, mock_api_class, sample_send_result
    ):
        _, api = mock_api_class
        api.send_message.return_value = sample_send_result
        cli_runner.invoke(
            cli, ["send", "--to", "+10000000000", "--message", "Hi"]
        )
        call_kwargs = api.send_message.call_args
        assert isinstance(call_kwargs.kwargs["to"], list)
        assert len(call_kwargs.kwargs["to"]) == 1

    def test_exit_code_zero(
        self, cli_runner, mock_auth_class, mock_api_class, sample_send_result
    ):
        _, api = mock_api_class
        api.send_message.return_value = sample_send_result
        result = cli_runner.invoke(
            cli, ["send", "--to", RECIPIENT_ID, "--message", "Hello"]
        )
        assert result.exit_code == 0


class TestSendOptions:
    """Missing required options, short flags, --help."""

    def test_missing_to(self, cli_runner, mock_auth_class):
        result = cli_runner.invoke(cli, ["send", "--message", "Hello"])
        assert result.exit_code == 2

    def test_missing_message(self, cli_runner, mock_auth_class):
        result = cli_runner.invoke(cli, ["send", "--to", RECIPIENT_ID])
        assert result.exit_code == 2

    def test_short_flag_t(
        self, cli_runner, mock_auth_class, mock_api_class, sample_send_result
    ):
        _, api = mock_api_class
        api.send_message.return_value = sample_send_result
        result = cli_runner.invoke(
            cli, ["send", "-t", RECIPIENT_ID, "-m", "Short flags"]
        )
        assert result.exit_code == 0

    def test_help(self, cli_runner):
        result = cli_runner.invoke(cli, ["send", "--help"])
        assert result.exit_code == 0
        assert "Send a message" in result.output


class TestSendLocation:
    """GPS location options."""

    def test_lat_lon_passes_user_location(
        self, cli_runner, mock_auth_class, mock_api_class, sample_send_result
    ):
        _, api = mock_api_class
        api.send_message.return_value = sample_send_result
        result = cli_runner.invoke(
            cli,
            ["send", "--to", RECIPIENT_ID, "--message", "Here",
             "--latitude", "45.5231", "--longitude", "-122.6765"],
        )
        assert result.exit_code == 0
        call_kwargs = api.send_message.call_args.kwargs
        loc = call_kwargs["user_location"]
        assert isinstance(loc, UserLocation)
        assert loc.latitudeDegrees == 45.5231
        assert loc.longitudeDegrees == -122.6765
        assert loc.elevationMeters is None

    def test_lat_lon_elevation(
        self, cli_runner, mock_auth_class, mock_api_class, sample_send_result
    ):
        _, api = mock_api_class
        api.send_message.return_value = sample_send_result
        result = cli_runner.invoke(
            cli,
            ["send", "--to", RECIPIENT_ID, "--message", "Summit",
             "--latitude", "45.5231", "--longitude", "-122.6765",
             "--elevation", "1234.5"],
        )
        assert result.exit_code == 0
        loc = api.send_message.call_args.kwargs["user_location"]
        assert loc.elevationMeters == 1234.5

    def test_short_flags_lat_lon(
        self, cli_runner, mock_auth_class, mock_api_class, sample_send_result
    ):
        _, api = mock_api_class
        api.send_message.return_value = sample_send_result
        result = cli_runner.invoke(
            cli,
            ["send", "--to", RECIPIENT_ID, "--message", "Here",
             "--lat", "10.0", "--lon", "20.0"],
        )
        assert result.exit_code == 0
        loc = api.send_message.call_args.kwargs["user_location"]
        assert loc.latitudeDegrees == 10.0
        assert loc.longitudeDegrees == 20.0

    def test_lat_without_lon_errors(
        self, cli_runner, mock_auth_class, mock_api_class
    ):
        result = cli_runner.invoke(
            cli,
            ["send", "--to", RECIPIENT_ID, "--message", "Hello",
             "--latitude", "45.0"],
        )
        assert result.exit_code == 2
        assert "--latitude and --longitude must both be provided" in result.output

    def test_lon_without_lat_errors(
        self, cli_runner, mock_auth_class, mock_api_class
    ):
        result = cli_runner.invoke(
            cli,
            ["send", "--to", RECIPIENT_ID, "--message", "Hello",
             "--longitude", "-122.0"],
        )
        assert result.exit_code == 2
        assert "--latitude and --longitude must both be provided" in result.output

    def test_elevation_without_lat_lon_errors(
        self, cli_runner, mock_auth_class, mock_api_class
    ):
        result = cli_runner.invoke(
            cli,
            ["send", "--to", RECIPIENT_ID, "--message", "Hello",
             "--elevation", "100.0"],
        )
        assert result.exit_code == 2
        assert "--elevation requires --latitude and --longitude" in result.output

    def test_no_location_passes_none(
        self, cli_runner, mock_auth_class, mock_api_class, sample_send_result
    ):
        _, api = mock_api_class
        api.send_message.return_value = sample_send_result
        cli_runner.invoke(
            cli, ["send", "--to", RECIPIENT_ID, "--message", "Hello"]
        )
        call_kwargs = api.send_message.call_args.kwargs
        assert call_kwargs["user_location"] is None


class TestSendAuth:
    """Auth failures."""

    def test_no_session_exits(self, cli_runner, mock_auth_class):
        _, instance = mock_auth_class
        instance.resume.side_effect = RuntimeError("No saved session")
        result = cli_runner.invoke(
            cli, ["send", "--to", RECIPIENT_ID, "--message", "Hello"]
        )
        assert result.exit_code == 1
        assert "Run 'garmin-messenger login'" in result.stderr


class TestSendMedia:
    """send --file / -f media attachment."""

    def test_avif_calls_send_media_message(
        self, cli_runner, mock_auth_class, mock_api_class, sample_send_media_result, tmp_path
    ):
        _, api = mock_api_class
        api.send_media_message.return_value = sample_send_media_result
        f = tmp_path / "photo.avif"
        f.write_bytes(b"\x00\x00\x00\x1cftyp")
        result = cli_runner.invoke(
            cli, ["send", "--to", RECIPIENT_ID, "--message", "Look!", "--file", str(f)]
        )
        assert result.exit_code == 0
        api.send_media_message.assert_called_once()
        kw = api.send_media_message.call_args.kwargs
        assert kw["media_type"] == MediaType.IMAGE_AVIF
        assert kw["file_data"] == b"\x00\x00\x00\x1cftyp"
        assert kw["to"] == [RECIPIENT_ID]
        assert kw["message_body"] == "Look!"

    def test_ogg_calls_send_media_message(
        self, cli_runner, mock_auth_class, mock_api_class, sample_send_media_result, tmp_path
    ):
        _, api = mock_api_class
        api.send_media_message.return_value = sample_send_media_result
        f = tmp_path / "voice.ogg"
        f.write_bytes(b"OggS")
        result = cli_runner.invoke(
            cli, ["send", "--to", RECIPIENT_ID, "--message", "Listen", "--file", str(f)]
        )
        assert result.exit_code == 0
        kw = api.send_media_message.call_args.kwargs
        assert kw["media_type"] == MediaType.AUDIO_OGG

    def test_oga_calls_send_media_message(
        self, cli_runner, mock_auth_class, mock_api_class, sample_send_media_result, tmp_path
    ):
        _, api = mock_api_class
        api.send_media_message.return_value = sample_send_media_result
        f = tmp_path / "voice.oga"
        f.write_bytes(b"OggS")
        result = cli_runner.invoke(
            cli, ["send", "--to", RECIPIENT_ID, "--message", "Listen", "--file", str(f)]
        )
        assert result.exit_code == 0
        kw = api.send_media_message.call_args.kwargs
        assert kw["media_type"] == MediaType.AUDIO_OGG

    def test_file_with_location(
        self, cli_runner, mock_auth_class, mock_api_class, sample_send_media_result, tmp_path
    ):
        _, api = mock_api_class
        api.send_media_message.return_value = sample_send_media_result
        f = tmp_path / "photo.avif"
        f.write_bytes(b"\x00")
        result = cli_runner.invoke(
            cli,
            ["send", "--to", RECIPIENT_ID, "--message", "Here",
             "--file", str(f), "--lat", "45.5", "--lon", "-122.6"],
        )
        assert result.exit_code == 0
        kw = api.send_media_message.call_args.kwargs
        assert isinstance(kw["user_location"], UserLocation)
        assert kw["user_location"].latitudeDegrees == 45.5

    def test_unsupported_extension_errors(
        self, cli_runner, mock_auth_class, mock_api_class, tmp_path
    ):
        f = tmp_path / "photo.jpg"
        f.write_bytes(b"\xff\xd8")
        result = cli_runner.invoke(
            cli, ["send", "--to", RECIPIENT_ID, "--message", "Nope", "--file", str(f)]
        )
        assert result.exit_code == 2
        assert "Unsupported file extension" in result.output

    def test_unsupported_mp3_errors(
        self, cli_runner, mock_auth_class, mock_api_class, tmp_path
    ):
        f = tmp_path / "song.mp3"
        f.write_bytes(b"ID3")
        result = cli_runner.invoke(
            cli, ["send", "--to", RECIPIENT_ID, "--message", "Nope", "--file", str(f)]
        )
        assert result.exit_code == 2
        assert "Unsupported file extension" in result.output

    def test_no_file_still_calls_send_message(
        self, cli_runner, mock_auth_class, mock_api_class, sample_send_result
    ):
        _, api = mock_api_class
        api.send_message.return_value = sample_send_result
        result = cli_runner.invoke(
            cli, ["send", "--to", RECIPIENT_ID, "--message", "Text only"]
        )
        assert result.exit_code == 0
        api.send_message.assert_called_once()
        api.send_media_message.assert_not_called()

    def test_output_shows_ids(
        self, cli_runner, mock_auth_class, mock_api_class, sample_send_media_result, tmp_path
    ):
        _, api = mock_api_class
        api.send_media_message.return_value = sample_send_media_result
        f = tmp_path / "photo.avif"
        f.write_bytes(b"\x00")
        result = cli_runner.invoke(
            cli, ["send", "--to", RECIPIENT_ID, "--message", "Look!", "--file", str(f)]
        )
        assert MSG_ID in result.output
        assert CONV_ID in result.output

    def test_short_flag_f(
        self, cli_runner, mock_auth_class, mock_api_class, sample_send_media_result, tmp_path
    ):
        _, api = mock_api_class
        api.send_media_message.return_value = sample_send_media_result
        f = tmp_path / "photo.avif"
        f.write_bytes(b"\x00")
        result = cli_runner.invoke(
            cli, ["send", "--to", RECIPIENT_ID, "--message", "Look!", "-f", str(f)]
        )
        assert result.exit_code == 0
        api.send_media_message.assert_called_once()
