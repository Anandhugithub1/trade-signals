import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/material.dart';
import '../services/push_notification_service.dart';
import '../theme/app_colors.dart';

class NotificationSettingsScreen extends StatefulWidget {
  const NotificationSettingsScreen({super.key});

  @override
  State<NotificationSettingsScreen> createState() =>
      _NotificationSettingsScreenState();
}

class _NotificationSettingsScreenState
    extends State<NotificationSettingsScreen> {
  bool _enabled     = true;
  bool _loading     = true;
  String? _token;
  AuthorizationStatus _permission = AuthorizationStatus.notDetermined;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final settings = await FirebaseMessaging.instance.getNotificationSettings();
    final enabled  = await PushNotificationService.isEnabled();
    final token    = await PushNotificationService.getToken();
    if (mounted) {
      setState(() {
        _permission = settings.authorizationStatus;
        _enabled    = enabled;
        _token      = token;
        _loading    = false;
      });
    }
  }

  Future<void> _toggle(bool value) async {
    setState(() => _loading = true);
    await PushNotificationService.setEnabled(value);
    setState(() { _enabled = value; _loading = false; });
  }

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final granted = _permission == AuthorizationStatus.authorized ||
        _permission == AuthorizationStatus.provisional;

    return Scaffold(
      backgroundColor: c.bg,
      appBar: AppBar(
        backgroundColor: c.bg,
        elevation: 0,
        leading: IconButton(
          icon: Icon(Icons.arrow_back_ios_new_rounded, color: c.t1, size: 18),
          onPressed: () => Navigator.pop(context),
        ),
        title: Text('Notifications',
            style: TextStyle(color: c.t1, fontWeight: FontWeight.w700, fontSize: 17)),
      ),
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          // Permission status banner
          if (!granted) _PermissionBanner(),

          const SizedBox(height: 8),

          // Main toggle card
          _Card(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('Push Notifications',
                            style: TextStyle(
                                color: c.t1,
                                fontSize: 15,
                                fontWeight: FontWeight.w700)),
                        const SizedBox(height: 3),
                        Text('Alerts when new signals are posted',
                            style: TextStyle(color: c.t2, fontSize: 12)),
                      ],
                    ),
                    _loading
                        ? SizedBox(
                            width: 20, height: 20,
                            child: CircularProgressIndicator(
                                strokeWidth: 2, color: c.accent))
                        : Switch.adaptive(
                            value: _enabled && granted,
                            onChanged: granted ? _toggle : null,
                            activeColor: c.accent,
                          ),
                  ],
                ),
              ],
            ),
          ),

          const SizedBox(height: 14),

          // What you'll receive
          _Card(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('You will receive alerts for',
                    style: TextStyle(
                        color: c.t1, fontSize: 14, fontWeight: FontWeight.w700)),
                const SizedBox(height: 12),
                ...const [
                  (Icons.bolt_rounded,        'New trading signals',         'LONG / SHORT with entry, SL, TP'),
                  (Icons.check_circle_outline, 'Signal closed — WIN',         'Take profit hit'),
                  (Icons.cancel_outlined,      'Signal closed — LOSS',        'Stop loss hit'),
                  (Icons.schedule_rounded,     'Signal expiring soon',        'Less than 12 hours remaining'),
                ].map((item) {
                  final (icon, title, sub) = item;
                  return Padding(
                    padding: const EdgeInsets.only(bottom: 12),
                    child: Row(
                      children: [
                        Icon(icon, color: c.accent, size: 18),
                        const SizedBox(width: 12),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(title,
                                  style: TextStyle(
                                      color: c.t1,
                                      fontSize: 13,
                                      fontWeight: FontWeight.w600)),
                              Text(sub,
                                  style: TextStyle(color: c.t3, fontSize: 11)),
                            ],
                          ),
                        ),
                      ],
                    ),
                  );
                }),
              ],
            ),
          ),

          // Token debug info (only shown in debug mode)
          if (_token != null) ...[
            const SizedBox(height: 14),
            _Card(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Device Token',
                      style: TextStyle(
                          color: c.t1, fontSize: 14, fontWeight: FontWeight.w700)),
                  const SizedBox(height: 6),
                  Text(
                    '${_token!.substring(0, 20)}…${_token!.substring(_token!.length - 10)}',
                    style: TextStyle(
                        color: c.t3, fontSize: 11, fontFamily: 'monospace'),
                  ),
                  const SizedBox(height: 4),
                  Text('Stored in Supabase · Used to deliver push alerts',
                      style: TextStyle(color: c.t3, fontSize: 11)),
                ],
              ),
            ),
          ],

          const SizedBox(height: 30),
        ],
      ),
    );
  }
}

class _PermissionBanner extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return Container(
      padding: const EdgeInsets.all(14),
      margin: const EdgeInsets.only(bottom: 14),
      decoration: BoxDecoration(
        color: c.gold.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: c.gold.withValues(alpha: 0.3)),
      ),
      child: Row(
        children: [
          Icon(Icons.notifications_off_outlined, color: c.gold, size: 18),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Permission required',
                    style: TextStyle(
                        color: c.gold, fontSize: 13, fontWeight: FontWeight.w700)),
                const SizedBox(height: 2),
                Text('Enable notifications in your phone Settings to receive alerts.',
                    style: TextStyle(color: c.t2, fontSize: 12)),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _Card extends StatelessWidget {
  final Widget child;
  const _Card({required this.child});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: c.card,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: c.border),
      ),
      child: child,
    );
  }
}
