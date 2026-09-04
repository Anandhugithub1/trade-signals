import 'package:flutter_test/flutter_test.dart';
import 'package:zenviq/models/crypto_option_signal.dart';

/// Row shaped exactly like what `crypto option trading/src/supabase_writer.py`
/// writes, so these tests fail if the two ever drift apart.
Map<String, dynamic> _row({
  String side = 'PUT',
  Object? premiumUsd = 972.34,
  Object? premiumCostUsd = 415.56,
  Object? markIv = 31.21,
  String? optionExpiry = '2026-09-08',
  String? expiresAt = '2026-09-07T11:11:31.570231+00:00',
  Object? result = 'pending',
  Object? pnlUsd,
}) =>
    {
      'id': '3192f75e-0ce4-4cb2-9e21-5eb99ec5d673',
      'symbol': 'BTCUSDT',
      'side': side,
      'strike': 81000.0,
      'option_expiry': optionExpiry,
      'instrument': 'BTC-8SEP26-81000-P',
      'size': 0.427378,
      'premium_usd': premiumUsd,
      'premium_cost_usd': premiumCostUsd,
      'mark_iv': markIv,
      'spot': 81104.4,
      'entry': 77307.7,
      'stop_price': 78243.64,
      'target_price': 76137.76,
      'max_loss_usd': 200.0,
      'rsi': 49.88,
      'atr': 467.97,
      'result': result,
      'pnl_usd': pnlUsd,
      'entry_confirmed': false,
      'exit_reason': null,
      'timestamp': '2026-09-04T11:11:31.570231+00:00',
      'expires_at': expiresAt,
      'entry_at': null,
      'closed_at': null,
      'exit_price': null,
      'latest_price': 81104.4,
      'note': 'Downtrend: Supertrend down, EMA9<EMA21, RSI lost 50, ADX 26.',
    };

void main() {
  group('CryptoOptionSignal parsing', () {
    test('parses a full backend row', () {
      final s = CryptoOptionSignal.fromJson(_row());
      expect(s.symbol, 'BTCUSDT');
      expect(s.side, OptionSide.put);
      expect(s.strike, 81000.0);
      expect(s.size, closeTo(0.427378, 1e-9));
      expect(s.premiumUsd, closeTo(972.34, 1e-9));
      expect(s.premiumCostUsd, closeTo(415.56, 1e-9));
      expect(s.markIv, closeTo(31.21, 1e-9));
      expect(s.isPending, isTrue);
    });

    test('CALL vs PUT direction mapping', () {
      expect(CryptoOptionSignal.fromJson(_row(side: 'CALL')).side,
          OptionSide.call);
      expect(CryptoOptionSignal.fromJson(_row(side: 'CALL')).isBullish, isTrue);
      expect(CryptoOptionSignal.fromJson(_row(side: 'PUT')).isBullish, isFalse);
    });

    test('tolerates string numerics and missing premium columns', () {
      // Supabase can hand numerics back as strings; and rows written before
      // the premium migration (or when Deribit was unreachable) have nulls.
      final s = CryptoOptionSignal.fromJson(_row(
        premiumUsd: '972.34',
        premiumCostUsd: null,
        markIv: null,
      ));
      expect(s.premiumUsd, closeTo(972.34, 1e-9));
      expect(s.premiumCostUsd, isNull);
      expect(s.markIv, isNull);
      expect(s.hasPremium, isTrue);
      expect(s.premiumCostLabel, '—');
      expect(s.markIvLabel, '—');
    });

    test('degrades to "Check Deribit" when premium is absent', () {
      final s = CryptoOptionSignal.fromJson(_row(premiumUsd: null));
      expect(s.hasPremium, isFalse);
      expect(s.premiumLabel, 'Check Deribit');
    });
  });

  group('money formatting', () {
    test('adds thousands separators and 2dp', () {
      expect(CryptoOptionSignal.fromJson(_row(premiumUsd: 972.34)).premiumLabel,
          r'$972.34');
      expect(
          CryptoOptionSignal.fromJson(_row(premiumUsd: 1112.4)).premiumLabel,
          r'$1,112.40');
      expect(
          CryptoOptionSignal.fromJson(_row(premiumUsd: 1234567.5))
              .premiumLabel,
          r'$1,234,567.50');
      // ETH-scale premiums must not gain a separator.
      expect(CryptoOptionSignal.fromJson(_row(premiumUsd: 38.68)).premiumLabel,
          r'$38.68');
    });
  });

  group('expiry safety check', () {
    test('contract outliving the trade is not flagged', () {
      // Settles 2026-09-08 08:00Z; trade closes 2026-09-07 11:11Z.
      final s = CryptoOptionSignal.fromJson(_row());
      expect(s.expiresBeforeTradeCloses, isFalse);
    });

    test('contract settling mid-trade IS flagged', () {
      // This reproduces the real 2026-08-26 bug: a BTC put on the 27AUG26
      // contract for a signal held until 29AUG26.
      final s = CryptoOptionSignal.fromJson(_row(
        optionExpiry: '2026-08-27',
        expiresAt: '2026-08-29T22:54:57.453514+00:00',
      ));
      expect(s.expiresBeforeTradeCloses, isTrue);
    });

    test('is not flagged when either date is missing', () {
      expect(
          CryptoOptionSignal.fromJson(_row(optionExpiry: null))
              .expiresBeforeTradeCloses,
          isFalse);
      expect(
          CryptoOptionSignal.fromJson(_row(expiresAt: null))
              .expiresBeforeTradeCloses,
          isFalse);
    });
  });

  group('OptionStats', () {
    test('win rate excludes pending, P&L includes every row', () {
      final signals = [
        CryptoOptionSignal.fromJson(_row(result: 'win', pnlUsd: 250.0)),
        CryptoOptionSignal.fromJson(_row(result: 'loss', pnlUsd: -200.0)),
        CryptoOptionSignal.fromJson(_row(result: 'loss', pnlUsd: -200.0)),
        CryptoOptionSignal.fromJson(_row(result: 'pending')),
      ];
      final st = OptionStats.from(signals);
      expect(st.total, 4);
      expect(st.wins, 1);
      expect(st.losses, 2);
      expect(st.pending, 1);
      expect(st.closed, 3);
      expect(st.winRate, closeTo(1 / 3, 1e-9));
      expect(st.netPnlUsd, closeTo(-150.0, 1e-9));
    });

    test('no closed trades gives 0 win rate, not NaN', () {
      final st = OptionStats.from(
          [CryptoOptionSignal.fromJson(_row(result: 'pending'))]);
      expect(st.winRate, 0);
      expect(st.winRate.isNaN, isFalse);
    });

    test('the 4-loss live streak reproduces the reported card values', () {
      final st = OptionStats.from(List.generate(
          4, (_) => CryptoOptionSignal.fromJson(
              _row(result: 'loss', pnlUsd: -200.0))));
      expect(st.netPnlUsd, closeTo(-800.0, 1e-9));
      expect(st.wins, 0);
      expect(st.losses, 4);
      expect(st.winRate, 0);
    });
  });
}
