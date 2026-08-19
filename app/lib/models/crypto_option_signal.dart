// Model for a BTC/ETH option signal produced by the crypto options algo
// (`crypto option trading/src`). Backed by the `crypto_option_signals`
// Supabase table. Replaces NiftyOptionSignal — kept deliberately parallel to
// TradeSignal so the UI patterns match, but with option-specific fields
// (side / strike / size / USD stop).

enum OptionSide { call, put } // call = bullish, put = bearish

enum OptionResult { pending, win, loss, expired }

class CryptoOptionSignal {
  final String id;
  final String symbol; // 'BTCUSDT' | 'ETHUSDT'
  final OptionSide side;
  final double? strike;

  /// Nearest Deribit expiry for the ATM contract quoted at signal time.
  final DateTime? optionExpiry;

  /// Broker/exchange-ready label written by the backend, e.g. 'BTC-29AUG26-70000-C'.
  final String? instrument;

  /// Underlying units sized to the USD stop budget, e.g. 0.05 BTC.
  final double size;

  // Underlying (perp) price levels the signal is based on
  final double spot;
  final double entry;
  final double stopPrice;
  final double? targetPrice;

  final double maxLossUsd; // USD stop budget per trade
  final double? rsi;
  final double? atr;

  final OptionResult result;
  final double? pnlUsd;
  final bool entryConfirmed;

  /// Why the trade closed: TARGET | STOP | TRAIL | TIMEOUT. Null while open.
  final String? exitReason;
  final double? exitPrice;
  final double? latestPrice;

  /// When the trade was created (signal fired).
  final DateTime timestamp;

  /// When the trade will be / was force-closed (24/7 market — no session
  /// close, so this is entry time + max hold, not an exchange close time).
  final DateTime? expiresAt;

  /// When entry actually filled — null while the limit is still unfilled.
  final DateTime? entryAt;

  /// When the trade actually closed. Null while still open.
  final DateTime? closedAt;

  final String? note;

  const CryptoOptionSignal({
    required this.id,
    required this.symbol,
    required this.side,
    this.strike,
    this.optionExpiry,
    this.instrument,
    this.size = 0,
    required this.spot,
    required this.entry,
    required this.stopPrice,
    this.targetPrice,
    required this.maxLossUsd,
    this.rsi,
    this.atr,
    this.result = OptionResult.pending,
    this.pnlUsd,
    this.entryConfirmed = false,
    this.exitReason,
    this.exitPrice,
    this.latestPrice,
    required this.timestamp,
    this.expiresAt,
    this.entryAt,
    this.closedAt,
    this.note,
  });

  factory CryptoOptionSignal.fromJson(Map<String, dynamic> j) {
    return CryptoOptionSignal(
      id: j['id'] as String,
      symbol: (j['symbol'] as String?) ?? 'BTCUSDT',
      side: (j['side'] as String).toUpperCase() == 'PUT'
          ? OptionSide.put
          : OptionSide.call,
      strike: _num(j['strike']),
      optionExpiry: _parseTime(j['option_expiry']),
      instrument: j['instrument'] as String?,
      size: _num(j['size']) ?? 0,
      spot: _num(j['spot']) ?? 0,
      entry: _num(j['entry']) ?? 0,
      stopPrice: _num(j['stop_price']) ?? 0,
      targetPrice: _num(j['target_price']),
      maxLossUsd: _num(j['max_loss_usd']) ?? 0,
      rsi: _num(j['rsi']),
      atr: _num(j['atr']),
      result: _resultFromString(j['result'] as String? ?? 'pending'),
      pnlUsd: j['pnl_usd'] != null ? (j['pnl_usd'] as num).toDouble() : null,
      entryConfirmed: j['entry_confirmed'] as bool? ?? false,
      exitReason: j['exit_reason'] as String?,
      exitPrice: _num(j['exit_price']),
      latestPrice: _num(j['latest_price']),
      timestamp: _parseTime(j['timestamp']) ?? DateTime.now(),
      expiresAt: _parseTime(j['expires_at']),
      entryAt: _parseTime(j['entry_at']),
      closedAt: _parseTime(j['closed_at']),
      note: j['note'] as String?,
    );
  }

  /// Tolerant numeric read — Supabase can hand back numerics as num or as a
  /// string depending on column type, and the key may be absent entirely.
  static double? _num(dynamic v) {
    if (v == null) return null;
    if (v is num) return v.toDouble();
    return double.tryParse(v.toString());
  }

  /// Supabase returns timestamptz (UTC); parse to local time so "created
  /// 10:15 AM" reads correctly on-device instead of showing a raw UTC instant.
  static DateTime? _parseTime(dynamic v) {
    if (v == null) return null;
    return DateTime.tryParse(v.toString())?.toLocal();
  }

  static OptionResult _resultFromString(String r) {
    switch (r) {
      case 'win':
        return OptionResult.win;
      case 'loss':
        return OptionResult.loss;
      case 'expired':
        return OptionResult.expired;
      default:
        return OptionResult.pending;
    }
  }

  // ---- Display helpers ----
  bool get isBullish => side == OptionSide.call;
  bool get isPending => result == OptionResult.pending;
  bool get isWin => result == OptionResult.win;
  bool get isLoss => result == OptionResult.loss;

  String get sideLabel => side == OptionSide.call ? 'BUY CALL' : 'BUY PUT';
  String get directionLabel => isBullish ? 'Bullish' : 'Bearish';

  String get assetLabel => symbol.replaceAll('USDT', '');

  /// The exact contract to buy, e.g. "BTC-29AUG26-70000-C".
  /// Prefers the backend's exchange-ready label; falls back to composing one.
  String get instrumentLabel {
    if (instrument != null && instrument!.isNotEmpty) return instrument!;
    final t = side == OptionSide.call ? 'CALL' : 'PUT';
    if (strike == null) return '$assetLabel $t (ATM)';
    return '$assetLabel ${strike!.toStringAsFixed(0)} $t';
  }

  /// One-line plain-English instruction.
  String get actionLabel =>
      'Buy ${size.toStringAsFixed(4)} $assetLabel of $instrumentLabel';

  /// Why this side — spells out CALL-vs-PUT rather than assuming it's known.
  String get sideExplainer => side == OptionSide.call
      ? 'CALL — profits if $assetLabel rises'
      : 'PUT — profits if $assetLabel falls';

  bool get hasExpiry => expiresAt != null;

  String get expiryLabel {
    if (expiresAt == null) return '';
    final left = expiresAt!.difference(DateTime.now());
    if (left.isNegative) return 'Closed';
    if (left.inMinutes < 60) return 'Exits in ${left.inMinutes}m';
    if (left.inHours < 24) return 'Exits in ${left.inHours}h';
    return 'Exits ${_dayLabel(expiresAt!)}';
  }

  // ---- Trade lifecycle timestamps ----

  /// "1 Aug, 10:15 AM" — when the trade was created.
  String get createdLabel => _fmtDateTime(timestamp);

  /// When the trade closed, or the scheduled timeout while still open.
  String get closedLabel {
    if (closedAt != null) return _fmtDateTime(closedAt!);
    if (expiresAt != null) return _fmtDateTime(expiresAt!);
    return '—';
  }

  /// When entry actually filled, or a placeholder while unfilled.
  String get entryAtLabel =>
      entryAt != null ? _fmtDateTime(entryAt!) : 'Not filled';

  /// How long the trade was held, e.g. "1h 45m". Empty while open.
  String get holdDurationLabel {
    final start = entryAt ?? timestamp;
    final end = closedAt;
    if (end == null) return '';
    final d = end.difference(start);
    if (d.isNegative) return '';
    final h = d.inHours;
    final m = d.inMinutes % 60;
    return h > 0 ? '${h}h ${m}m' : '${m}m';
  }

  /// Human label for how the trade ended.
  String get exitReasonLabel {
    switch (exitReason) {
      case 'TARGET':
        return 'Target hit';
      case 'STOP':
        return 'Stop-loss hit';
      case 'TRAIL':
        return 'Trailing stop hit';
      case 'TIMEOUT':
        return 'Closed at timeout';
      default:
        return isPending ? 'Open' : result.name.toUpperCase();
    }
  }

  static const _months = [
    'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
    'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
  ];

  static String _dayLabel(DateTime d) {
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    final that = DateTime(d.year, d.month, d.day);
    final diff = that.difference(today).inDays;
    if (diff == 0) return 'today';
    if (diff == 1) return 'tomorrow';
    if (diff == -1) return 'yesterday';
    return '${d.day} ${_months[d.month - 1]}';
  }

  static String _fmtDateTime(DateTime d) {
    final h24 = d.hour;
    final ampm = h24 >= 12 ? 'PM' : 'AM';
    final h = h24 % 12 == 0 ? 12 : h24 % 12;
    final m = d.minute.toString().padLeft(2, '0');
    return '${d.day} ${_months[d.month - 1]}, $h:$m $ampm';
  }
}

// Stats over a list of option signals (win rate + USD P&L).
class OptionStats {
  final int total;
  final int wins;
  final int losses;
  final int pending;
  final double netPnlUsd;

  const OptionStats({
    required this.total,
    required this.wins,
    required this.losses,
    required this.pending,
    required this.netPnlUsd,
  });

  factory OptionStats.from(List<CryptoOptionSignal> signals) {
    final closed = signals.where((s) => !s.isPending).toList();
    final w = closed.where((s) => s.isWin).length;
    final l = closed.where((s) => s.isLoss).length;
    final net = signals.fold<double>(0, (sum, s) => sum + (s.pnlUsd ?? 0));
    return OptionStats(
      total: signals.length,
      wins: w,
      losses: l,
      pending: signals.where((s) => s.isPending).length,
      netPnlUsd: net,
    );
  }

  double get winRate => (wins + losses) == 0 ? 0 : wins / (wins + losses);
  int get closed => wins + losses;
}
