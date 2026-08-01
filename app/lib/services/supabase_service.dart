import 'dart:async';
import 'dart:io';

import 'package:supabase_flutter/supabase_flutter.dart';
import '../models/signal.dart';
import '../models/market_sentiment.dart';
import '../models/nifty_option_signal.dart';
import '../utils/app_error.dart';

class SupabaseService {
  static SupabaseClient get _db => Supabase.instance.client;

  /// Wraps any Supabase / network call and maps exceptions to typed [AppError]s.
  static Future<T> _guard<T>(Future<T> Function() fn) async {
    try {
      return await fn().timeout(
        const Duration(seconds: 15),
        onTimeout: () => throw NetworkError(),
      );
    } on NetworkError {
      rethrow;
    } on AuthError {
      rethrow;
    } on AppError {
      rethrow;
    } on AuthException {
      throw const AuthError();
    } on PostgrestException catch (e) {
      // Map common Supabase PG error codes to friendly messages
      final msg = switch (e.code) {
        '42P01' => 'Table not found — run the Supabase setup SQL.',
        '23505' => 'Duplicate entry — this record already exists.',
        '42501' => 'Permission denied — check Row Level Security policies.',
        _       => e.message,
      };
      throw ServerError(msg, code: e.code);
    } on TypeError catch (e) {
      // A cast/shape mismatch while decoding a row — e.g. the app expects a
      // column the database doesn't have yet because a migration hasn't been
      // applied. This is NOT a connectivity problem, and must not fall through
      // to the string-matching below: those heuristics match substrings like
      // "timeout" anywhere in the text, so a schema error used to render as
      // "No Connection" and send you chasing your network instead of the DB.
      throw DataError('Unexpected data shape — $e');
    } catch (e) {
      // Only treat it as a network failure when the exception TYPE says so.
      // Matching on message text alone produced false positives.
      if (e is SocketException || e is TimeoutException) {
        throw const NetworkError();
      }
      final s = e.toString().toLowerCase();
      if (s.contains('socket') || s.contains('failed host lookup') ||
          s.contains('connection refused') ||
          s.contains('connection closed') ||
          s.contains('no address associated')) {
        throw const NetworkError();
      }
      throw AppError(e.toString());
    }
  }

  /// Signals from the last 90 days, newest first.
  static Future<List<TradeSignal>> fetchSignals() => _guard(() async {
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
      });

  /// NIFTY 50 option signals from the last 90 days, newest first.
  static Future<List<NiftyOptionSignal>> fetchNiftyOptionSignals() =>
      _guard(() async {
        final cutoff = DateTime.now()
            .subtract(const Duration(days: 90))
            .toIso8601String();
        final data = await _db
            .from('nifty_option_signals')
            .select()
            .gte('timestamp', cutoff)
            .order('timestamp', ascending: false);
        return data
            .map<NiftyOptionSignal>((e) => NiftyOptionSignal.fromJson(e))
            .toList();
      });

  /// Most recent market sentiment row.
  static Future<MarketSentiment?> fetchLatestSentiment() => _guard(() async {
        final data = await _db
            .from('market_sentiment')
            .select()
            .order('date', ascending: false)
            .limit(1)
            .maybeSingle();
        if (data == null) return null;
        return MarketSentiment.fromJson(data);
      });

  /// Both in parallel — throws the first error if either fails.
  static Future<({List<TradeSignal> signals, MarketSentiment? sentiment})>
      fetchAll() async {
    final (sigs, sent) = await (fetchSignals(), fetchLatestSentiment()).wait;
    return (signals: sigs, sentiment: sent);
  }
}
