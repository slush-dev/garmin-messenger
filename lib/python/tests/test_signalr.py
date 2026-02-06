"""Tests for garmin_messenger.signalr — HermesSignalR WebSocket client."""

from __future__ import annotations

import threading
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest

from garmin_messenger.models import (
    ConversationMuteStatusUpdate,
    MessageModel,
    MessageStatus,
    MessageStatusUpdate,
    NetworkPropertiesResponse,
    ServerNotification,
    UserBlockStatusUpdate,
)
from garmin_messenger.signalr import HUB_PATH, HermesSignalR

from .conftest import CONV_ID, MSG_ID, USER_ID


@pytest.fixture
def mock_hub():
    """Mock signalrcore hub connection."""
    hub = MagicMock()
    hub.start = MagicMock()
    hub.stop = MagicMock()
    hub.send = MagicMock()
    hub.on = MagicMock()
    hub.on_open = MagicMock()
    hub.on_close = MagicMock()
    hub.on_error = MagicMock()
    return hub


@pytest.fixture
def signalr_client(mock_auth, mock_hub):
    """HermesSignalR with patched HubConnectionBuilder."""
    with patch("garmin_messenger.signalr.HubConnectionBuilder") as mock_builder:
        builder = MagicMock()
        builder.with_url.return_value = builder
        builder.with_automatic_reconnect.return_value = builder
        builder.build.return_value = mock_hub
        mock_builder.return_value = builder

        client = HermesSignalR(mock_auth)
        yield client, mock_hub, mock_builder


# =========================================================================== #
# Event registration
# =========================================================================== #


class TestEventRegistration:
    def test_on_message(self, mock_auth):
        client = HermesSignalR(mock_auth)
        handler = MagicMock()
        client.on_message(handler)
        assert client._on_message is handler

    def test_on_status_update(self, mock_auth):
        client = HermesSignalR(mock_auth)
        handler = MagicMock()
        client.on_status_update(handler)
        assert client._on_status_update is handler

    def test_on_mute_update(self, mock_auth):
        client = HermesSignalR(mock_auth)
        handler = MagicMock()
        client.on_mute_update(handler)
        assert client._on_mute_update is handler

    def test_on_block_update(self, mock_auth):
        client = HermesSignalR(mock_auth)
        handler = MagicMock()
        client.on_block_update(handler)
        assert client._on_block_update is handler

    def test_on_notification(self, mock_auth):
        client = HermesSignalR(mock_auth)
        handler = MagicMock()
        client.on_notification(handler)
        assert client._on_notification is handler

    def test_on_open(self, mock_auth):
        client = HermesSignalR(mock_auth)
        handler = MagicMock()
        client.on_open(handler)
        assert client._on_open is handler

    def test_on_close(self, mock_auth):
        client = HermesSignalR(mock_auth)
        handler = MagicMock()
        client.on_close(handler)
        assert client._on_close is handler

    def test_on_nonconversational_message(self, mock_auth):
        client = HermesSignalR(mock_auth)
        handler = MagicMock()
        client.on_nonconversational_message(handler)
        assert client._on_nonconversational_message is handler

    def test_on_error(self, mock_auth):
        client = HermesSignalR(mock_auth)
        handler = MagicMock()
        client.on_error(handler)
        assert client._on_error is handler


# =========================================================================== #
# Connection lifecycle
# =========================================================================== #


class TestConnectionLifecycle:
    def test_start_builds_and_starts(self, signalr_client):
        client, mock_hub, mock_builder = signalr_client
        client.start()

        mock_builder.assert_called_once()
        mock_hub.start.assert_called_once()
        assert client._stopped is False

    def test_start_registers_server_handlers(self, signalr_client):
        client, mock_hub, _ = signalr_client
        client.start()

        on_calls = [call[0][0] for call in mock_hub.on.call_args_list]
        assert "ReceiveMessage" in on_calls
        assert "ReceiveMessageUpdate" in on_calls
        assert "ReceiveConversationMuteStatusUpdate" in on_calls
        assert "ReceiveUserBlockStatusUpdate" in on_calls
        assert "ReceiveServerNotification" in on_calls
        assert "ReceiveNonconversationalMessage" in on_calls
        assert mock_hub.on.call_count == 6

    def test_start_registers_lifecycle_handlers(self, signalr_client):
        client, mock_hub, _ = signalr_client
        client.start()

        mock_hub.on_open.assert_called_once()
        mock_hub.on_close.assert_called_once()
        mock_hub.on_error.assert_called_once()

    def test_hub_url_correct(self, signalr_client):
        client, mock_hub, mock_builder = signalr_client
        client.start()

        builder = mock_builder.return_value
        url_arg = builder.with_url.call_args[0][0]
        assert url_arg == f"{client.auth.hermes_base}{HUB_PATH}"

    def test_stop_calls_hub_stop(self, signalr_client):
        client, mock_hub, _ = signalr_client
        client.start()
        client.stop()

        mock_hub.stop.assert_called()
        assert client._stopped is True

    def test_stop_without_hub_no_error(self, mock_auth):
        client = HermesSignalR(mock_auth)
        assert client._hub is None
        client.stop()  # should not raise
        assert client._stopped is True


# =========================================================================== #
# Handler dispatch
# =========================================================================== #


class TestHandlerDispatch:
    def test_handle_message_dispatches(self, mock_auth, sample_message_dict):
        client = HermesSignalR(mock_auth)
        handler = MagicMock()
        client.on_message(handler)

        client._handle_message([sample_message_dict])

        handler.assert_called_once()
        msg = handler.call_args[0][0]
        assert isinstance(msg, MessageModel)
        assert str(msg.messageId) == MSG_ID

    def test_handle_message_from_keyword(self, mock_auth, sample_message_dict):
        client = HermesSignalR(mock_auth)
        handler = MagicMock()
        client.on_message(handler)

        client._handle_message([sample_message_dict])

        msg = handler.call_args[0][0]
        assert msg.from_ == USER_ID

    def test_handle_message_no_handler(self, mock_auth, sample_message_dict):
        client = HermesSignalR(mock_auth)
        # _on_message is None
        client._handle_message([sample_message_dict])  # should not raise

    def test_handle_message_bad_data(self, mock_auth):
        client = HermesSignalR(mock_auth)
        handler = MagicMock()
        client.on_message(handler)

        # Missing required fields — should log error, not raise
        client._handle_message([{"invalid": "data"}])
        handler.assert_not_called()

    def test_handle_status_update_dispatches(self, mock_auth, sample_status_update_dict):
        client = HermesSignalR(mock_auth)
        handler = MagicMock()
        client.on_status_update(handler)

        client._handle_status_update([sample_status_update_dict])

        handler.assert_called_once()
        update = handler.call_args[0][0]
        assert isinstance(update, MessageStatusUpdate)
        # The "status" key remap should work
        assert update.messageStatus == MessageStatus.DELIVERED

    def test_handle_mute_update_dispatches(self, mock_auth):
        client = HermesSignalR(mock_auth)
        handler = MagicMock()
        client.on_mute_update(handler)

        client._handle_mute_update([{
            "conversationId": CONV_ID,
            "isMuted": True,
        }])

        handler.assert_called_once()
        update = handler.call_args[0][0]
        assert isinstance(update, ConversationMuteStatusUpdate)
        assert update.isMuted is True

    def test_handle_block_update_dispatches(self, mock_auth):
        client = HermesSignalR(mock_auth)
        handler = MagicMock()
        client.on_block_update(handler)

        client._handle_block_update([{
            "userId": USER_ID,
            "isBlocked": True,
        }])

        handler.assert_called_once()
        update = handler.call_args[0][0]
        assert isinstance(update, UserBlockStatusUpdate)

    def test_handle_notification_dispatches(self, mock_auth):
        client = HermesSignalR(mock_auth)
        handler = MagicMock()
        client.on_notification(handler)

        client._handle_notification([{
            "notificationType": "Maintenance",
            "message": "Server restarting",
        }])

        handler.assert_called_once()
        notif = handler.call_args[0][0]
        assert isinstance(notif, ServerNotification)
        assert notif.message == "Server restarting"

    def test_handle_nonconversational_message_dispatches(self, mock_auth):
        client = HermesSignalR(mock_auth)
        handler = MagicMock()
        client.on_nonconversational_message(handler)

        client._handle_nonconversational_message(["300234063904190"])

        handler.assert_called_once_with("300234063904190")

    def test_handle_nonconversational_message_no_handler(self, mock_auth):
        client = HermesSignalR(mock_auth)
        client._handle_nonconversational_message(["300234063904190"])  # should not raise

    def test_handle_nonconversational_message_numeric_imei(self, mock_auth):
        """IMEI may arrive as a number; handler should receive a string."""
        client = HermesSignalR(mock_auth)
        handler = MagicMock()
        client.on_nonconversational_message(handler)

        client._handle_nonconversational_message([300234063904190])

        handler.assert_called_once_with("300234063904190")

    def test_handle_error_dispatches(self, mock_auth):
        client = HermesSignalR(mock_auth)
        handler = MagicMock()
        client.on_error(handler)

        client._handle_error("connection failed")

        handler.assert_called_once_with("connection failed")

    def test_handle_error_no_handler(self, mock_auth):
        client = HermesSignalR(mock_auth)
        client._handle_error("some error")  # should not raise


# =========================================================================== #
# Hub open/close handlers
# =========================================================================== #


class TestHubOpenClose:
    def test_on_hub_open_calls_handler(self, mock_auth):
        client = HermesSignalR(mock_auth)
        handler = MagicMock()
        client.on_open(handler)

        client._on_hub_open()
        handler.assert_called_once()

    def test_on_hub_close_calls_handler(self, mock_auth):
        client = HermesSignalR(mock_auth)
        handler = MagicMock()
        client.on_close(handler)

        with patch.object(client, "_schedule_full_reconnect"):
            client._on_hub_close()
        handler.assert_called_once()

    def test_on_hub_close_triggers_reconnect_when_not_stopped(self, mock_auth):
        client = HermesSignalR(mock_auth)
        client._stopped = False

        with patch.object(client, "_schedule_full_reconnect") as mock_reconnect:
            client._on_hub_close()
        mock_reconnect.assert_called_once()

    def test_on_hub_close_no_reconnect_when_stopped(self, mock_auth):
        client = HermesSignalR(mock_auth)
        client._stopped = True

        with patch.object(client, "_schedule_full_reconnect") as mock_reconnect:
            client._on_hub_close()
        mock_reconnect.assert_not_called()


# =========================================================================== #
# Client → server invocations
# =========================================================================== #


class TestClientToServer:
    def test_mark_as_delivered(self, signalr_client):
        client, mock_hub, _ = signalr_client
        client.start()

        msg_id = UUID(MSG_ID)
        conv_id = UUID(CONV_ID)
        client.mark_as_delivered(msg_id, conv_id)

        mock_hub.send.assert_called_once_with(
            "MarkAsDelivered",
            [str(conv_id), str(msg_id)],
            None,
        )

    def test_mark_as_read(self, signalr_client):
        client, mock_hub, _ = signalr_client
        client.start()

        msg_id = UUID(MSG_ID)
        conv_id = UUID(CONV_ID)
        client.mark_as_read(msg_id, conv_id)

        mock_hub.send.assert_called_once_with(
            "MarkAsRead",
            [str(conv_id), str(msg_id)],
            None,
        )

    def test_query_network_properties_no_callback(self, signalr_client):
        client, mock_hub, _ = signalr_client
        client.start()

        client.query_network_properties()

        mock_hub.send.assert_called_once_with("NetworkProperties", [], None)

    def test_query_network_properties_with_callback(self, signalr_client):
        client, mock_hub, _ = signalr_client
        client.start()

        callback = MagicMock()
        client.query_network_properties(callback=callback)

        mock_hub.send.assert_called_once()
        call_args = mock_hub.send.call_args
        assert call_args[0][0] == "NetworkProperties"
        assert call_args[0][1] == []

        # Simulate the hub invoking the result callback
        result_cb = call_args[0][2]
        result_cb({"dataConstrained": True, "enablesPremiumMessaging": False})

        callback.assert_called_once()
        resp = callback.call_args[0][0]
        assert isinstance(resp, NetworkPropertiesResponse)
        assert resp.dataConstrained is True
        assert resp.enablesPremiumMessaging is False

    def test_query_network_properties_callback_bad_data(self, signalr_client):
        """Callback with unparseable data should log error, not raise."""
        client, mock_hub, _ = signalr_client
        client.start()

        callback = MagicMock()
        client.query_network_properties(callback=callback)

        result_cb = mock_hub.send.call_args[0][2]
        result_cb(None)  # invalid data

        callback.assert_not_called()

    def test_mark_as_delivered_with_callback(self, signalr_client):
        client, mock_hub, _ = signalr_client
        client.start()

        callback = MagicMock()
        msg_id = UUID(MSG_ID)
        conv_id = UUID(CONV_ID)
        client.mark_as_delivered(msg_id, conv_id, callback=callback)

        mock_hub.send.assert_called_once_with(
            "MarkAsDelivered",
            [str(conv_id), str(msg_id)],
            callback,
        )


# =========================================================================== #
# Reconnection
# =========================================================================== #


class TestReconnection:
    def test_schedule_reconnect_starts_thread(self, mock_auth):
        client = HermesSignalR(mock_auth)
        client._stopped = False

        with patch.object(client, "_full_reconnect_loop"):
            client._schedule_full_reconnect()

        assert client._reconnect_thread is not None
        # Wait briefly for thread to start
        client._reconnect_thread.join(timeout=1)

    def test_schedule_reconnect_no_duplicate(self, mock_auth):
        client = HermesSignalR(mock_auth)

        # Simulate an alive thread
        alive_thread = MagicMock(spec=threading.Thread)
        alive_thread.is_alive.return_value = True
        client._reconnect_thread = alive_thread

        client._schedule_full_reconnect()
        # Should not have replaced the thread
        assert client._reconnect_thread is alive_thread

    def test_full_reconnect_loop_exits_when_stopped(self, mock_auth, monkeypatch):
        monkeypatch.setattr("garmin_messenger.signalr.time.sleep", lambda _: None)

        client = HermesSignalR(mock_auth)
        client._stopped = True

        # Should exit immediately
        client._full_reconnect_loop()

    def test_full_reconnect_loop_rebuilds_hub(self, mock_auth, monkeypatch):
        monkeypatch.setattr("garmin_messenger.signalr.time.sleep", lambda _: None)

        client = HermesSignalR(mock_auth)
        client._stopped = False

        old_hub = MagicMock()
        client._hub = old_hub

        new_hub = MagicMock()

        with patch.object(client, "_build_hub") as mock_build:
            def set_new_hub():
                client._hub = new_hub
            mock_build.side_effect = set_new_hub

            client._full_reconnect_loop()

        old_hub.stop.assert_called_once()
        mock_build.assert_called_once()
        new_hub.start.assert_called_once()

    def test_full_reconnect_loop_retries_on_token_failure(self, mock_auth, monkeypatch):
        sleeps = []
        monkeypatch.setattr("garmin_messenger.signalr.time.sleep", lambda s: sleeps.append(s))

        client = HermesSignalR(mock_auth)
        client._stopped = False
        mock_auth.expires_at = 0  # make token expired

        refresh_calls = []
        def failing_refresh():
            refresh_calls.append(1)
            if len(refresh_calls) >= 2:
                client._stopped = True
            raise RuntimeError("refresh failed")

        mock_auth.refresh_hermes_token = failing_refresh

        client._full_reconnect_loop()

        assert len(refresh_calls) == 2
        # Second delay should be double the first (exponential backoff)
        assert sleeps[1] == sleeps[0] * 2

    def test_full_reconnect_loop_retries_on_build_failure(self, mock_auth, monkeypatch):
        sleeps = []
        monkeypatch.setattr("garmin_messenger.signalr.time.sleep", lambda s: sleeps.append(s))

        client = HermesSignalR(mock_auth)
        client._stopped = False

        build_calls = []
        with patch.object(client, "_build_hub") as mock_build:
            def failing_build():
                build_calls.append(1)
                if len(build_calls) >= 2:
                    client._stopped = True
                raise RuntimeError("build failed")
            mock_build.side_effect = failing_build

            client._full_reconnect_loop()

        assert len(build_calls) == 2
        assert sleeps[1] == sleeps[0] * 2

    def test_full_reconnect_loop_stops_old_hub_even_if_raises(self, mock_auth, monkeypatch):
        monkeypatch.setattr("garmin_messenger.signalr.time.sleep", lambda _: None)

        client = HermesSignalR(mock_auth)
        client._stopped = False

        old_hub = MagicMock()
        old_hub.stop.side_effect = Exception("already dead")
        client._hub = old_hub

        new_hub = MagicMock()
        with patch.object(client, "_build_hub") as mock_build:
            mock_build.side_effect = lambda: setattr(client, "_hub", new_hub)
            client._full_reconnect_loop()

        old_hub.stop.assert_called_once()
        new_hub.start.assert_called_once()


# =========================================================================== #
# Token factory
# =========================================================================== #


class TestTokenFactory:
    def test_returns_token_when_valid(self, signalr_client):
        client, mock_hub, mock_builder = signalr_client
        client.start()

        builder = mock_builder.return_value
        options = builder.with_url.call_args[1]["options"]
        token_factory = options["access_token_factory"]

        result = token_factory()
        assert result == client.auth.access_token

    def test_refreshes_expired_token(self, signalr_client):
        client, mock_hub, mock_builder = signalr_client
        client.start()

        builder = mock_builder.return_value
        options = builder.with_url.call_args[1]["options"]
        token_factory = options["access_token_factory"]

        # Make token expired
        client.auth.expires_at = 0
        client.auth.refresh_hermes_token = MagicMock()

        result = token_factory()
        client.auth.refresh_hermes_token.assert_called_once()
        assert result == client.auth.access_token

    def test_raises_on_refresh_failure(self, signalr_client):
        client, mock_hub, mock_builder = signalr_client
        client.start()

        builder = mock_builder.return_value
        options = builder.with_url.call_args[1]["options"]
        token_factory = options["access_token_factory"]

        client.auth.expires_at = 0
        client.auth.refresh_hermes_token = MagicMock(
            side_effect=RuntimeError("refresh failed")
        )

        with pytest.raises(RuntimeError, match="refresh failed"):
            token_factory()


# =========================================================================== #
# Stop edge cases
# =========================================================================== #


class TestStopEdgeCases:
    def test_stop_hub_raises_no_error(self, signalr_client):
        client, mock_hub, _ = signalr_client
        client.start()
        mock_hub.stop.side_effect = Exception("connection already closed")

        client.stop()  # should not raise
        assert client._stopped is True
