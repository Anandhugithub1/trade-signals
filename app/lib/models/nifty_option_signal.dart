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

  final DateTime timestamp;
  final DateTime? expiresAt;
  final String? note;

  const NiftyOptionSignal({
    required this.id,
    required this.side,
    this.strike,
    this.strikeStyle = 'ATM',
    this.premium,
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
    required this.timestamp,
    this.expiresAt,
    this.note,
  });

  factory NiftyOptionSignal.fromJson(Map<String, dynamic> j) {
    return NiftyOptionSignal(
      id: j['id'] as String,
      side: (j['side'] as String).toUpperCase() == 'PE'
          ? OptionSide.pe
          : OptionSide.ce,
      strike: j['strike'] != null ? (j['strike'] as num).toInt() : null,
      strikeStyle: (j['strike_style'] as String?) ?? 'ATM',
      premium: j['premium'] != null ? (j['premium'] as num).toDouble() : null,
      lots: j['lots'] != null ? (j['lots'] as num).toInt() : 1,
      spot: (j['spot'] as num).toDouble(),
      indexEntry: (j['index_entry'] as num).toDouble(),
      indexStop: (j['index_stop'] as num).toDouble(),
      indexTarget: j['index_target'] != null
          ? (j['index_target'] as num).toDouble()
          : null,
      maxLossRs: (j['max_loss_rs'] as num).toDouble(),
      rsi: j['rsi'] != null ? (j['rsi'] as num).toDouble() : null,
      atr: j['atr'] != null ? (j['atr'] as num).toDouble() : null,
      result: _resultFromString(j['result'] as String? ?? 'pending'),
      pnlRs: j['pnl_rs'] != null ? (j['pnl_rs'] as num).toDouble() : null,
      entryConfirmed: j['entry_confirmed'] as bool? ?? false,
      timestamp: DateTime.parse(j['timestamp'] as String),
      expiresAt: j['expires_at'] != null
          ? DateTime.parse(j['expires_at'] as String)
          : null,
      note: j['note'] as String?,
    );
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

  /// e.g. "NIFTY 24000 CE" or "NIFTY CE (ATM)" if strike not yet resolved.
  String get instrumentLabel {
    final t = side == OptionSide.ce ? 'CE' : 'PE';
    if (strike != null) return 'NIFTY $strike $t';
    return 'NIFTY $t ($strikeStyle)';
  }

  /// Approximate premium outlay to buy the position (per unit x 75 x lots).
  static const int lotSize = 75;
  double? get premiumOutlay =>
      premium == null ? null : premium! * lotSize * lots;

  bool get hasExpiry => expiresAt != null;

  String get expiryLabel {
    if (expiresAt == null) return '';
    final left = expiresAt!.difference(DateTime.now());
    if (left.isNegative) return 'Squared off';
    if (left.inHours < 1) return 'Exits in <1h';
    if (left.inHours < 24) return 'Exits in ${left.inHours}h';
    return 'Exits today';
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
