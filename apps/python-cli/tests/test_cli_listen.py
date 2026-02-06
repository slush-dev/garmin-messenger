"""Tests for the listen command."""

from __future__ import annotations

import signal as signal_mod
from unittest.mock import patch
from uuid import UUID

import pytest
from garmin_messenger.models import (
    MediaMetadata,
    MediaType,
    MessageModel,
    MessageStatusUpdate,
    SimpleCompoundMessageId,
    UserLocation,
)

from garmin_messenger_cli.main import cli

from .conftest import CONV_ID, MODULE, MSG_ID, STATUS_USER_UUID, USER_ID

MEDIA_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


class TestListenSetup:
    """listen creates SignalR, registers handlers, calls start."""

    def _invoke_listen(self, cli_runner, mock_auth_class, mock_signalr_class):
        """Helper: invoke listen with time.sleep raising SystemExit."""
        _, sr = mock_signalr_class
        with patch(f"{MODULE}.time.sleep", side_effect=SystemExit(0)), \
             patch(f"{MODULE}.signal.signal"):
            result = cli_runner.invoke(cli, ["listen"])
        return result, sr

    def test_creates_signalr_with_auth(
        self, cli_runner, mock_auth_class, mock_signalr_class
    ):
        MockSR, _ = mock_signalr_class
        _, auth_inst = mock_auth_class
        with patch(f"{MODULE}.time.sleep", side_effect=SystemExit(0)), \
             patch(f"{MODULE}.signal.signal"):
            cli_runner.invoke(cli, ["listen"])
        MockSR.assert_called_once_with(auth_inst)

    def test_registers_on_message(
        self, cli_runner, mock_auth_class, mock_signalr_class
    ):
        result, sr = self._invoke_listen(cli_runner, mock_auth_class, mock_signalr_class)
        sr.on_message.assert_called_once()

    def test_registers_on_status(
        self, cli_runner, mock_auth_class, mock_signalr_class
    ):
        result, sr = self._invoke_listen(cli_runner, mock_auth_class, mock_signalr_class)
        sr.on_status_update.assert_called_once()

    def test_registers_on_open(
        self, cli_runner, mock_auth_class, mock_signalr_class
    ):
        result, sr = self._invoke_listen(cli_runner, mock_auth_class, mock_signalr_class)
        sr.on_open.assert_called_once()

    def test_registers_on_close(
        self, cli_runner, mock_auth_class, mock_signalr_class
    ):
        result, sr = self._invoke_listen(cli_runner, mock_auth_class, mock_signalr_class)
        sr.on_close.assert_called_once()

    def test_registers_on_nonconversational_message(
        self, cli_runner, mock_auth_class, mock_signalr_class
    ):
        result, sr = self._invoke_listen(cli_runner, mock_auth_class, mock_signalr_class)
        sr.on_nonconversational_message.assert_called_once()

    def test_registers_on_error(
        self, cli_runner, mock_auth_class, mock_signalr_class
    ):
        result, sr = self._invoke_listen(cli_runner, mock_auth_class, mock_signalr_class)
        sr.on_error.assert_called_once()

    def test_calls_start(
        self, cli_runner, mock_auth_class, mock_signalr_class
    ):
        result, sr = self._invoke_listen(cli_runner, mock_auth_class, mock_signalr_class)
        sr.start.assert_called_once()

    def test_outputs_listening(
        self, cli_runner, mock_auth_class, mock_signalr_class
    ):
        result, _ = self._invoke_listen(cli_runner, mock_auth_class, mock_signalr_class)
        assert "Listening" in result.output


class TestListenHandlers:
    """Handler callbacks produce correct output."""

    def _get_handlers(self, cli_runner, mock_auth_class, mock_signalr_class):
        """Invoke listen and capture the registered handler functions."""
        _, sr = mock_signalr_class
        with patch(f"{MODULE}.time.sleep", side_effect=SystemExit(0)), \
             patch(f"{MODULE}.signal.signal"):
            cli_runner.invoke(cli, ["listen"])

        on_msg = sr.on_message.call_args[0][0]
        on_status = sr.on_status_update.call_args[0][0]
        on_nonconv = sr.on_nonconversational_message.call_args[0][0]
        on_open = sr.on_open.call_args[0][0]
        on_close = sr.on_close.call_args[0][0]
        on_error = sr.on_error.call_args[0][0]
        return on_msg, on_status, on_nonconv, on_open, on_close, on_error, sr

    def test_on_message_format(
        self, cli_runner, mock_auth_class, mock_signalr_class, capsys
    ):
        on_msg, *_, sr = self._get_handlers(
            cli_runner, mock_auth_class, mock_signalr_class
        )
        msg = MessageModel(
            messageId=UUID(MSG_ID),
            conversationId=UUID(CONV_ID),
            messageBody="Satellite ping",
            from_=USER_ID,
        )
        on_msg(msg)
        captured = capsys.readouterr()
        assert CONV_ID in captured.out
        assert USER_ID in captured.out
        assert "Satellite ping" in captured.out

    def test_on_message_calls_mark_as_delivered(
        self, cli_runner, mock_auth_class, mock_signalr_class
    ):
        on_msg, *_, sr = self._get_handlers(
            cli_runner, mock_auth_class, mock_signalr_class
        )
        msg = MessageModel(
            messageId=UUID(MSG_ID),
            conversationId=UUID(CONV_ID),
            messageBody="test",
            from_=USER_ID,
        )
        on_msg(msg)
        sr.mark_as_delivered.assert_called_once_with(UUID(MSG_ID), UUID(CONV_ID))

    def test_on_message_missing_sender(
        self, cli_runner, mock_auth_class, mock_signalr_class, capsys
    ):
        on_msg, *_ = self._get_handlers(
            cli_runner, mock_auth_class, mock_signalr_class
        )
        msg = MessageModel(
            messageId=UUID(MSG_ID),
            conversationId=UUID(CONV_ID),
            messageBody="No sender",
            from_=None,
        )
        on_msg(msg)
        captured = capsys.readouterr()
        assert "?" in captured.out

    def test_on_status_format(
        self, cli_runner, mock_auth_class, mock_signalr_class, capsys
    ):
        _, on_status, *_ = self._get_handlers(
            cli_runner, mock_auth_class, mock_signalr_class
        )
        update = MessageStatusUpdate(
            messageId=SimpleCompoundMessageId(
                messageId=UUID(MSG_ID),
                conversationId=UUID(CONV_ID),
            ),
            messageStatus="Delivered",
            userId=UUID(STATUS_USER_UUID),
        )
        on_status(update)
        captured = capsys.readouterr()
        assert "STATUS" in captured.out
        # conversation shown (falls back to ID when no contacts)
        assert CONV_ID in captured.out
        assert "DELIVERED" in captured.out or "Delivered" in captured.out
        # message_id hidden by default (requires --uuid)
        assert MSG_ID not in captured.out

    def test_on_open_output(
        self, cli_runner, mock_auth_class, mock_signalr_class, capsys
    ):
        *_, on_open, on_close, on_error, sr = self._get_handlers(
            cli_runner, mock_auth_class, mock_signalr_class
        )
        on_open()
        captured = capsys.readouterr()
        assert "connected" in captured.out.lower()

    def test_on_close_output(
        self, cli_runner, mock_auth_class, mock_signalr_class, capsys
    ):
        *_, on_open, on_close, on_error, sr = self._get_handlers(
            cli_runner, mock_auth_class, mock_signalr_class
        )
        on_close()
        captured = capsys.readouterr()
        assert "disconnected" in captured.out.lower()

    def test_on_error_output(
        self, cli_runner, mock_auth_class, mock_signalr_class, capsys
    ):
        *_, on_error, sr = self._get_handlers(
            cli_runner, mock_auth_class, mock_signalr_class
        )
        on_error("connection lost")
        captured = capsys.readouterr()
        assert "error" in captured.out.lower() or "error" in captured.err.lower()

    def test_on_message_with_location(
        self, cli_runner, mock_auth_class, mock_signalr_class, capsys
    ):
        on_msg, *_, sr = self._get_handlers(
            cli_runner, mock_auth_class, mock_signalr_class
        )
        msg = MessageModel(
            messageId=UUID(MSG_ID),
            conversationId=UUID(CONV_ID),
            messageBody="I'm here",
            from_=USER_ID,
            userLocation=UserLocation(
                latitudeDegrees=45.5231,
                longitudeDegrees=-122.6765,
            ),
        )
        on_msg(msg)
        captured = capsys.readouterr()
        assert "@ 45.5231, -122.6765" in captured.out

    def test_on_message_with_elevation(
        self, cli_runner, mock_auth_class, mock_signalr_class, capsys
    ):
        on_msg, *_, sr = self._get_handlers(
            cli_runner, mock_auth_class, mock_signalr_class
        )
        msg = MessageModel(
            messageId=UUID(MSG_ID),
            conversationId=UUID(CONV_ID),
            messageBody="Summit",
            from_=USER_ID,
            userLocation=UserLocation(
                latitudeDegrees=45.5, longitudeDegrees=-122.6, elevationMeters=1500.0
            ),
        )
        on_msg(msg)
        captured = capsys.readouterr()
        assert "@ 45.5, -122.6, 1500.0m" in captured.out

    def test_on_message_with_reference_point(
        self, cli_runner, mock_auth_class, mock_signalr_class, capsys
    ):
        on_msg, *_, sr = self._get_handlers(
            cli_runner, mock_auth_class, mock_signalr_class
        )
        msg = MessageModel(
            messageId=UUID(MSG_ID),
            conversationId=UUID(CONV_ID),
            messageBody="Check this spot",
            from_=USER_ID,
            referencePoint=UserLocation(
                latitudeDegrees=50.0, longitudeDegrees=14.0,
            ),
        )
        on_msg(msg)
        captured = capsys.readouterr()
        assert "REF" in captured.out
        assert "@ 50.0, 14.0" in captured.out

    def test_on_message_with_map_share_url(
        self, cli_runner, mock_auth_class, mock_signalr_class, capsys
    ):
        on_msg, *_, sr = self._get_handlers(
            cli_runner, mock_auth_class, mock_signalr_class
        )
        msg = MessageModel(
            messageId=UUID(MSG_ID),
            conversationId=UUID(CONV_ID),
            messageBody="Sharing map",
            from_=USER_ID,
            mapShareUrl="https://share.garmin.com/abc",
        )
        on_msg(msg)
        captured = capsys.readouterr()
        assert "MapShare: https://share.garmin.com/abc" in captured.out

    def test_on_message_with_live_track_url(
        self, cli_runner, mock_auth_class, mock_signalr_class, capsys
    ):
        on_msg, *_, sr = self._get_handlers(
            cli_runner, mock_auth_class, mock_signalr_class
        )
        msg = MessageModel(
            messageId=UUID(MSG_ID),
            conversationId=UUID(CONV_ID),
            messageBody="Track me",
            from_=USER_ID,
            liveTrackUrl="https://livetrack.garmin.com/xyz",
        )
        on_msg(msg)
        captured = capsys.readouterr()
        assert "LiveTrack: https://livetrack.garmin.com/xyz" in captured.out

    def test_on_nonconversational_message_format(
        self, cli_runner, mock_auth_class, mock_signalr_class, capsys
    ):
        _, _, on_nonconv, *_ = self._get_handlers(
            cli_runner, mock_auth_class, mock_signalr_class
        )
        on_nonconv("300234063904190")
        captured = capsys.readouterr()
        assert "DEVICE" in captured.out
        assert "300234063904190" in captured.out

    def test_on_message_without_location_no_marker(
        self, cli_runner, mock_auth_class, mock_signalr_class, capsys
    ):
        on_msg, *_, sr = self._get_handlers(
            cli_runner, mock_auth_class, mock_signalr_class
        )
        msg = MessageModel(
            messageId=UUID(MSG_ID),
            conversationId=UUID(CONV_ID),
            messageBody="No location",
            from_=USER_ID,
        )
        on_msg(msg)
        captured = capsys.readouterr()
        assert "@ " not in captured.out


class TestListenSignalHandling:
    """Signal registration and shutdown."""

    def test_registers_sigint(
        self, cli_runner, mock_auth_class, mock_signalr_class
    ):
        with patch(f"{MODULE}.time.sleep", side_effect=SystemExit(0)), \
             patch(f"{MODULE}.signal.signal") as mock_signal:
            cli_runner.invoke(cli, ["listen"])
        sigint_calls = [c for c in mock_signal.call_args_list if c[0][0] == signal_mod.SIGINT]
        assert len(sigint_calls) == 1

    def test_registers_sigterm(
        self, cli_runner, mock_auth_class, mock_signalr_class
    ):
        with patch(f"{MODULE}.time.sleep", side_effect=SystemExit(0)), \
             patch(f"{MODULE}.signal.signal") as mock_signal:
            cli_runner.invoke(cli, ["listen"])
        sigterm_calls = [c for c in mock_signal.call_args_list if c[0][0] == signal_mod.SIGTERM]
        assert len(sigterm_calls) == 1

    def test_signal_handler_calls_stop(
        self, cli_runner, mock_auth_class, mock_signalr_class
    ):
        """The registered signal handler calls sr.stop()."""
        _, sr = mock_signalr_class
        captured_handlers = {}

        def capture_signal(signum, handler):
            captured_handlers[signum] = handler

        with patch(f"{MODULE}.time.sleep", side_effect=SystemExit(0)), \
             patch(f"{MODULE}.signal.signal", side_effect=capture_signal):
            cli_runner.invoke(cli, ["listen"])

        # Call the SIGINT handler
        handler = captured_handlers.get(signal_mod.SIGINT)
        assert handler is not None
        with pytest.raises(SystemExit):
            handler(signal_mod.SIGINT, None)
        sr.stop.assert_called_once()


class TestListenAuth:
    """Auth failures."""

    def test_no_session_exits(self, cli_runner, mock_auth_class):
        _, instance = mock_auth_class
        instance.resume.side_effect = RuntimeError("No saved session")
        result = cli_runner.invoke(cli, ["listen"])
        assert result.exit_code == 1
        assert "Run 'garmin-messenger login'" in result.stderr


class TestListenConversationName:
    """Conversation name resolution in listen."""

    def _get_handlers_with_contacts(
        self, cli_runner, mock_auth_class, mock_signalr_class, tmp_path,
    ):
        """Invoke listen with a contacts.yaml that has conversation names."""
        import yaml as _yaml
        contacts_data = {
            "members": {}, "conversations": {CONV_ID: "Weekend Hiking"},
        }
        (tmp_path / "contacts.yaml").write_text(_yaml.dump(contacts_data))

        _, sr = mock_signalr_class
        with patch(f"{MODULE}.time.sleep", side_effect=SystemExit(0)), \
             patch(f"{MODULE}.signal.signal"):
            cli_runner.invoke(cli, ["--session-dir", str(tmp_path), "listen"])

        on_msg = sr.on_message.call_args[0][0]
        return on_msg, sr

    def test_conversation_name_shown(
        self, cli_runner, mock_auth_class, mock_signalr_class, tmp_path, capsys
    ):
        on_msg, _ = self._get_handlers_with_contacts(
            cli_runner, mock_auth_class, mock_signalr_class, tmp_path
        )
        msg = MessageModel(
            messageId=UUID(MSG_ID),
            conversationId=UUID(CONV_ID),
            messageBody="Hello!",
            from_=USER_ID,
        )
        on_msg(msg)
        captured = capsys.readouterr()
        assert "Weekend Hiking" in captured.out
        assert CONV_ID not in captured.out

    def test_conversation_fallback_to_id(
        self, cli_runner, mock_auth_class, mock_signalr_class, capsys
    ):
        """No contacts → falls back to conversation_id."""
        _, sr = mock_signalr_class
        with patch(f"{MODULE}.time.sleep", side_effect=SystemExit(0)), \
             patch(f"{MODULE}.signal.signal"):
            cli_runner.invoke(cli, ["listen"])

        on_msg = sr.on_message.call_args[0][0]
        msg = MessageModel(
            messageId=UUID(MSG_ID),
            conversationId=UUID(CONV_ID),
            messageBody="Hello!",
            from_=USER_ID,
        )
        on_msg(msg)
        captured = capsys.readouterr()
        assert CONV_ID in captured.out


class TestListenUuidFlag:
    """--uuid flag controls ID visibility."""

    def _get_handlers_with_uuid(self, cli_runner, mock_auth_class, mock_signalr_class):
        """Invoke listen --uuid and capture handlers."""
        _, sr = mock_signalr_class
        with patch(f"{MODULE}.time.sleep", side_effect=SystemExit(0)), \
             patch(f"{MODULE}.signal.signal"):
            cli_runner.invoke(cli, ["listen", "--uuid"])

        on_msg = sr.on_message.call_args[0][0]
        return on_msg, sr

    def test_help_shows_uuid_flag(self, cli_runner):
        result = cli_runner.invoke(cli, ["listen", "--help"])
        assert "--uuid" in result.output


class TestListenMedia:
    """Media attachment display in listen."""

    def _get_handlers(self, cli_runner, mock_auth_class, mock_signalr_class):
        _, sr = mock_signalr_class
        with patch(f"{MODULE}.time.sleep", side_effect=SystemExit(0)), \
             patch(f"{MODULE}.signal.signal"):
            cli_runner.invoke(cli, ["listen"])
        on_msg = sr.on_message.call_args[0][0]
        return on_msg, sr

    def _get_handlers_yaml(self, cli_runner, mock_auth_class, mock_signalr_class):
        _, sr = mock_signalr_class
        with patch(f"{MODULE}.time.sleep", side_effect=SystemExit(0)), \
             patch(f"{MODULE}.signal.signal"):
            cli_runner.invoke(cli, ["--yaml", "listen"])
        on_msg = sr.on_message.call_args[0][0]
        return on_msg, sr

    def test_media_cmd_shown_text(
        self, cli_runner, mock_auth_class, mock_signalr_class, capsys
    ):
        on_msg, _ = self._get_handlers(
            cli_runner, mock_auth_class, mock_signalr_class
        )
        msg = MessageModel(
            messageId=UUID(MSG_ID),
            conversationId=UUID(CONV_ID),
            messageBody="Photo",
            from_=USER_ID,
            mediaId=UUID(MEDIA_ID),
            mediaType=MediaType.IMAGE_AVIF,
        )
        on_msg(msg)
        captured = capsys.readouterr()
        assert "garmin-messenger media" in captured.out
        assert MEDIA_ID in captured.out
        assert "ImageAvif" in captured.out

    def test_no_media_no_cmd(
        self, cli_runner, mock_auth_class, mock_signalr_class, capsys
    ):
        on_msg, _ = self._get_handlers(
            cli_runner, mock_auth_class, mock_signalr_class
        )
        msg = MessageModel(
            messageId=UUID(MSG_ID),
            conversationId=UUID(CONV_ID),
            messageBody="Just text",
            from_=USER_ID,
        )
        on_msg(msg)
        captured = capsys.readouterr()
        assert "garmin-messenger media" not in captured.out

    def test_media_yaml_includes_fields(
        self, cli_runner, mock_auth_class, mock_signalr_class, capsys
    ):
        import yaml
        on_msg, _ = self._get_handlers_yaml(
            cli_runner, mock_auth_class, mock_signalr_class
        )
        msg = MessageModel(
            messageId=UUID(MSG_ID),
            conversationId=UUID(CONV_ID),
            messageBody="Photo",
            from_=USER_ID,
            mediaId=UUID(MEDIA_ID),
            mediaType=MediaType.IMAGE_AVIF,
            mediaMetadata=MediaMetadata(width=1920, height=1080),
        )
        on_msg(msg)
        captured = capsys.readouterr()
        data = yaml.safe_load(captured.out)
        assert data["media_id"] == MEDIA_ID
        assert data["media_type"] == "ImageAvif"
        assert data["media_metadata"]["width"] == 1920
        assert data["media_metadata"]["height"] == 1080
        assert data["conversation_id"] == CONV_ID
        assert data["message_id"] == MSG_ID

    def test_media_yaml_duration(
        self, cli_runner, mock_auth_class, mock_signalr_class, capsys
    ):
        import yaml
        on_msg, _ = self._get_handlers_yaml(
            cli_runner, mock_auth_class, mock_signalr_class
        )
        msg = MessageModel(
            messageId=UUID(MSG_ID),
            conversationId=UUID(CONV_ID),
            messageBody="Audio",
            from_=USER_ID,
            mediaId=UUID(MEDIA_ID),
            mediaType=MediaType.AUDIO_OGG,
            mediaMetadata=MediaMetadata(durationMs=5000),
        )
        on_msg(msg)
        captured = capsys.readouterr()
        data = yaml.safe_load(captured.out)
        assert data["media_metadata"]["duration_ms"] == 5000


class TestListenHelp:
    """--help."""

    def test_help(self, cli_runner):
        result = cli_runner.invoke(cli, ["listen", "--help"])
        assert result.exit_code == 0
        assert "Listen for incoming messages" in result.output
