-- =====================================================================
-- Migration — add build_number to notification_tokens
--
-- WHY: "New Listing Shorts" push notifications must NOT reach devices
-- running an app build from before this feature shipped (they have no
-- Shorts tab to open, so a push about it is just confusing noise, and
-- the user explicitly asked that old installs never see it).
--
-- There is no existing way to tell old installs from new ones -- the
-- app's version has never been bumped before this release (every APK
-- ever built reports 1.0.0+1), and notification_tokens only stores
-- device_token/platform/is_enabled. This adds the missing piece:
--
--   - The app now sends its build number every time it registers/
--     refreshes its push token (see push_notification_service.dart).
--   - An OLD, already-installed APK's code has no idea this field
--     exists, so it can NEVER send one -- its row's build_number stays
--     NULL forever, regardless of how many times it reopens.
--   - Only an app built AFTER this migration (build_number >= 2, see
--     FEATURE_MIN_BUILD in short_notify.py) will ever populate it.
--
-- Run in the Supabase SQL editor. Safe to re-run (IF NOT EXISTS).
-- =====================================================================

ALTER TABLE public.notification_tokens
    ADD COLUMN IF NOT EXISTS build_number integer;  -- NULL = pre-Shorts-tab install

-- Verify
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name   = 'notification_tokens'
  AND column_name  = 'build_number';
