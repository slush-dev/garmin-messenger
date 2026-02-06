"""Tests for _generate_ota_uuid — Garmin's custom UUID bit layout."""

from __future__ import annotations

from uuid import UUID

import pytest

from garmin_messenger.api import _generate_ota_uuid


class TestOtaUuid:
    def test_returns_uuid_type(self):
        result = _generate_ota_uuid()
        assert isinstance(result, UUID)

    def test_deterministic_with_fixed_inputs(self):
        """Fixed timestamp + random_value should produce a deterministic UUID."""
        u1 = _generate_ota_uuid(timestamp=0x12345678, random_value=0xAABBCCDDEEFF0011)
        u2 = _generate_ota_uuid(timestamp=0x12345678, random_value=0xAABBCCDDEEFF0011)
        assert u1 == u2

    def test_timestamp_in_first_4_bytes(self):
        ts = 0x12345678
        u = _generate_ota_uuid(timestamp=ts, random_value=0)
        raw = u.bytes
        assert raw[0:4] == ts.to_bytes(4, "big")

    def test_fixed_marker_bits(self):
        """Bytes 6, 8, and 14 have 0x80 marker set in high bit."""
        u = _generate_ota_uuid(timestamp=0, random_value=0)
        raw = u.bytes
        assert raw[6] & 0x80 == 0x80
        assert raw[8] & 0x80 == 0x80
        assert raw[14] & 0x80 == 0x80

    def test_random_bytes_placement(self):
        rand = 0x0102030405060708
        u = _generate_ota_uuid(timestamp=0, random_value=rand)
        raw = u.bytes
        rand_bytes = rand.to_bytes(8, "big")
        assert raw[4] == rand_bytes[0]   # 0x01
        assert raw[5] == rand_bytes[1]   # 0x02
        assert raw[7] == rand_bytes[2]   # 0x03
        assert raw[9] == rand_bytes[3]   # 0x04
        assert raw[10] == rand_bytes[4]  # 0x05
        assert raw[11] == rand_bytes[5]  # 0x06
        assert raw[12] == rand_bytes[6]  # 0x07
        assert raw[13] == rand_bytes[7]  # 0x08

    def test_group_index_valid_range(self):
        for gi in range(15):  # 0..14
            u = _generate_ota_uuid(timestamp=0, random_value=0, group_index=gi)
            raw = u.bytes
            assert raw[6] & 0x0F == (gi + 1) & 0x0F

    def test_group_index_out_of_range(self):
        with pytest.raises(ValueError, match="group_index"):
            _generate_ota_uuid(group_index=15)
        with pytest.raises(ValueError, match="group_index"):
            _generate_ota_uuid(group_index=-1)

    def test_fragment_index_valid_range(self):
        for fi in range(31):  # 0..30
            u = _generate_ota_uuid(timestamp=0, random_value=0, fragment_index=fi)
            raw = u.bytes
            assert raw[8] & 0x1F == (fi + 1) & 0x1F

    def test_fragment_index_out_of_range(self):
        with pytest.raises(ValueError, match="fragment_index"):
            _generate_ota_uuid(fragment_index=31)
        with pytest.raises(ValueError, match="fragment_index"):
            _generate_ota_uuid(fragment_index=-1)

    def test_reserved1_validation(self):
        _generate_ota_uuid(reserved1=0)  # ok
        _generate_ota_uuid(reserved1=1)  # ok
        with pytest.raises(ValueError, match="reserved1"):
            _generate_ota_uuid(reserved1=2)

    def test_reserved1_encoding(self):
        u = _generate_ota_uuid(timestamp=0, random_value=0, reserved1=1)
        raw = u.bytes
        assert raw[8] & 0x20 == 0x20  # bit 5 set

    def test_reserved2_validation(self):
        _generate_ota_uuid(reserved2=0)      # ok
        _generate_ota_uuid(reserved2=16383)  # ok (2^14 - 1)
        with pytest.raises(ValueError, match="reserved2"):
            _generate_ota_uuid(reserved2=16384)
        with pytest.raises(ValueError, match="reserved2"):
            _generate_ota_uuid(reserved2=-1)

    def test_reserved2_encoding(self):
        u = _generate_ota_uuid(timestamp=0, random_value=0, reserved2=0x1234)
        raw = u.bytes
        high = (0x1234 >> 8) & 0x3F
        low = 0x1234 & 0xFF
        assert raw[14] & 0x3F == high
        assert raw[15] == low

    def test_no_args_uses_random(self):
        u1 = _generate_ota_uuid()
        u2 = _generate_ota_uuid()
        assert u1 != u2

    def test_combined_group_and_fragment(self):
        u = _generate_ota_uuid(
            timestamp=0, random_value=0, group_index=5, fragment_index=10
        )
        raw = u.bytes
        assert raw[6] & 0x0F == 6   # group_index + 1
        assert raw[8] & 0x1F == 11  # fragment_index + 1
        # marker bits still set
        assert raw[6] & 0x80 == 0x80
        assert raw[8] & 0x80 == 0x80
