"""
Push notifications for "short new listings" signals.

Same FCM v1 pattern as backend/generate_signals (new-signal alert) and
backend/check_signals (win/loss alert), with one addition: these pushes
are gated to devices running a build that actually HAS the Shorts tab.

WHY THE GATING: the app's version was never bumped before this feature
shipped (every APK ever built reports 1.0.0+1), and notification_tokens
never tracked which build a device is running. A push about a feature an
old install can't even open would just be confusing noise -- see the
schema migration (schema/migration_notification_build_gating.sql) and
push_notification_service.dart for the full mechanism. In short: an old
app's code has no idea a `build_number` field exists, so it can never
send one, and its notification_tokens row's build_number stays NULL
forever. Filtering on `build_number >= FEATURE_MIN_BUILD` at the SQL
level naturally excludes those rows -- `NULL >= 2` is never true in SQL,
so no separate NULL-handling is needed.
"""
from __future__ import annotations

import json
import os
from typing import Optional

import requests

# The app build that first sends build_number when it registers its push
# token (see app/pubspec.yaml's version comment). Bump this alongside any
# FUTURE feature that also needs to skip older installs.
FEATURE_MIN_BUILD = 2

FCM_HEADERS = {"User-Agent": "ShortNewListings/1.0 signal-bot"}


def _load_firebase_sa() -> str:
    """Same convention as every other engine: local dev reads a file path,
    CI reads the whole JSON from an env var."""
    path = os.environ.get("FIREBASE_SERVICE_ACCOUNT_PATH", "")
    if path and os.path.isfile(path):
        with open(path) as f:
            return f.read()
    return os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON", "")


def _fcm_token() -> Optional[tuple[str, str]]:
    """Returns (bearer_token, project_id), or None if not configured/failed."""
    sa_json = _load_firebase_sa()
    if not sa_json:
        return None
    try:
        from google.oauth2 import service_account
        import google.auth.transport.requests

        sa = json.loads(sa_json)
        creds = service_account.Credentials.from_service_account_info(
            sa, scopes=["https://www.googleapis.com/auth/firebase.messaging"]
        )
        creds.refresh(google.auth.transport.requests.Request())
        return creds.token, sa["project_id"]
    except Exception as e:  # noqa: BLE001
        print(f"  [FCM] token error: {e}")
        return None


def _eligible_device_tokens(supabase) -> list[str]:
    """Enabled devices running a build new enough to have the Shorts tab."""
    try:
        res = (
            supabase.table("notification_tokens")
            .select("device_token")
            .eq("is_enabled", True)
            .gte("build_number", FEATURE_MIN_BUILD)
            .execute()
        )
        return [r["device_token"] for r in (res.data or [])]
    except Exception as e:  # noqa: BLE001
        print(f"  [FCM] could not fetch device tokens: {e}")
        return []


def _send(tokens: list[str], title: str, body: str, data: dict) -> None:
    fcm = _fcm_token()
    if not fcm:
        print("  [FCM] not configured — skipping push")
        return
    bearer, project_id = fcm
    url = f"https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"
    headers = {"Authorization": f"Bearer {bearer}", "Content-Type": "application/json"}

    ok = fail = 0
    for token in tokens:
        try:
            resp = requests.post(url, headers=headers, timeout=8, json={
                "message": {
                    "token": token,
                    "notification": {"title": title, "body": body},
                    "data": data,
                    "android": {"priority": "high"},
                    "apns": {"payload": {"aps": {"sound": "default"}}},
                }
            })
            ok += 1 if resp.status_code == 200 else 0
            fail += 0 if resp.status_code == 200 else 1
        except Exception:
            fail += 1

    print(f"  [FCM] push sent to {len(tokens)} eligible device(s) "
          f"(build>={FEATURE_MIN_BUILD}) — {ok} ok / {fail} failed")


def notify_new_signal(supabase, symbol: str) -> None:
    """SHORT signal just fired on `symbol`."""
    tokens = _eligible_device_tokens(supabase)
    if not tokens:
        return
    asset = symbol.replace("USDT", "")
    _send(
        tokens,
        "New Listing Short",
        f"SHORT {asset} — new listing, 27-33 days old",
        data={"type": "new_listing_short", "symbol": symbol},
    )


def notify_signal_result(supabase, symbol: str, result: str, pnl_pct: Optional[float]) -> None:
    """A short position closed (win/loss)."""
    if result not in ("win", "loss"):
        return
    tokens = _eligible_device_tokens(supabase)
    if not tokens:
        return
    asset = symbol.replace("USDT", "")
    pnl_str = f"  {'+' if (pnl_pct or 0) >= 0 else ''}{pnl_pct:.1f}%" if pnl_pct is not None else ""
    if result == "win":
        title = f"{asset} SHORT — Profit Locked"
        body = f"Closed in profit{pnl_str}"
    else:
        title = f"{asset} SHORT — Stop-Loss Hit"
        body = f"Closed at stop{pnl_str}"
    _send(tokens, title, body, data={"type": "short_result", "result": result, "symbol": symbol})
