"""Garmin Messenger authentication: SMS OTP → Hermes JWT.

Uses the Registration/App path (same as the real Android app):
  1. request_otp()   → POST Registration/App  → SMS OTP sent to phone
  2. Caller collects OTP code (terminal prompt, GUI dialog, web form, …)
  3. confirm_otp()   → POST Registration/App/Confirm → Hermes JWT
  4. Auto-refresh via POST Registration/App/Refresh when expired
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import httpx

from garmin_messenger.models import (
    AccessAndRefreshToken,
    AppRegistrationResponse,
    ConfirmAppRegistrationBody,
    NewAppRegistrationBody,
    NewAppRegistrationResponse,
    OtpRequest,
    RefreshAuthBody,
)

log = logging.getLogger(__name__)

HERMES_BASE = "https://hermes.inreachapp.com"
REGISTRATION_API_KEY = "?E2PFAzUzKx!S&1k1D"


# ---------------------------------------------------------------------------
# Diagnostic helpers
# ---------------------------------------------------------------------------

def _dump_request(method: str, url: str, *,
                  headers: dict | None = None,
                  data: dict | None = None,
                  json_body: dict | None = None) -> None:
    """Log full details of an outgoing HTTP request."""
    log.debug(">>> %s %s", method, url)
    if headers:
        log.debug("  Request headers:")
        for k, v in headers.items():
            if len(str(v)) > 120:
                log.debug("    %s: %s…%s (%d chars)",
                         k, str(v)[:60], str(v)[-20:], len(str(v)))
            else:
                log.debug("    %s: %s", k, v)
    if data:
        log.debug("  Form data:")
        for k, v in data.items():
            log.debug("    %s = %s", k, v)
    if json_body:
        log.debug("  JSON body: %s", json.dumps(json_body, indent=2))


def _dump_response(resp: httpx.Response, *, body_limit: int = 2000) -> None:
    """Log full details of an HTTP response."""
    log.debug("<<< %d %s", resp.status_code, resp.reason_phrase)
    log.debug("  Response URL: %s", resp.url)
    log.debug("  Response headers:")
    for k, v in resp.headers.items():
        log.debug("    %s: %s", k, v)
    body = resp.text
    log.debug("  Response body length: %d chars", len(body))
    if len(body) <= body_limit:
        log.debug("  Response body:\n%s", body)
    else:
        log.debug("  Response body (first %d chars):\n%s",
                 body_limit, body[:body_limit])


# ---------------------------------------------------------------------------
# Auth class
# ---------------------------------------------------------------------------

class HermesAuth:
    """Manages the full authentication lifecycle for Hermes messaging API.

    SMS registration flow (two-step, headless):
        1. request_otp(phone)  → sends SMS, returns OtpRequest
        2. confirm_otp(otp_request, code) → exchanges OTP for Hermes JWT
        3. Auto-refresh via POST Registration/App/Refresh when expired
    """

    def __init__(
        self,
        hermes_base: str = HERMES_BASE,
        session_dir: str | None = None,
    ):
        self.hermes_base = hermes_base.rstrip("/")
        self.session_dir = session_dir

        # Hermes credentials (populated after registration)
        self.access_token: str | None = None
        self.refresh_token: str | None = None
        self.instance_id: str | None = None
        self.expires_at: float = 0.0  # unix timestamp

    # ----- public API --------------------------------------------------------

    def request_otp(
        self,
        phone_number: str,
        device_name: str = "garmin-messenger",
    ) -> OtpRequest:
        """Request an SMS OTP code for *phone_number*.

        Returns an :class:`OtpRequest` that must be passed to
        :meth:`confirm_otp` together with the code the user received.

        Args:
            phone_number: Phone number with country code (e.g. "+1234567890").
            device_name: Device identifier shown on the account
                         (default: "garmin-messenger").
        """
        log.debug("=" * 70)
        log.debug("STAGE 1: Request SMS OTP")
        log.debug("=" * 70)
        log.debug("  Phone: %s", phone_number)

        url = f"{self.hermes_base}/Registration/App"
        body = NewAppRegistrationBody(smsNumber=phone_number)
        req_headers = {
            "RegistrationApiKey": REGISTRATION_API_KEY,
            "Api-Version": "1.0",
            "Content-Type": "application/json",
        }
        req_json = body.model_dump()
        _dump_request("POST", url, headers=req_headers, json_body=req_json)

        resp = httpx.post(url, json=req_json, headers=req_headers)
        _dump_response(resp)
        if resp.status_code == 409:
            log.warning("Previous OTP request still active. Waiting 30s …")
            time.sleep(30)
            resp = httpx.post(url, json=req_json, headers=req_headers)
            _dump_response(resp)
        resp.raise_for_status()

        otp_resp = NewAppRegistrationResponse.model_validate(resp.json())
        log.debug("  requestId: %s", otp_resp.requestId)
        log.debug("  validUntil: %s", otp_resp.validUntil)
        log.debug("  attemptsRemaining: %s", otp_resp.attemptsRemaining)

        return OtpRequest(
            request_id=otp_resp.requestId,
            phone_number=phone_number,
            device_name=device_name,
            valid_until=otp_resp.validUntil,
            attempts_remaining=otp_resp.attemptsRemaining,
        )

    def confirm_otp(self, otp_request: OtpRequest, otp_code: str) -> None:
        """Confirm registration with the SMS OTP code.

        Args:
            otp_request: The :class:`OtpRequest` returned by :meth:`request_otp`.
            otp_code: The 6-digit OTP code the user received via SMS.
        """
        log.debug("=" * 70)
        log.debug("STAGE 3: Confirm registration with OTP")
        log.debug("=" * 70)

        url = f"{self.hermes_base}/Registration/App/Confirm"
        req_headers = {
            "RegistrationApiKey": REGISTRATION_API_KEY,
            "Api-Version": "1.0",
            "Content-Type": "application/json",
        }
        confirm_body = ConfirmAppRegistrationBody(
            requestId=otp_request.request_id,
            smsNumber=otp_request.phone_number,
            verificationCode=otp_code,
            appDescription=otp_request.device_name,
        )
        req_json = confirm_body.model_dump()
        _dump_request("POST", url, headers=req_headers, json_body=req_json)

        resp = httpx.post(url, json=req_json, headers=req_headers)
        _dump_response(resp)
        resp.raise_for_status()

        reg = AppRegistrationResponse.model_validate(resp.json())
        log.debug("Hermes registration response:")
        log.debug("  instanceId: %s", reg.instanceId)
        log.debug("  accessToken length: %d",
                 len(reg.accessAndRefreshToken.accessToken))
        log.debug("  refreshToken length: %d",
                 len(reg.accessAndRefreshToken.refreshToken))
        log.debug("  expiresIn: %d seconds",
                 reg.accessAndRefreshToken.expiresIn)
        if reg.smsOptInResult:
            log.debug("  smsOptInResult: success=%s fatalError=%s",
                     reg.smsOptInResult.success, reg.smsOptInResult.fatalError)

        self._store_credentials(reg.instanceId, reg.accessAndRefreshToken)
        log.debug("Registration successful (instance=%s)", self.instance_id)

    def resume(self, session_dir: str | None = None) -> None:
        """Resume from stored Hermes credentials."""
        d = session_dir or self.session_dir

        creds_path = self._creds_path(d)
        if creds_path and creds_path.exists():
            data = json.loads(creds_path.read_text())
            self.access_token = data["access_token"]
            self.refresh_token = data["refresh_token"]
            self.instance_id = data["instance_id"]
            self.expires_at = data["expires_at"]
            log.debug("Resumed Hermes credentials (instance=%s)",
                     self.instance_id)
            log.debug("  Token expires at: %s (in %.0f seconds)",
                     time.strftime("%Y-%m-%d %H:%M:%S UTC",
                                   time.gmtime(self.expires_at)),
                     self.expires_at - time.time())

            if self.token_expired:
                self.refresh_hermes_token()
        else:
            raise RuntimeError(
                f"No saved credentials found at {creds_path}. "
                "Call request_otp() + confirm_otp() first."
            )

    def headers(self) -> dict[str, str]:
        """Return auth headers for Hermes REST API requests.

        Note: The Android app's Retrofit interface uses a custom ``AccessToken``
        header, but an OkHttp interceptor (sfe.java:70-89) rewrites it to the
        standard ``Authorization: Bearer <token>`` before sending.
        """
        if self.token_expired:
            self.refresh_hermes_token()
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Api-Version": "2.0",
        }

    @property
    def token_expired(self) -> bool:
        if not self.access_token:
            return True
        return time.time() >= self.expires_at - 60  # 60s buffer

    def refresh_hermes_token(self) -> None:
        """Refresh the Hermes access token."""
        if not self.refresh_token or not self.instance_id:
            raise RuntimeError(
                "No refresh token / instance ID. "
                "Call request_otp() + confirm_otp() first."
            )
        log.debug("Refreshing Hermes token …")
        body = RefreshAuthBody(
            refreshToken=self.refresh_token,
            instanceId=self.instance_id,
        )
        url = f"{self.hermes_base}/Registration/App/Refresh"
        req_headers = {"Api-Version": "1.0"}
        req_json = body.model_dump()
        _dump_request("POST", url, headers=req_headers, json_body=req_json)
        resp = httpx.post(url, json=req_json, headers=req_headers)
        _dump_response(resp)
        resp.raise_for_status()
        reg = AppRegistrationResponse.model_validate(resp.json())
        self._store_credentials(reg.instanceId, reg.accessAndRefreshToken)

    # ----- internal ----------------------------------------------------------

    def _store_credentials(
        self,
        instance_id: str,
        tokens: AccessAndRefreshToken,
    ) -> None:
        self.access_token = tokens.accessToken
        self.refresh_token = tokens.refreshToken
        self.instance_id = instance_id
        self.expires_at = time.time() + tokens.expiresIn

        creds_path = self._creds_path(self.session_dir)
        if creds_path:
            creds_path.parent.mkdir(parents=True, exist_ok=True)
            creds_path.write_text(
                json.dumps(
                    {
                        "access_token": self.access_token,
                        "refresh_token": self.refresh_token,
                        "instance_id": self.instance_id,
                        "expires_at": self.expires_at,
                    },
                    indent=2,
                )
            )
            log.debug("Saved Hermes credentials to %s", creds_path)

    @staticmethod
    def _creds_path(session_dir: str | None) -> Path | None:
        if not session_dir:
            return None
        return Path(session_dir) / "hermes_credentials.json"
