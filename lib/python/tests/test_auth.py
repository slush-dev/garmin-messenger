"""Tests for garmin_messenger.auth — HermesAuth lifecycle."""

from __future__ import annotations

import json
import time

import httpx
import pytest

from garmin_messenger.auth import HERMES_BASE, HermesAuth
from garmin_messenger.models import OtpRequest

from .conftest import ACCESS_TOKEN, INSTANCE_ID, REFRESH_TOKEN

# =========================================================================== #
# Initialization
# =========================================================================== #


class TestAuthInit:
    def test_defaults(self):
        auth = HermesAuth()
        assert auth.hermes_base == HERMES_BASE
        assert auth.session_dir is None
        assert auth.access_token is None
        assert auth.refresh_token is None
        assert auth.instance_id is None
        assert auth.expires_at == 0.0

    def test_custom_base_strips_slash(self):
        auth = HermesAuth(hermes_base="https://example.com/")
        assert auth.hermes_base == "https://example.com"

    def test_with_session_dir(self, tmp_path):
        auth = HermesAuth(session_dir=str(tmp_path))
        assert auth.session_dir == str(tmp_path)


# =========================================================================== #
# token_expired property
# =========================================================================== #


class TestTokenExpired:
    def test_no_token(self):
        auth = HermesAuth()
        assert auth.token_expired is True

    def test_expired_past(self):
        auth = HermesAuth()
        auth.access_token = "tok"
        auth.expires_at = time.time() - 100
        assert auth.token_expired is True

    def test_within_buffer(self):
        """Token expiring within 60s buffer is considered expired."""
        auth = HermesAuth()
        auth.access_token = "tok"
        auth.expires_at = time.time() + 30  # within 60s buffer
        assert auth.token_expired is True

    def test_not_expired(self):
        auth = HermesAuth()
        auth.access_token = "tok"
        auth.expires_at = time.time() + 3600
        assert auth.token_expired is False


# =========================================================================== #
# request_otp
# =========================================================================== #


class TestRequestOtp:
    def test_returns_otp_request(self, httpx_mock, sample_otp_response):
        httpx_mock.add_response(
            method="POST",
            url=f"{HERMES_BASE}/Registration/App",
            json=sample_otp_response,
        )

        auth = HermesAuth()
        result = auth.request_otp("+15551234567")

        assert isinstance(result, OtpRequest)
        assert result.request_id == "req-abc-123"
        assert result.phone_number == "+15551234567"
        assert result.device_name == "garmin-messenger"
        assert result.valid_until == "2025-06-01T12:00:00Z"
        assert result.attempts_remaining == 3

    def test_409_retry(self, httpx_mock, monkeypatch, sample_otp_response):
        monkeypatch.setattr("garmin_messenger.auth.time.sleep", lambda _: None)

        httpx_mock.add_response(
            method="POST",
            url=f"{HERMES_BASE}/Registration/App",
            status_code=409,
        )
        httpx_mock.add_response(
            method="POST",
            url=f"{HERMES_BASE}/Registration/App",
            json=sample_otp_response,
        )

        auth = HermesAuth()
        result = auth.request_otp("+15551234567")

        assert result.request_id == "req-abc-123"
        requests = httpx_mock.get_requests()
        assert len(requests) == 2

    def test_409_double_failure(self, httpx_mock, monkeypatch):
        monkeypatch.setattr("garmin_messenger.auth.time.sleep", lambda _: None)

        httpx_mock.add_response(
            method="POST",
            url=f"{HERMES_BASE}/Registration/App",
            status_code=409,
        )
        httpx_mock.add_response(
            method="POST",
            url=f"{HERMES_BASE}/Registration/App",
            status_code=409,
        )

        auth = HermesAuth()
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            auth.request_otp("+15551234567")
        assert exc_info.value.response.status_code == 409

    def test_correct_request_body(self, httpx_mock, sample_otp_response):
        httpx_mock.add_response(
            method="POST",
            url=f"{HERMES_BASE}/Registration/App",
            json=sample_otp_response,
        )

        auth = HermesAuth()
        auth.request_otp("+15551234567")

        req = httpx_mock.get_requests()[0]
        body = json.loads(req.content)
        assert body["smsNumber"] == "+15551234567"
        assert body["platform"] == "android"
        assert req.headers["RegistrationApiKey"] is not None
        assert req.headers["Api-Version"] == "1.0"


# =========================================================================== #
# confirm_otp
# =========================================================================== #


class TestConfirmOtp:
    def _make_otp_request(self, **overrides):
        defaults = {
            "request_id": "req-abc-123",
            "phone_number": "+15551234567",
            "device_name": "garmin-messenger",
            "valid_until": "2025-06-01T12:00:00Z",
            "attempts_remaining": 3,
        }
        defaults.update(overrides)
        return OtpRequest(**defaults)

    def test_happy_path(self, httpx_mock, tmp_path,
                        sample_registration_response):
        httpx_mock.add_response(
            method="POST",
            url=f"{HERMES_BASE}/Registration/App/Confirm",
            json=sample_registration_response,
        )

        auth = HermesAuth(session_dir=str(tmp_path))
        auth.confirm_otp(self._make_otp_request(), "123456")

        assert auth.access_token == ACCESS_TOKEN
        assert auth.refresh_token == REFRESH_TOKEN
        assert auth.instance_id == INSTANCE_ID
        assert auth.expires_at > time.time()

    def test_stores_credentials_to_disk(self, httpx_mock, tmp_path,
                                        sample_registration_response):
        httpx_mock.add_response(
            method="POST",
            url=f"{HERMES_BASE}/Registration/App/Confirm",
            json=sample_registration_response,
        )

        auth = HermesAuth(session_dir=str(tmp_path))
        auth.confirm_otp(self._make_otp_request(), "999999")

        creds_file = tmp_path / "hermes_credentials.json"
        assert creds_file.exists()
        data = json.loads(creds_file.read_text())
        assert data["access_token"] == ACCESS_TOKEN
        assert data["refresh_token"] == REFRESH_TOKEN
        assert data["instance_id"] == INSTANCE_ID
        assert "expires_at" in data

    def test_no_session_dir(self, httpx_mock, sample_registration_response):
        httpx_mock.add_response(
            method="POST",
            url=f"{HERMES_BASE}/Registration/App/Confirm",
            json=sample_registration_response,
        )

        auth = HermesAuth()  # no session_dir
        auth.confirm_otp(self._make_otp_request(), "123456")
        assert auth.access_token == ACCESS_TOKEN

    def test_correct_request_body(self, httpx_mock,
                                  sample_registration_response):
        httpx_mock.add_response(
            method="POST",
            url=f"{HERMES_BASE}/Registration/App/Confirm",
            json=sample_registration_response,
        )

        auth = HermesAuth()
        auth.confirm_otp(self._make_otp_request(), "654321")

        req = httpx_mock.get_requests()[0]
        body = json.loads(req.content)
        assert body["requestId"] == "req-abc-123"
        assert body["smsNumber"] == "+15551234567"
        assert body["verificationCode"] == "654321"
        assert body["platform"] == "android"
        assert body["appDescription"] == "garmin-messenger"

    def test_custom_device_name(self, httpx_mock,
                                sample_registration_response):
        httpx_mock.add_response(
            method="POST",
            url=f"{HERMES_BASE}/Registration/App/Confirm",
            json=sample_registration_response,
        )

        auth = HermesAuth()
        otp_req = self._make_otp_request(device_name="my-laptop")
        auth.confirm_otp(otp_req, "654321")

        req = httpx_mock.get_requests()[0]
        body = json.loads(req.content)
        assert body["appDescription"] == "my-laptop"


# =========================================================================== #
# resume
# =========================================================================== #


class TestResume:
    def test_loads_credentials(self, tmp_path):
        creds = {
            "access_token": ACCESS_TOKEN,
            "refresh_token": REFRESH_TOKEN,
            "instance_id": INSTANCE_ID,
            "expires_at": time.time() + 7200,
        }
        (tmp_path / "hermes_credentials.json").write_text(json.dumps(creds))

        auth = HermesAuth(session_dir=str(tmp_path))
        auth.resume()

        assert auth.access_token == ACCESS_TOKEN
        assert auth.refresh_token == REFRESH_TOKEN
        assert auth.instance_id == INSTANCE_ID

    def test_refreshes_expired_token(self, httpx_mock, tmp_path,
                                     sample_registration_response):
        creds = {
            "access_token": "old-token",
            "refresh_token": REFRESH_TOKEN,
            "instance_id": INSTANCE_ID,
            "expires_at": time.time() - 100,  # expired
        }
        (tmp_path / "hermes_credentials.json").write_text(json.dumps(creds))

        httpx_mock.add_response(
            method="POST",
            url=f"{HERMES_BASE}/Registration/App/Refresh",
            json=sample_registration_response,
        )

        auth = HermesAuth(session_dir=str(tmp_path))
        auth.resume()

        assert auth.access_token == ACCESS_TOKEN  # refreshed
        assert len(httpx_mock.get_requests()) == 1

    def test_with_session_dir_override(self, tmp_path):
        other_dir = tmp_path / "other"
        other_dir.mkdir()
        creds = {
            "access_token": ACCESS_TOKEN,
            "refresh_token": REFRESH_TOKEN,
            "instance_id": INSTANCE_ID,
            "expires_at": time.time() + 7200,
        }
        (other_dir / "hermes_credentials.json").write_text(json.dumps(creds))

        auth = HermesAuth()  # no session_dir
        auth.resume(session_dir=str(other_dir))

        assert auth.access_token == ACCESS_TOKEN
        assert auth.instance_id == INSTANCE_ID

    def test_no_file_raises(self, tmp_path):
        auth = HermesAuth(session_dir=str(tmp_path))
        with pytest.raises(RuntimeError, match="No saved credentials"):
            auth.resume()


# =========================================================================== #
# headers
# =========================================================================== #


class TestHeaders:
    def test_returns_bearer(self, mock_auth):
        h = mock_auth.headers()
        assert h["Authorization"] == f"Bearer {ACCESS_TOKEN}"
        assert h["Api-Version"] == "2.0"

    def test_triggers_refresh(self, httpx_mock, mock_expired_auth,
                              sample_registration_response):
        httpx_mock.add_response(
            method="POST",
            url=f"{HERMES_BASE}/Registration/App/Refresh",
            json=sample_registration_response,
        )

        h = mock_expired_auth.headers()
        assert "Bearer" in h["Authorization"]
        assert len(httpx_mock.get_requests()) == 1


# =========================================================================== #
# refresh_hermes_token
# =========================================================================== #


class TestRefreshHermesToken:
    def test_happy_path(self, httpx_mock, mock_auth, sample_registration_response):
        httpx_mock.add_response(
            method="POST",
            url=f"{HERMES_BASE}/Registration/App/Refresh",
            json=sample_registration_response,
        )

        mock_auth.refresh_hermes_token()

        assert mock_auth.access_token == ACCESS_TOKEN
        req = httpx_mock.get_requests()[0]
        body = json.loads(req.content)
        assert body["refreshToken"] == REFRESH_TOKEN
        assert body["instanceId"] == INSTANCE_ID

    def test_no_credentials_raises(self):
        auth = HermesAuth()
        with pytest.raises(RuntimeError, match="No refresh token"):
            auth.refresh_hermes_token()

    def test_persists_to_disk(self, httpx_mock, tmp_path,
                              sample_registration_response):
        httpx_mock.add_response(
            method="POST",
            url=f"{HERMES_BASE}/Registration/App/Refresh",
            json=sample_registration_response,
        )

        auth = HermesAuth(session_dir=str(tmp_path))
        auth.access_token = "old"
        auth.refresh_token = REFRESH_TOKEN
        auth.instance_id = INSTANCE_ID
        auth.expires_at = time.time() + 100

        auth.refresh_hermes_token()

        creds_file = tmp_path / "hermes_credentials.json"
        assert creds_file.exists()
        data = json.loads(creds_file.read_text())
        assert data["access_token"] == ACCESS_TOKEN


# =========================================================================== #
# _creds_path
# =========================================================================== #


class TestCredsPath:
    def test_with_session_dir(self, tmp_path):
        p = HermesAuth._creds_path(str(tmp_path))
        assert p is not None
        assert p.name == "hermes_credentials.json"

    def test_without_session_dir(self):
        assert HermesAuth._creds_path(None) is None
