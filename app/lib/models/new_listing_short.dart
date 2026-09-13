// Model for a "short newly-listed coin" signal produced by the
// short-new-listings algo ("short new listings/src"). Backed by the
// `new_listing_shorts` Supabase table. Replaces StockSignal as the app's
// 4th tab. This is a plain perp SHORT (no options complexity), so P&L is
// a direct % move, not a delta approximation.

enum ShortResult { pending, win, loss, expired }

class NewListingShort {
  final String id;
  final String symbol;
  final DateTime listingDate;
  final double? daysSinceListing;

  final double entry;
  final double stopPrice;  // +30% adverse -> stopped out
  final double lockPrice;  // -50% favourable -> profit locked in early

  final ShortResult result;
  final double? pnlPct;
  final String? exitReason; // STOP | LOCK | TIME
  final double? exitPrice;
  final double? latestPrice;

  final DateTime timestamp;
  final DateTime? expiresAt;
  final DateTime? closedAt;
  final String? note;

  const NewListingShort({
    required this.id,
    required this.symbol,
    required this.listingDate,
    this.daysSinceListing,
    required this.entry,
    required this.stopPrice,
    required this.lockPrice,
    this.result = ShortResult.pending,
    this.pnlPct,
    this.exitReason,
    this.exitPrice,
    this.latestPrice,
    required this.timestamp,
    this.expiresAt,
    this.closedAt,
    this.note,
  });

  factory NewListingShort.fromJson(Map<String, dynamic> j) {
    return NewListingShort(
      id: j['id'] as String,
      symbol: (j['symbol'] as String?) ?? '',
      listingDate: _parseTime(j['listing_date']) ?? DateTime.now(),
      daysSinceListing: _num(j['days_since_listing']),
      entry: _num(j['entry']) ?? 0,
      stopPrice: _num(j['stop_price']) ?? 0,
      lockPrice: _num(j['lock_price']) ?? 0,
      result: _resultFromString(j['result'] as String? ?? 'pending'),
      pnlPct: _num(j['pnl_pct']),
      exitReason: j['exit_reason'] as String?,
      exitPrice: _num(j['exit_price']),
      latestPrice: _num(j['latest_price']),
      timestamp: _parseTime(j['timestamp']) ?? DateTime.now(),
      expiresAt: _parseTime(j['expires_at']),
      closedAt: _parseTime(j['closed_at']),
      note: j['note'] as String?,
    );
  }

  static double? _num(dynamic v) {
    if (v == null) return null;
    if (v is num) return v.toDouble();
    return double.tryParse(v.toString());
  }

  static DateTime? _parseTime(dynamic v) {
    if (v == null) return null;
    return DateTime.tryParse(v.toString())?.toLocal();
  }

  static ShortResult _resultFromString(String r) {
    switch (r) {
      case 'win':
        return ShortResult.win;
      case 'loss':
        return ShortResult.loss;
      case 'expired':
        return ShortResult.expired;
      default:
        return ShortResult.pending;
    }
  }

  // ---- Display helpers ----
  bool get isPending => result == ShortResult.pending;
  bool get isWin => result == ShortResult.win;
  bool get isLoss => result == ShortResult.loss;

  String get assetLabel => symbol.replaceAll('USDT', '');

  String get actionLabel => 'Short $assetLabel @ ${entry.toStringAsFixed(6)}';

  String get ageLabel => daysSinceListing == null
      ? '—'
      : 'Listed ${daysSinceListing!.round()}d ago';

  bool get hasExpiry => expiresAt != null;

  String get expiryLabel {
    if (expiresAt == null) return '';
    final left = expiresAt!.difference(DateTime.now());
    if (left.isNegative) return 'Closed';
    if (left.inHours < 24) return 'Exits in ${left.inHours}h';
    return 'Exits in ${left.inDays}d';
  }

  String get createdLabel => _fmtDateTime(timestamp);

  String get closedLabel {
    if (closedAt != null) return _fmtDateTime(closedAt!);
    if (expiresAt != null) return _fmtDateTime(expiresAt!);
    return '—';
  }

  String get exitReasonLabel {
    switch (exitReason) {
      case 'STOP':
        return 'Stop-loss hit';
      case 'LOCK':
        return 'Profit locked early';
      case 'TIME':
        return 'Closed at time limit';
      default:
        return isPending ? 'Open' : result.name.toUpperCase();
    }
  }

  static const _months = [
    'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
    'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
  ];

  static String _fmtDateTime(DateTime d) {
    final h24 = d.hour;
    final ampm = h24 >= 12 ? 'PM' : 'AM';
    final h = h24 % 12 == 0 ? 12 : h24 % 12;
    final m = d.minute.toString().padLeft(2, '0');
    return '${d.day} ${_months[d.month - 1]}, $h:$m $ampm';
  }
}

// Stats over a list of short signals (win rate + % P&L).
class ShortStats {
  final int total;
  final int wins;
  final int losses;
  final int pending;
  final double avgPnlPct;

  const ShortStats({
    required this.total,
    required this.wins,
    required this.losses,
    required this.pending,
    required this.avgPnlPct,
  });

  factory ShortStats.from(List<NewListingShort> signals) {
    final closed = signals.where((s) => !s.isPending).toList();
    final w = closed.where((s) => s.isWin).length;
    final l = closed.where((s) => s.isLoss).length;
    final pnls = closed.map((s) => s.pnlPct ?? 0).toList();
    final avg = pnls.isEmpty ? 0.0 : pnls.reduce((a, b) => a + b) / pnls.length;
    return ShortStats(
      total: signals.length,
      wins: w,
      losses: l,
      pending: signals.where((s) => s.isPending).length,
      avgPnlPct: avg,
    );
  }

  double get winRate => (wins + losses) == 0 ? 0 : wins / (wins + losses);
  int get closed => wins + losses;
}
