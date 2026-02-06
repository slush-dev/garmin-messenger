"""SignalR real-time client for Garmin Hermes messaging.

Connects via WebSocket to hermes.inreachapp.com for push notifications
of new messages, status updates, and server events.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import Any
from uuid import UUID

from signalrcore.hub_connection_builder import HubConnectionBuilder

from garmin_messenger.auth import HermesAuth
from garmin_messenger.models import (
    ConversationMuteStatusUpdate,
    MessageModel,
    MessageStatusUpdate,
    NetworkPropertiesResponse,
    ServerNotification,
    UserBlockStatusUpdate,
)

log = logging.getLogger(__name__)

# SignalR hub path (Microsoft SignalR convention)
HUB_PATH = "/messaging"

# Reconnection settings (for when signalrcore's built-in reconnect gives up)
_RECONNECT_BASE_DELAY = 5      # seconds
_RECONNECT_MAX_DELAY = 120     # seconds
_RECONNECT_BACKOFF = 2         # multiplier


class HermesSignalR:
    """SignalR WebSocket client for real-time Hermes events.

    Server → Client methods:
        ReceiveMessage, ReceiveMessageUpdate,
        ReceiveConversationMuteStatusUpdate,
        ReceiveUserBlockStatusUpdate, ReceiveServerNotification,
        ReceiveNonconversationalMessage

    Client → Server methods:
        MarkAsDelivered, MarkAsRead, NetworkProperties

    Handles reconnection after network disruptions (e.g. system suspend)
    by rebuilding the hub connection from scratch when the library's
    built-in reconnect exhausts its attempts.
    """

    def __init__(self, auth: HermesAuth):
        self.auth = auth
        self._hub = None
        self._on_message: Callable[[MessageModel], Any] | None = None
        self._on_status_update: Callable[[MessageStatusUpdate], Any] | None = None
        self._on_mute_update: Callable[[ConversationMuteStatusUpdate], Any] | None = None
        self._on_block_update: Callable[[UserBlockStatusUpdate], Any] | None = None
        self._on_notification: Callable[[ServerNotification], Any] | None = None
        self._on_nonconversational_message: Callable[[str], Any] | None = None
        self._on_open: Callable[[], Any] | None = None
        self._on_close: Callable[[], Any] | None = None
        self._on_error: Callable[[Any], Any] | None = None
        self._stopped = False
        self._reconnect_thread: threading.Thread | None = None

    # ----- event registration ------------------------------------------------

    def on_message(self, handler: Callable[[MessageModel], Any]) -> None:
        """Register handler for incoming messages (ReceiveMessage)."""
        self._on_message = handler

    def on_status_update(self, handler: Callable[[MessageStatusUpdate], Any]) -> None:
        """Register handler for message status changes (ReceiveMessageUpdate)."""
        self._on_status_update = handler

    def on_mute_update(
        self, handler: Callable[[ConversationMuteStatusUpdate], Any]
    ) -> None:
        self._on_mute_update = handler

    def on_block_update(self, handler: Callable[[UserBlockStatusUpdate], Any]) -> None:
        self._on_block_update = handler

    def on_notification(self, handler: Callable[[ServerNotification], Any]) -> None:
        self._on_notification = handler

    def on_nonconversational_message(self, handler: Callable[[str], Any]) -> None:
        """Register handler for device system messages (ReceiveNonconversationalMessage).

        The handler receives an IMEI string identifying the InReach device.
        """
        self._on_nonconversational_message = handler

    def on_open(self, handler: Callable[[], Any]) -> None:
        self._on_open = handler

    def on_close(self, handler: Callable[[], Any]) -> None:
        self._on_close = handler

    def on_error(self, handler: Callable[[Any], Any]) -> None:
        self._on_error = handler

    # ----- connection --------------------------------------------------------

    def _build_hub(self) -> None:
        """Build (or rebuild) the SignalR hub connection object."""
        hub_url = f"{self.auth.hermes_base}{HUB_PATH}"
        log.debug("Building SignalR hub for %s", hub_url)

        def token_factory() -> str:
            try:
                if self.auth.token_expired:
                    self.auth.refresh_hermes_token()
            except Exception:
                log.exception("Token refresh failed in token_factory")
                raise
            return self.auth.access_token

        self._hub = (
            HubConnectionBuilder()
            .with_url(
                hub_url,
                options={
                    "access_token_factory": token_factory,
                },
            )
            .with_automatic_reconnect(
                {
                    "type": "raw",
                    "keep_alive_interval": 15,
                    "reconnect_interval": 5,
                    "max_attempts": 5,
                }
            )
            .build()
        )

        # Wire up server → client handlers
        self._hub.on("ReceiveMessage", self._handle_message)
        self._hub.on("ReceiveMessageUpdate", self._handle_status_update)
        self._hub.on(
            "ReceiveConversationMuteStatusUpdate", self._handle_mute_update
        )
        self._hub.on("ReceiveUserBlockStatusUpdate", self._handle_block_update)
        self._hub.on("ReceiveServerNotification", self._handle_notification)
        self._hub.on(
            "ReceiveNonconversationalMessage",
            self._handle_nonconversational_message,
        )

        self._hub.on_open(self._on_hub_open)
        self._hub.on_close(self._on_hub_close)
        self._hub.on_error(self._handle_error)

    def start(self) -> None:
        """Build and start the SignalR hub connection."""
        self._stopped = False
        self._build_hub()
        self._hub.start()
        log.debug("SignalR connected")

    def stop(self) -> None:
        """Stop the SignalR connection and disable auto-reconnect."""
        self._stopped = True
        if self._hub:
            try:
                self._hub.stop()
            except Exception:
                pass
            log.debug("SignalR disconnected")

    def _on_hub_open(self) -> None:
        log.debug("SignalR connection opened")
        if self._on_open:
            self._on_open()

    def _on_hub_close(self) -> None:
        log.debug("SignalR connection closed")
        if self._on_close:
            self._on_close()
        # If we didn't explicitly stop, the library's built-in reconnect
        # has exhausted its attempts. Kick off a full rebuild.
        if not self._stopped:
            self._schedule_full_reconnect()

    def _schedule_full_reconnect(self) -> None:
        """Start a background thread that rebuilds the connection with backoff."""
        if (
            self._reconnect_thread is not None
            and self._reconnect_thread.is_alive()
        ):
            return  # already trying
        self._reconnect_thread = threading.Thread(
            target=self._full_reconnect_loop, daemon=True
        )
        self._reconnect_thread.start()

    def _full_reconnect_loop(self) -> None:
        """Tear down and rebuild the hub connection with exponential backoff."""
        delay = _RECONNECT_BASE_DELAY
        while not self._stopped:
            log.debug(
                "Full reconnect: waiting %ds before rebuilding connection …",
                delay,
            )
            time.sleep(delay)
            if self._stopped:
                return

            # Ensure token is fresh before attempting reconnect
            try:
                if self.auth.token_expired:
                    log.debug("Full reconnect: refreshing expired token …")
                    self.auth.refresh_hermes_token()
            except Exception:
                log.warning(
                    "Full reconnect: token refresh failed, will retry",
                    exc_info=True,
                )
                delay = min(delay * _RECONNECT_BACKOFF, _RECONNECT_MAX_DELAY)
                continue

            try:
                # Tear down the old hub (ignore errors — it's already dead)
                if self._hub:
                    try:
                        self._hub.stop()
                    except Exception:
                        pass

                self._build_hub()
                self._hub.start()
                log.debug("Full reconnect: connection re-established")
                return  # success — exit the loop
            except Exception:
                log.warning(
                    "Full reconnect: failed to rebuild connection, will retry",
                    exc_info=True,
                )
                delay = min(delay * _RECONNECT_BACKOFF, _RECONNECT_MAX_DELAY)

    # ----- client → server invocations ---------------------------------------

    def mark_as_delivered(
        self,
        message_id: UUID,
        conversation_id: UUID,
        callback: Callable | None = None,
    ) -> None:
        """Invoke MarkAsDelivered on the server."""
        self._hub.send(
            "MarkAsDelivered",
            [str(conversation_id), str(message_id)],
            callback,
        )

    def mark_as_read(
        self,
        message_id: UUID,
        conversation_id: UUID,
        callback: Callable | None = None,
    ) -> None:
        """Invoke MarkAsRead on the server."""
        self._hub.send(
            "MarkAsRead",
            [str(conversation_id), str(message_id)],
            callback,
        )

    def query_network_properties(
        self,
        callback: Callable[[NetworkPropertiesResponse], Any] | None = None,
    ) -> None:
        """Invoke NetworkProperties on the server.

        The callback receives a ``NetworkPropertiesResponse`` with
        ``dataConstrained`` and ``enablesPremiumMessaging`` flags.
        """
        def _on_result(raw):
            if callback:
                try:
                    result = NetworkPropertiesResponse.model_validate(raw)
                    callback(result)
                except Exception:
                    log.exception("Error parsing NetworkProperties response")
        self._hub.send("NetworkProperties", [], _on_result if callback else None)

    # ----- internal handlers -------------------------------------------------

    def _handle_message(self, args: list) -> None:
        try:
            data = args[0] if args else args
            msg = MessageModel.model_validate(data)
            log.debug("ReceiveMessage: %s", msg.messageId)
            if self._on_message:
                self._on_message(msg)
        except Exception:
            log.exception("Error handling ReceiveMessage")

    def _handle_status_update(self, args: list) -> None:
        try:
            data = args[0] if args else args
            update = MessageStatusUpdate.model_validate(data)
            log.debug("ReceiveMessageUpdate: %s", update.messageId)
            if self._on_status_update:
                self._on_status_update(update)
        except Exception:
            log.exception("Error handling ReceiveMessageUpdate")

    def _handle_mute_update(self, args: list) -> None:
        try:
            data = args[0] if args else args
            update = ConversationMuteStatusUpdate.model_validate(data)
            if self._on_mute_update:
                self._on_mute_update(update)
        except Exception:
            log.exception("Error handling ReceiveConversationMuteStatusUpdate")

    def _handle_block_update(self, args: list) -> None:
        try:
            data = args[0] if args else args
            update = UserBlockStatusUpdate.model_validate(data)
            if self._on_block_update:
                self._on_block_update(update)
        except Exception:
            log.exception("Error handling ReceiveUserBlockStatusUpdate")

    def _handle_notification(self, args: list) -> None:
        try:
            data = args[0] if args else args
            notif = ServerNotification.model_validate(data)
            log.debug("ServerNotification: %s", notif)
            if self._on_notification:
                self._on_notification(notif)
        except Exception:
            log.exception("Error handling ReceiveServerNotification")

    def _handle_nonconversational_message(self, args: list) -> None:
        try:
            imei = str(args[0]) if args else ""
            log.debug("ReceiveNonconversationalMessage: IMEI=%s", imei)
            if self._on_nonconversational_message:
                self._on_nonconversational_message(imei)
        except Exception:
            log.exception("Error handling ReceiveNonconversationalMessage")

    def _handle_error(self, error) -> None:
        log.error("SignalR error: %s", error)
        if self._on_error:
            self._on_error(error)
