// Model for a US stock swing signal produced by backend/generate_stock_signals.
// Backed by the `stock_signals` Supabase table. Kept parallel to TradeSignal
// and NiftyOptionSignal so the UI patterns match.

enum StockResult { pending, win, loss, expired }

class StockSignal {
  final String id;
  final String ticker;
  final String direction; // 'long' — the strategy is long-only

  final double entry;
  final double stopLoss;
  final double takeProfit;
  final double? latestPrice;
  final double? exitPrice;

  final double? atr;
  final double? adx;
  final double? rsi;
  final int? score;
  final double? rrRatio;

  final StockResult result;
  final String? exitReason; // TARGET | STOP | TIME | NO_FILL
  final double? pnlPct;
  final bool entryConfirmed;

  final DateTime timestamp;
  final DateTime? expiresAt;
  final DateTime? entryAt;
  final DateTime? closedAt;
  final String? note;

  const StockSignal({
    required this.id,
    required this.ticker,
    this.direction = 'long',
    required this.entry,
    required this.stopLoss,
    required this.takeProfit,
    this.latestPrice,
    this.exitPrice,
    this.atr,
    this.adx,
    this.rsi,
    this.score,
    this.rrRatio,
    this.result = StockResult.pending,
    this.exitReason,
    this.pnlPct,
    this.entryConfirmed = false,
    required this.timestamp,
    this.expiresAt,
    this.entryAt,
    this.closedAt,
    this.note,
  });

  factory StockSignal.fromJson(Map<String, dynamic> j) {
    return StockSignal(
      id: j['id'] as String,
      ticker: (j['ticker'] as String?) ?? '—',
      direction: (j['direction'] as String?) ?? 'long',
      entry: _num(j['entry']) ?? 0,
      stopLoss: _num(j['stop_loss']) ?? 0,
      takeProfit: _num(j['take_profit']) ?? 0,
      latestPrice: _num(j['latest_price']),
      exitPrice: _num(j['exit_price']),
      atr: _num(j['atr']),
      adx: _num(j['adx']),
      rsi: _num(j['rsi']),
      score: _num(j['score'])?.toInt(),
      rrRatio: _num(j['rr_ratio']),
      result: _resultFrom(j['result'] as String? ?? 'pending'),
      exitReason: j['exit_reason'] as String?,
      pnlPct: _num(j['pnl_pct']),
      entryConfirmed: j['entry_confirmed'] as bool? ?? false,
      timestamp: _time(j['timestamp']) ?? DateTime.now(),
      expiresAt: _time(j['expires_at']),
      entryAt: _time(j['entry_at']),
      closedAt: _time(j['closed_at']),
      note: j['note'] as String?,
    );
  }

  static double? _num(dynamic v) {
    if (v == null) return null;
    if (v is num) return v.toDouble();
    return double.tryParse(v.toString());
  }

  static DateTime? _time(dynamic v) {
    if (v == null) return null;
    return DateTime.tryParse(v.toString())?.toLocal();
  }

  static StockResult _resultFrom(String r) => switch (r) {
        'win' => StockResult.win,
        'loss' => StockResult.loss,
        'expired' => StockResult.expired,
        _ => StockResult.pending,
      };

  // ---- Display helpers ----
  bool get isPending => result == StockResult.pending;
  bool get isWin => result == StockResult.win;
  bool get isLoss => result == StockResult.loss;

  /// Risk per share in dollars.
  double get riskPerShare => (entry - stopLoss).abs();

  /// Reward:risk, e.g. "1 : 2.0".
  String get rrLabel =>
      rrRatio == null ? '—' : '1 : ${rrRatio!.toStringAsFixed(1)}';

  /// Plain instruction, e.g. "Buy AAPL at $312.28".
  String get actionLabel => 'Buy $ticker near \$${entry.toStringAsFixed(2)}';

  /// Live unrealised move while open, realised once closed.
  double? get movePct {
    if (pnlPct != null) return pnlPct;
    if (latestPrice == null || entry == 0) return null;
    return (latestPrice! - entry) / entry * 100;
  }

  String get statusLabel {
    if (isPending) return entryConfirmed ? 'In trade' : 'Waiting for entry';
    return switch (exitReason) {
      'TARGET' => 'Target hit',
      'STOP' => 'Stop-loss hit',
      'TIME' => 'Closed at time limit',
      'NO_FILL' => 'Never filled',
      _ => result.name.toUpperCase(),
    };
  }

  String get createdLabel => _fmt(timestamp);
  String get closedLabel =>
      closedAt != null ? _fmt(closedAt!) : (expiresAt != null ? _fmt(expiresAt!) : '—');

  /// How long the trade ran. Empty while open.
  String get holdLabel {
    final end = closedAt;
    if (end == null) return '';
    final d = end.difference(entryAt ?? timestamp);
    if (d.isNegative) return '';
    return d.inDays >= 1 ? '${d.inDays}d' : '${d.inHours}h';
  }

  static const _months = [
    'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
    'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
  ];

  static String _fmt(DateTime d) => '${d.day} ${_months[d.month - 1]}';
}

/// Aggregate stats over a list of stock signals.
class StockStats {
  final int total;
  final int wins;
  final int losses;
  final int pending;
  final double netPct;

  const StockStats({
    required this.total,
    required this.wins,
    required this.losses,
    required this.pending,
    required this.netPct,
  });

  factory StockStats.from(List<StockSignal> s) {
    final w = s.where((x) => x.isWin).length;
    final l = s.where((x) => x.isLoss).length;
    return StockStats(
      total: s.length,
      wins: w,
      losses: l,
      pending: s.where((x) => x.isPending).length,
      netPct: s.fold<double>(0, (sum, x) => sum + (x.pnlPct ?? 0)),
    );
  }

  int get closed => wins + losses;
  double get winRate => closed == 0 ? 0 : wins / closed;
}
