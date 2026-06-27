class TradeSignal {
  final String id;
  final String pair;
  final SignalDirection direction;
  final double entry;
  final double stopLoss;
  final double takeProfit;
  final int confidence;
  final DateTime timestamp;
  final SignalResult result;
  final double? closePrice; // actual price when signal closed

  const TradeSignal({
    required this.id,
    required this.pair,
    required this.direction,
    required this.entry,
    required this.stopLoss,
    required this.takeProfit,
    required this.confidence,
    required this.timestamp,
    this.result = SignalResult.pending,
    this.closePrice,
  });

  bool get isPending => result == SignalResult.pending;
  bool get isWin => result == SignalResult.win;
  bool get isLoss => result == SignalResult.loss;

  // Profit/loss % vs entry when closed
  double? get pnlPercent {
    if (closePrice == null) return null;
    final diff = closePrice! - entry;
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
