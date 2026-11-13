class MonthlySummaryRow {
  final String month;
  final String market;
  final int trades;
  final int wins;
  final int losses;
  final int expired;
  final double? winRate;
  final double pnl;
  final String pnlUnit;
  final double totalR;
  final double? best;
  final double? worst;

  const MonthlySummaryRow({
    required this.month,
    required this.market,
    required this.trades,
    required this.wins,
    required this.losses,
    required this.expired,
    this.winRate,
    required this.pnl,
    required this.pnlUnit,
    this.totalR = 0.0,
    this.best,
    this.worst,
  });

  factory MonthlySummaryRow.fromJson(Map<String, dynamic> json) {
    return MonthlySummaryRow(
      month: json['month'] as String? ?? '',
      market: json['market'] as String? ?? 'crypto',
      trades: (json['trades'] as num?)?.toInt() ?? 0,
      wins: (json['wins'] as num?)?.toInt() ?? 0,
      losses: (json['losses'] as num?)?.toInt() ?? 0,
      expired: (json['expired'] as num?)?.toInt() ?? 0,
      winRate: (json['win_rate'] as num?)?.toDouble(),
      pnl: (json['pnl'] as num?)?.toDouble() ?? 0.0,
      pnlUnit: json['pnl_unit'] as String? ?? 'pct',
      totalR: (json['total_r'] as num?)?.toDouble() ?? 0.0,
      best: (json['best'] as num?)?.toDouble(),
      worst: (json['worst'] as num?)?.toDouble(),
    );
  }
}
