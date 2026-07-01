import 'dart:io';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

/// Handles FCM token registration, Supabase storage, and user preference.
///
/// Setup required (one-time):
///   1. Create a Firebase project at console.firebase.google.com
///   2. Add Android app → download google-services.json → place in android/app/
///   3. Add iOS app    → download GoogleService-Info.plist → place in ios/Runner/
///   4. For Android: apply the Google Services plugin in android/app/build.gradle
///   5. Add your FCM Server Key to the backend .env as FCM_SERVER_KEY
class PushNotificationService {
  static const _prefKey = 'notifications_enabled';

  static FirebaseMessaging get _fcm => FirebaseMessaging.instance;
  static SupabaseClient    get _db  => Supabase.instance.client;

  /// Call once from main() after Firebase.initializeApp().
  static Future<void> init() async {
    // Request OS-level permission
    final settings = await _fcm.requestPermission(
      alert: true,
      badge: true,
      sound: true,
      announcement: false,
      carPlay: false,
      criticalAlert: false,
      provisional: false,
    );

    if (settings.authorizationStatus == AuthorizationStatus.authorized ||
        settings.authorizationStatus == AuthorizationStatus.provisional) {
      await _registerToken();
    }

    // Refresh token if FCM rotates it
    _fcm.onTokenRefresh.listen((newToken) => _saveToken(newToken));

    // Handle notification tap when app is in background/terminated
    FirebaseMessaging.onMessageOpenedApp.listen(_onNotificationTap);
  }

  /// Returns the current FCM token, or null if unavailable.
  static Future<String?> getToken() => _fcm.getToken();

  /// Whether the user has notifications enabled (local preference).
  static Future<bool> isEnabled() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getBool(_prefKey) ?? true;
  }

  /// Toggle notifications on/off — updates both local prefs and Supabase.
  static Future<void> setEnabled(bool enabled) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_prefKey, enabled);

    final token = await _fcm.getToken();
    if (token == null) return;
    try {
      await _db
          .from('notification_tokens')
          .update({'is_enabled': enabled})
          .eq('device_token', token);
    } catch (_) {}
  }

  // ── private ────────────────────────────────────────────────────────────────

  static Future<void> _registerToken() async {
    final token = await _fcm.getToken();
    if (token != null) await _saveToken(token);
  }

  static Future<void> _saveToken(String token) async {
    final platform = kIsWeb ? 'web' : (Platform.isIOS ? 'ios' : 'android');
    try {
      await _db.from('notification_tokens').upsert(
        {'device_token': token, 'platform': platform, 'is_enabled': true},
        onConflict: 'device_token',
      );
      debugPrint('[PushNotification] ✓ token saved ($platform)  token=${token.substring(0, 20)}...');
    } on PostgrestException catch (e) {
      // Common causes:
      // 42P01 = table doesn't exist (run the Supabase setup SQL)
      // 42501 = RLS blocked insert (add policy: allow anon insert)
      debugPrint('[PushNotification] ✗ Supabase error ${e.code}: ${e.message}');
      debugPrint('[PushNotification]   → If 42P01: run CREATE TABLE notification_tokens ...');
      debugPrint('[PushNotification]   → If 42501: add RLS policy allowing anon INSERT');
    } catch (e) {
      debugPrint('[PushNotification] ✗ token save failed: $e');
    }
  }

  static void _onNotificationTap(RemoteMessage message) {
    debugPrint('[PushNotification] tapped: ${message.data}');
    // TODO: navigate to signals screen based on message.data['type']
  }
}
