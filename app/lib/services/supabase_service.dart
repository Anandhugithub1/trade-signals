import 'package:supabase_flutter/supabase_flutter.dart';
import '../models/signal.dart';
import '../models/market_sentiment.dart';

class SupabaseService {
  static SupabaseClient get _db => Supabase.instance.client;

  /// Signals from the last 90 days, newest first.
  static Future<List<TradeSignal>> fetchSignals() async {
    final cutoff = DateTime.now()
        .subtract(const Duration(days: 90))
        .toIso8601String();
    final data = await _db
        .from('trade_signals')
        .select()
        .gte('timestamp', cutoff)
        .order('timestamp', ascending: false);
    return data
        .map<TradeSignal>((e) => TradeSignal.fromJson(e))
        .toList();
  }

  /// Most recent market sentiment row.
  static Future<MarketSentiment?> fetchLatestSentiment() async {
    final data = await _db
        .from('market_sentiment')
        .select()
        .order('date', ascending: false)
        .limit(1)
        .maybeSingle();
    if (data == null) return null;
    return MarketSentiment.fromJson(data);
  }

  /// Both in parallel.
  static Future<({List<TradeSignal> signals, MarketSentiment? sentiment})>
      fetchAll() async {
    final (sigs, sent) = await (fetchSignals(), fetchLatestSentiment()).wait;
    return (signals: sigs, sentiment: sent);
  }
}
