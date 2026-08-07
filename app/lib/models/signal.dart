class TradeSignal {
  final String id;
  final String pair;
  final SignalDirection direction;
  final double entry;
  final double stopLoss;
  final double takeProfit;
  final int confidence;
  final DateTime timestamp;
  final DateTime? expiresAt;
  final SignalResult result;
  final double? closePrice;
  final double? latestPrice;  // updated every hour by check_signals
  final bool entryConfirmed;  // true once price has touched the limit entry

  /// Which engine produced this signal: 'donchian' (4h channel breakout) or
  /// 'legacy' (the original 1h vote model). Both run side by side so live
  /// results can settle which one is actually better.
  final String strategy;

  const TradeSignal({
    required this.id,
    required this.pair,
    required this.direction,
    required this.entry,
    required this.stopLoss,
    required this.takeProfit,
    required this.confidence,
    required this.timestamp,
    this.expiresAt,
    this.result = SignalResult.pending,
    this.closePrice,
    this.latestPrice,
    this.entryConfirmed = false,
    this.strategy = 'legacy',
  });

  factory TradeSignal.fromJson(Map<String, dynamic> j) {
    return TradeSignal(
      id: j['id'] as String,
      pair: j['pair'] as String,
      direction: j['direction'] == 'long' ? SignalDirection.long : SignalDirection.short,
      entry: (j['entry'] as num).toDouble(),
      stopLoss: (j['stop_loss'] as num).toDouble(),
      takeProfit: (j['take_profit'] as num).toDouble(),
      confidence: j['confidence'] as int,
      timestamp: DateTime.parse(j['timestamp'] as String),
      expiresAt: j['expires_at'] != null ? DateTime.parse(j['expires_at'] as String) : null,
      result: _resultFromString(j['result'] as String? ?? 'pending'),
      closePrice: j['close_price'] != null ? (j['close_price'] as num).toDouble() : null,
      latestPrice: j['latest_price'] != null ? (j['latest_price'] as num).toDouble() : null,
      entryConfirmed: j['entry_confirmed'] as bool? ?? false,
      // Defaults to 'legacy' so rows written before the engine split (and
      // any app build older than the migration) still render.
      strategy: (j['strategy'] as String?) ?? 'legacy',
    );
  }

  // ---- Engine helpers ----
  bool get isDonchian => strategy == 'donchian';

  /// Badge text for the feed card. Short enough to survive a crowded header
  /// row (pair + PERP chip + direction + result) on a narrow phone, but still
  /// a real word rather than a cryptic code.
  String get strategyLabel => isDonchian ? 'BREAK' : 'MOMENTUM';

  /// One-line explanation of what the engine looks for.
  String get strategyNote => isDonchian
      ? '55-bar channel breakout on 4h bars, 3R target'
      : 'Multi-indicator momentum vote on 1h bars, 2R target';

  static SignalResult _resultFromString(String r) {
    switch (r) {
      case 'win':     return SignalResult.win;
      case 'loss':    return SignalResult.loss;
      case 'expired': return SignalResult.expired;
      default:        return SignalResult.pending;
    }
  }

  bool get isPending => result == SignalResult.pending;
  bool get isWin => result == SignalResult.win;
  bool get isLoss => result == SignalResult.loss;

  // Expiry helpers
  bool get hasExpiry => expiresAt != null;

  Duration? get timeLeft {
    if (expiresAt == null) return null;
    return expiresAt!.difference(DateTime.now());
  }

  bool get isExpiringSoon {
    final left = timeLeft;
    return left != null && left.inHours <= 12 && left.isNegative == false && isPending;
  }

  /// Human-readable countdown, e.g. "Expires in 2d 4h" or "Expired"
  String get expiryLabel {
    if (expiresAt == null) return '';
    final left = expiresAt!.difference(DateTime.now());
    if (left.isNegative) return 'Expired';
    if (left.inHours < 1) return 'Expires in <1h';
    if (left.inHours < 24) return 'Expires in ${left.inHours}h';
    final days = left.inDays;
    final hours = left.inHours - days * 24;
    return hours > 0 ? 'Expires in ${days}d ${hours}h' : 'Expires in ${days}d';
  }

  // Risk : Reward ratio — reward side of "1 : X"
  double get rrRatio {
    final risk = (entry - stopLoss).abs();
    if (risk == 0) return 0;
    return (takeProfit - entry).abs() / risk;
  }

  // Formatted label e.g. "1 : 1.5"
  String get rrLabel => '1 : ${rrRatio.toStringAsFixed(1)}';

  // Quality tier based on ratio
  String get rrQuality {
    if (rrRatio >= 2.0) return 'Excellent';
    if (rrRatio >= 1.5) return 'Good';
    return 'Fair';
  }

  // Profit/loss % vs entry when closed
  double? get pnlPercent {
    if (closePrice == null) return null;
    final diff = closePrice! - entry;
    final directedDiff = direction == SignalDirection.long ? diff : -diff;
    return (directedDiff / entry) * 100;
  }

  // Live unrealised P&L % using latest_price (pending signals only).
  // Only meaningful once the limit entry has actually been filled.
  double? get livePnlPercent {
    if (latestPrice == null || !isPending || !entryConfirmed) return null;
    final diff = latestPrice! - entry;
    final directedDiff = direction == SignalDirection.long ? diff : -diff;
    return (directedDiff / entry) * 100;
  }
}

enum SignalDirection { long, short }

enum SignalResult { pending, win, loss, expired }

// Only signals within the last 90 days are retained
final DateTime _cutoff = DateTime.now().subtract(const Duration(days: 90));

List<TradeSignal> get signalsFeed =>
    _allSignals.where((s) => s.timestamp.isAfter(_cutoff)).toList();

// Active signals only (pending result)
List<TradeSignal> get activeSignals =>
    signalsFeed.where((s) => s.isPending).toList();

// Performance stats computed from closed signals
SignalStats get signalStats => SignalStats.from(signalsFeed);

class SignalStats {
  final int total;
  final int wins;
  final int losses;
  final int pending;

  const SignalStats({
    required this.total,
    required this.wins,
    required this.losses,
    required this.pending,
  });

  factory SignalStats.from(List<TradeSignal> signals) {
    final closed = signals.where((s) => !s.isPending).toList();
    final w = closed.where((s) => s.isWin).length;
    final l = closed.where((s) => s.isLoss).length;
    return SignalStats(
      total: signals.length,
      wins: w,
      losses: l,
      pending: signals.where((s) => s.isPending).length,
    );
  }

  double get winRate => (wins + losses) == 0 ? 0 : wins / (wins + losses);
  int get closed => wins + losses;
}

// Full historical dataset — signals auto-expire after 90 days
final List<TradeSignal> _allSignals = [
  // --- Active / Pending (last 24 hours) ---
  TradeSignal(
    id: 'a1',
    pair: 'BTCUSDT',
    direction: SignalDirection.long,
    entry: 67420.50,
    stopLoss: 65800.00,
    takeProfit: 71000.00,
    confidence: 87,
    timestamp: DateTime.now().subtract(const Duration(minutes: 12)),
    expiresAt: DateTime.now().add(const Duration(days: 3, hours: 12)),
  ),
  TradeSignal(
    id: 'a2',
    pair: 'ETHUSDT',
    direction: SignalDirection.short,
    entry: 3521.80,
    stopLoss: 3680.00,
    takeProfit: 3200.00,
    confidence: 74,
    timestamp: DateTime.now().subtract(const Duration(hours: 1)),
    expiresAt: DateTime.now().add(const Duration(days: 3, hours: 8)),
  ),
  TradeSignal(
    id: 'a3',
    pair: 'SOLUSDT',
    direction: SignalDirection.long,
    entry: 178.40,
    stopLoss: 168.00,
    takeProfit: 198.00,
    confidence: 82,
    timestamp: DateTime.now().subtract(const Duration(hours: 3)),
    expiresAt: DateTime.now().add(const Duration(days: 3)),
  ),
  TradeSignal(
    id: 'a4',
    pair: 'XRPUSDT',
    direction: SignalDirection.short,
    entry: 0.6284,
    stopLoss: 0.6650,
    takeProfit: 0.5700,
    confidence: 69,
    timestamp: DateTime.now().subtract(const Duration(hours: 6)),
    expiresAt: DateTime.now().add(const Duration(days: 2)),
  ),
  TradeSignal(
    id: 'a5',
    pair: 'BNBUSDT',
    direction: SignalDirection.long,
    entry: 612.30,
    stopLoss: 590.00,
    takeProfit: 660.00,
    confidence: 78,
    timestamp: DateTime.now().subtract(const Duration(hours: 10)),
    expiresAt: DateTime.now().add(const Duration(days: 4, hours: 6)),
  ),

  // --- Week 1 (WIN) ---
  TradeSignal(
    id: 'w1',
    pair: 'BTCUSDT',
    direction: SignalDirection.long,
    entry: 65200.00,
    stopLoss: 63400.00,
    takeProfit: 69000.00,
    confidence: 85,
    timestamp: DateTime.now().subtract(const Duration(days: 2)),
    result: SignalResult.win,
    closePrice: 69000.00,
  ),
  TradeSignal(
    id: 'w2',
    pair: 'SOLUSDT',
    direction: SignalDirection.long,
    entry: 162.50,
    stopLoss: 154.00,
    takeProfit: 180.00,
    confidence: 80,
    timestamp: DateTime.now().subtract(const Duration(days: 3)),
    result: SignalResult.win,
    closePrice: 180.00,
  ),
  TradeSignal(
    id: 'w3',
    pair: 'ETHUSDT',
    direction: SignalDirection.short,
    entry: 3680.00,
    stopLoss: 3820.00,
    takeProfit: 3350.00,
    confidence: 76,
    timestamp: DateTime.now().subtract(const Duration(days: 4)),
    result: SignalResult.win,
    closePrice: 3350.00,
  ),
  TradeSignal(
    id: 'l1',
    pair: 'ADAUSDT',
    direction: SignalDirection.long,
    entry: 0.5100,
    stopLoss: 0.4750,
    takeProfit: 0.5800,
    confidence: 65,
    timestamp: DateTime.now().subtract(const Duration(days: 5)),
    result: SignalResult.loss,
    closePrice: 0.4750,
  ),
  TradeSignal(
    id: 'w4',
    pair: 'XRPUSDT',
    direction: SignalDirection.long,
    entry: 0.5940,
    stopLoss: 0.5600,
    takeProfit: 0.6800,
    confidence: 72,
    timestamp: DateTime.now().subtract(const Duration(days: 6)),
    result: SignalResult.win,
    closePrice: 0.6800,
  ),

  // --- Week 2 ---
  TradeSignal(
    id: 'w5',
    pair: 'BNBUSDT',
    direction: SignalDirection.short,
    entry: 640.00,
    stopLoss: 668.00,
    takeProfit: 595.00,
    confidence: 79,
    timestamp: DateTime.now().subtract(const Duration(days: 9)),
    result: SignalResult.win,
    closePrice: 595.00,
  ),
  TradeSignal(
    id: 'l2',
    pair: 'BTCUSDT',
    direction: SignalDirection.short,
    entry: 66100.00,
    stopLoss: 68000.00,
    takeProfit: 62000.00,
    confidence: 67,
    timestamp: DateTime.now().subtract(const Duration(days: 11)),
    result: SignalResult.loss,
    closePrice: 68000.00,
  ),
  TradeSignal(
    id: 'w6',
    pair: 'SOLUSDT',
    direction: SignalDirection.long,
    entry: 148.20,
    stopLoss: 140.00,
    takeProfit: 168.00,
    confidence: 83,
    timestamp: DateTime.now().subtract(const Duration(days: 13)),
    result: SignalResult.win,
    closePrice: 168.00,
  ),

  // --- Week 3-4 ---
  TradeSignal(
    id: 'w7',
    pair: 'ETHUSDT',
    direction: SignalDirection.long,
    entry: 3280.00,
    stopLoss: 3100.00,
    takeProfit: 3600.00,
    confidence: 81,
    timestamp: DateTime.now().subtract(const Duration(days: 18)),
    result: SignalResult.win,
    closePrice: 3600.00,
  ),
  TradeSignal(
    id: 'l3',
    pair: 'XRPUSDT',
    direction: SignalDirection.short,
    entry: 0.6450,
    stopLoss: 0.6820,
    takeProfit: 0.5900,
    confidence: 64,
    timestamp: DateTime.now().subtract(const Duration(days: 21)),
    result: SignalResult.loss,
    closePrice: 0.6820,
  ),
  TradeSignal(
    id: 'w8',
    pair: 'BTCUSDT',
    direction: SignalDirection.long,
    entry: 62400.00,
    stopLoss: 60500.00,
    takeProfit: 66800.00,
    confidence: 88,
    timestamp: DateTime.now().subtract(const Duration(days: 25)),
    result: SignalResult.win,
    closePrice: 66800.00,
  ),
  TradeSignal(
    id: 'w9',
    pair: 'BNBUSDT',
    direction: SignalDirection.long,
    entry: 580.00,
    stopLoss: 555.00,
    takeProfit: 625.00,
    confidence: 75,
    timestamp: DateTime.now().subtract(const Duration(days: 28)),
    result: SignalResult.win,
    closePrice: 625.00,
  ),

  // --- Month 2 ---
  TradeSignal(
    id: 'l4',
    pair: 'SOLUSDT',
    direction: SignalDirection.short,
    entry: 155.00,
    stopLoss: 168.00,
    takeProfit: 135.00,
    confidence: 66,
    timestamp: DateTime.now().subtract(const Duration(days: 35)),
    result: SignalResult.loss,
    closePrice: 168.00,
  ),
  TradeSignal(
    id: 'w10',
    pair: 'ETHUSDT',
    direction: SignalDirection.long,
    entry: 3050.00,
    stopLoss: 2880.00,
    takeProfit: 3400.00,
    confidence: 84,
    timestamp: DateTime.now().subtract(const Duration(days: 42)),
    result: SignalResult.win,
    closePrice: 3400.00,
  ),
  TradeSignal(
    id: 'w11',
    pair: 'BTCUSDT',
    direction: SignalDirection.long,
    entry: 59800.00,
    stopLoss: 57500.00,
    takeProfit: 64500.00,
    confidence: 86,
    timestamp: DateTime.now().subtract(const Duration(days: 50)),
    result: SignalResult.win,
    closePrice: 64500.00,
  ),
  TradeSignal(
    id: 'l5',
    pair: 'ADAUSDT',
    direction: SignalDirection.long,
    entry: 0.4400,
    stopLoss: 0.4100,
    takeProfit: 0.5000,
    confidence: 63,
    timestamp: DateTime.now().subtract(const Duration(days: 58)),
    result: SignalResult.loss,
    closePrice: 0.4100,
  ),
  TradeSignal(
    id: 'w12',
    pair: 'XRPUSDT',
    direction: SignalDirection.long,
    entry: 0.5500,
    stopLoss: 0.5100,
    takeProfit: 0.6400,
    confidence: 77,
    timestamp: DateTime.now().subtract(const Duration(days: 63)),
    result: SignalResult.win,
    closePrice: 0.6400,
  ),

  // --- Month 3 ---
  TradeSignal(
    id: 'w13',
    pair: 'BTCUSDT',
    direction: SignalDirection.short,
    entry: 72000.00,
    stopLoss: 74500.00,
    takeProfit: 66000.00,
    confidence: 82,
    timestamp: DateTime.now().subtract(const Duration(days: 71)),
    result: SignalResult.win,
    closePrice: 66000.00,
  ),
  TradeSignal(
    id: 'l6',
    pair: 'BNBUSDT',
    direction: SignalDirection.short,
    entry: 598.00,
    stopLoss: 625.00,
    takeProfit: 545.00,
    confidence: 61,
    timestamp: DateTime.now().subtract(const Duration(days: 78)),
    result: SignalResult.loss,
    closePrice: 625.00,
  ),
  TradeSignal(
    id: 'w14',
    pair: 'SOLUSDT',
    direction: SignalDirection.long,
    entry: 135.00,
    stopLoss: 126.00,
    takeProfit: 158.00,
    confidence: 80,
    timestamp: DateTime.now().subtract(const Duration(days: 85)),
    result: SignalResult.win,
    closePrice: 158.00,
  ),
];
