"""
Tests for push_notify.py's build-number gating -- the mechanism that keeps
"New Listing Shorts" push notifications away from app installs that
predate the feature.

Run:  python -m pytest tests/ -q      (from "short new listings/")
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import push_notify as pn  # noqa: E402


class _FakeQuery:
    """Chainable stand-in for the Supabase query builder."""
    def __init__(self, rows):
        self._rows = rows
        self.calls = []

    def select(self, *a, **kw):
        self.calls.append(("select", a, kw))
        return self

    def eq(self, *a, **kw):
        self.calls.append(("eq", a, kw))
        return self

    def gte(self, *a, **kw):
        self.calls.append(("gte", a, kw))
        return self

    def execute(self):
        return MagicMock(data=self._rows)


class _FakeClient:
    def __init__(self, rows):
        self._q = _FakeQuery(rows)

    def table(self, name):
        assert name == "notification_tokens"
        return self._q


def test_eligible_tokens_filters_on_build_number_and_enabled():
    client = _FakeClient([{"device_token": "tok1"}, {"device_token": "tok2"}])
    tokens = pn._eligible_device_tokens(client)
    assert tokens == ["tok1", "tok2"]
    # Must filter by is_enabled=True AND build_number >= FEATURE_MIN_BUILD --
    # the actual gating mechanism, not just "fetch everything".
    calls = client._q.calls
    assert ("eq", ("is_enabled", True), {}) in calls
    assert ("gte", ("build_number", pn.FEATURE_MIN_BUILD), {}) in calls


def test_eligible_tokens_returns_empty_on_query_failure():
    class _Boom:
        def table(self, name):
            raise RuntimeError("db down")
    assert pn._eligible_device_tokens(_Boom()) == []


def test_notify_new_signal_skips_send_when_no_eligible_devices():
    client = _FakeClient([])
    with patch.object(pn, "_send") as mock_send:
        pn.notify_new_signal(client, "XYZUSDT")
    mock_send.assert_not_called()


def test_notify_new_signal_sends_to_eligible_devices():
    client = _FakeClient([{"device_token": "tok1"}])
    with patch.object(pn, "_send") as mock_send:
        pn.notify_new_signal(client, "XYZUSDT")
    mock_send.assert_called_once()
    (tokens, title, body), kwargs = mock_send.call_args
    assert tokens == ["tok1"]
    assert "XYZ" in body
    assert kwargs["data"]["type"] == "new_listing_short"
    assert kwargs["data"]["symbol"] == "XYZUSDT"


def test_notify_signal_result_ignores_pending_and_expired():
    client = _FakeClient([{"device_token": "tok1"}])
    with patch.object(pn, "_send") as mock_send:
        pn.notify_signal_result(client, "XYZUSDT", "pending", None)
        pn.notify_signal_result(client, "XYZUSDT", "expired", None)
    mock_send.assert_not_called()


def test_notify_signal_result_win_and_loss_wording():
    client = _FakeClient([{"device_token": "tok1"}])
    with patch.object(pn, "_send") as mock_send:
        pn.notify_signal_result(client, "XYZUSDT", "win", 45.5)
    (_, title, body), kwargs = mock_send.call_args
    assert "Profit Locked" in title
    assert "+45.5%" in body
    assert kwargs["data"]["result"] == "win"

    with patch.object(pn, "_send") as mock_send:
        pn.notify_signal_result(client, "XYZUSDT", "loss", -30.0)
    (_, title, body), kwargs = mock_send.call_args
    assert "Stop-Loss Hit" in title
    assert "-30.0%" in body
    assert kwargs["data"]["result"] == "loss"


def test_fcm_token_returns_none_when_unconfigured():
    with patch.dict(os.environ, {"FIREBASE_SERVICE_ACCOUNT_JSON": "",
                                  "FIREBASE_SERVICE_ACCOUNT_PATH": ""}, clear=False):
        assert pn._fcm_token() is None


def test_send_skips_gracefully_when_fcm_unconfigured():
    with patch.object(pn, "_fcm_token", return_value=None):
        # Must not raise even with real tokens present.
        pn._send(["tok1", "tok2"], "title", "body", {"type": "x"})
