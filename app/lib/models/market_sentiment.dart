class MarketSentiment {
  final String id;
  final DateTime date;
  final int bullishPct;
  final int neutralPct;
  final int bearishPct;
  final int? fearGreedValue;
  final String? fearGreedLabel;
  final int activeLongs;
  final int activeShorts;
  final String dominant;

  const MarketSentiment({
    required this.id,
    required this.date,
    required this.bullishPct,
    required this.neutralPct,
    required this.bearishPct,
    this.fearGreedValue,
    this.fearGreedLabel,
    this.activeLongs = 0,
    this.activeShorts = 0,
    this.dominant = 'neutral',
  });

  factory MarketSentiment.fromJson(Map<String, dynamic> j) {
    return MarketSentiment(
      id: j['id'] as String,
      date: DateTime.parse(j['date'] as String),
      bullishPct: j['bullish_pct'] as int,
      neutralPct: j['neutral_pct'] as int,
      bearishPct: j['bearish_pct'] as int,
      fearGreedValue: j['fear_greed_value'] as int?,
      fearGreedLabel: j['fear_greed_label'] as String?,
      activeLongs: (j['active_longs'] as int?) ?? 0,
      activeShorts: (j['active_shorts'] as int?) ?? 0,
      dominant: (j['dominant'] as String?) ?? 'neutral',
    );
  }

  // Fallback when no data exists yet in Supabase
  static final placeholder = MarketSentiment(
    id: 'placeholder',
    date: DateTime.utc(2000),
    bullishPct: 50,
    neutralPct: 30,
    bearishPct: 20,
    dominant: 'neutral',
  );
}
