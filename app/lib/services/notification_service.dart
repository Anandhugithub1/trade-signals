import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import '../models/signal.dart';

class NotificationService {
  static final NotificationService _instance = NotificationService._();
  factory NotificationService() => _instance;
  NotificationService._();

  final _plugin = FlutterLocalNotificationsPlugin();
  bool _ready = false;

  static const _channelId = 'trade_signals';
  static const _channelName = 'Trade Signals';
  static const _channelDesc = 'Real-time trade signal alerts';

  Future<void> init() async {
    const androidSettings = AndroidInitializationSettings('@mipmap/ic_launcher');
    const iosSettings = DarwinInitializationSettings(
      requestAlertPermission: true,
      requestBadgePermission: true,
      requestSoundPermission: true,
    );
    await _plugin.initialize(
      const InitializationSettings(android: androidSettings, iOS: iosSettings),
    );

    await _plugin
        .resolvePlatformSpecificImplementation<AndroidFlutterLocalNotificationsPlugin>()
        ?.requestNotificationsPermission();

    _ready = true;
  }

  Future<void> showSignalNotification(TradeSignal signal) async {
    if (!_ready) return;
    final isLong = signal.direction == SignalDirection.long;
    final dirLabel = isLong ? 'LONG  📈' : 'SHORT  📉';
    final entry = '\$${signal.entry.toStringAsFixed(2)}';

    await _plugin.show(
      signal.id.hashCode.abs() % 2147483647,
      '${signal.pair}  ·  $dirLabel',
      'Entry $entry  ·  ${signal.rrLabel} reward:risk  ·  Active signal',
      const NotificationDetails(
        android: AndroidNotificationDetails(
          _channelId,
          _channelName,
          channelDescription: _channelDesc,
          importance: Importance.high,
          priority: Priority.high,
          playSound: true,
          enableVibration: true,
        ),
        iOS: DarwinNotificationDetails(
          presentAlert: true,
          presentBadge: true,
          presentSound: true,
        ),
      ),
    );
  }

  Future<void> notifyActiveSignals() async {
    if (!_ready) return;
    final signals = activeSignals.take(3).toList();
    for (var i = 0; i < signals.length; i++) {
      await showSignalNotification(signals[i]);
      if (i < signals.length - 1) {
        await Future.delayed(const Duration(milliseconds: 500));
      }
    }
  }
}
