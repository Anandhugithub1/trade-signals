// Model for a NIFTY 50 option signal produced by the options algo
// (`nifty option trading/src`). Backed by the `nifty_option_signals`
// Supabase table. Kept deliberately parallel to TradeSignal so the UI
// patterns match, but with option-specific fields (strike / side / premium).

enum OptionSide { ce, pe } // CE = bullish (buy call), PE = bearish (buy put)

enum OptionResult { pending, win, loss, expired }

class NiftyOptionSignal {
  final String id;
  final OptionSide side;
  final int? strike;
  final String strikeStyle; // ITM | ATM | OTM
  final double? premium;

  /// Weekly contract expiry (the Tuesday the option settles) — distinct from
  /// [expiresAt], which is when this intraday signal is squared off.
  final DateTime? optionExpiry;

  /// Broker-ready label written by the backend, e.g. "NIFTY 24400 CE 12 Aug".
  final String? instrument;

  final int lots;

  // Index (NIFTY spot) levels the signal is based on
  final double spot;
  final double indexEntry;
  final double indexStop;
  final double? indexTarget; // null for reversal-exit signals

  final double maxLossRs; // rupee stop budget per trade
  final double? rsi;
  final double? atr;

  final OptionResult result;
  final double? pnlRs;
  final bool entryConfirmed;

  /// Why the trade closed: TARGET | STOP | REVERSAL | EOD. Null while open.
  final String? exitReason;
  final double? exitIndex;
  final double? latestIndex;

  /// When the trade was created (signal fired).
  final DateTime timestamp;

  /// When the trade will be / was squared off.
  final DateTime? expiresAt;

  /// When entry actually filled — null while the limit is still unfilled.
  final DateTime? entryAt;

  /// When the trade actually closed. Null while still open.
  final DateTime? closedAt;

  final String? note;

  const NiftyOptionSignal({
    required this.id,
    required this.side,
    this.strike,
    this.strikeStyle = 'ATM',
    this.premium,
    this.optionExpiry,
    this.instrument,
    this.lots = 1,
    required this.spot,
    required this.indexEntry,
    required this.indexStop,
    this.indexTarget,
    required this.maxLossRs,
    this.rsi,
    this.atr,
    this.result = OptionResult.pending,
    this.pnlRs,
    this.entryConfirmed = false,
    this.exitReason,
    this.exitIndex,
    this.latestIndex,
    required this.timestamp,
    this.expiresAt,
    this.entryAt,
    this.closedAt,
    this.note,
  });

  factory NiftyOptionSignal.fromJson(Map<String, dynamic> j) {
    return NiftyOptionSignal(
      id: j['id'] as String,
      side: (j['side'] as String).toUpperCase() == 'PE'
          ? OptionSide.pe
          : OptionSide.ce,
      strike: _num(j['strike'])?.toInt(),
      strikeStyle: (j['strike_style'] as String?) ?? 'ATM',
      premium: _num(j['premium']),
      optionExpiry: _parseTime(j['option_expiry']),
      instrument: j['instrument'] as String?,
      lots: _num(j['lots'])?.toInt() ?? 1,
      spot: _num(j['spot']) ?? 0,
      indexEntry: _num(j['index_entry']) ?? 0,
      indexStop: _num(j['index_stop']) ?? 0,
      indexTarget: _num(j['index_target']),
      maxLossRs: _num(j['max_loss_rs']) ?? 0,
      rsi: _num(j['rsi']),
      atr: _num(j['atr']),
      result: _resultFromString(j['result'] as String? ?? 'pending'),
      pnlRs: j['pnl_rs'] != null ? (j['pnl_rs'] as num).toDouble() : null,
      entryConfirmed: j['entry_confirmed'] as bool? ?? false,
      // These columns ship with the exit-tracking migration. Reading them
      // defensively means an app build that predates the migration (or a DB
      // that hasn't had it applied yet) still renders the feed instead of
      // throwing and surfacing as a bogus "No Connection".
      exitReason: j['exit_reason'] as String?,
      exitIndex: _num(j['exit_index']),
      latestIndex: _num(j['latest_index']),
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

  /// Supabase returns timestamptz; the backend writes IST-offset strings.
  /// Parse to local time so "created 10:15 AM" reads correctly on-device
  /// instead of showing a raw UTC instant.
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
  bool get isBullish => side == OptionSide.ce;
  bool get isPending => result == OptionResult.pending;
  bool get isWin => result == OptionResult.win;
  bool get isLoss => result == OptionResult.loss;

  String get sideLabel => side == OptionSide.ce ? 'BUY CE' : 'BUY PE';
  String get directionLabel => isBullish ? 'Bullish' : 'Bearish';

  /// The exact contract to buy, e.g. "NIFTY 24400 CE 12 Aug".
  /// Prefers the backend's broker-ready label; falls back to composing one.
  String get instrumentLabel {
    if (instrument != null && instrument!.isNotEmpty) return instrument!;
    final t = side == OptionSide.ce ? 'CE' : 'PE';
    if (strike == null) return 'NIFTY $t ($strikeStyle)';
    final exp = optionExpiry == null
        ? ''
        : ' ${optionExpiry!.day} ${_months[optionExpiry!.month - 1]}';
    return 'NIFTY $strike $t$exp';
  }

  /// One-line plain-English instruction, e.g.
  /// "Buy 1 lot (75) of NIFTY 24400 CE 12 Aug — bullish on NIFTY".
  String get actionLabel {
    final qty = lots == 1 ? '1 lot' : '$lots lots';
    final units = lotSize * lots;
    return 'Buy $qty ($units) of $instrumentLabel';
  }

  /// Why this side — spells out CE-vs-PE rather than assuming it's known.
  String get sideExplainer => side == OptionSide.ce
      ? 'CE (Call) — profits if NIFTY rises'
      : 'PE (Put) — profits if NIFTY falls';

  /// Premium is only known when NSE's chain was reachable at signal time.
  bool get hasPremium => premium != null;

  String get premiumLabel => premium == null
      ? 'Check broker'
      : '₹${premium!.toStringAsFixed(1)}';

  /// Total rupees to pay for the position, when premium is known.
  String get outlayLabel => premiumOutlay == null
      ? '—'
      : '₹${premiumOutlay!.toStringAsFixed(0)}';

  /// Approximate premium outlay to buy the position (per unit x 75 x lots).
  static const int lotSize = 75;
  double? get premiumOutlay =>
      premium == null ? null : premium! * lotSize * lots;

  bool get hasExpiry => expiresAt != null;

  String get expiryLabel {
    if (expiresAt == null) return '';
    final left = expiresAt!.difference(DateTime.now());
    if (left.isNegative) return 'Squared off';
    if (left.inMinutes < 60) return 'Exits in ${left.inMinutes}m';
    if (left.inHours < 24) return 'Exits in ${left.inHours}h';
    return 'Exits ${_dayLabel(expiresAt!)}';
  }

  // ---- Trade lifecycle timestamps ----

  /// "1 Aug, 10:15 AM" — when the trade was created.
  String get createdLabel => _fmtDateTime(timestamp);

  /// When the trade closed, or the scheduled square-off while still open.
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
      case 'REVERSAL':
        return 'Trend reversed';
      case 'EOD':
        return 'Squared off at close';
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

// Stats over a list of option signals (win rate + rupee P&L).
class OptionStats {
  final int total;
  final int wins;
  final int losses;
  final int pending;
  final double netPnlRs;

  const OptionStats({
    required this.total,
    required this.wins,
    required this.losses,
    required this.pending,
    required this.netPnlRs,
  });

  factory OptionStats.from(List<NiftyOptionSignal> signals) {
    final closed = signals.where((s) => !s.isPending).toList();
    final w = closed.where((s) => s.isWin).length;
    final l = closed.where((s) => s.isLoss).length;
    final net = signals.fold<double>(0, (sum, s) => sum + (s.pnlRs ?? 0));
    return OptionStats(
      total: signals.length,
      wins: w,
      losses: l,
      pending: signals.where((s) => s.isPending).length,
      netPnlRs: net,
    );
  }

  double get winRate => (wins + losses) == 0 ? 0 : wins / (wins + losses);
  int get closed => wins + losses;
}
