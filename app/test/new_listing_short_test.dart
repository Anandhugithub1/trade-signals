import 'package:flutter_test/flutter_test.dart';
import 'package:zenviq/models/new_listing_short.dart';

Map<String, dynamic> _row({
  String result = 'pending',
  Object? pnlPct,
  String? exitReason,
  String? closedAt,
}) =>
    {
      'id': 'abc123',
      'symbol': 'DOSUSDT',
      'listing_date': '2026-08-11',
      'days_since_listing': 32.8,
      'entry': 0.2223,
      'stop_price': 0.28899,
      'lock_price': 0.11115,
      'result': result,
      'pnl_pct': pnlPct,
      'exit_reason': exitReason,
      'exit_price': null,
      'latest_price': 0.2223,
      'timestamp': '2026-09-13T00:00:00+00:00',
      'expires_at': '2026-10-13T00:00:00+00:00',
      'closed_at': closedAt,
      'note': 'Listed 33d ago. Short at 0.2223.',
    };

void main() {
  group('NewListingShort parsing', () {
    test('parses a full backend row', () {
      final s = NewListingShort.fromJson(_row());
      expect(s.symbol, 'DOSUSDT');
      expect(s.assetLabel, 'DOS');
      expect(s.entry, closeTo(0.2223, 1e-9));
      expect(s.stopPrice, closeTo(0.28899, 1e-9));
      expect(s.lockPrice, closeTo(0.11115, 1e-9));
      expect(s.isPending, isTrue);
    });

    test('tolerates string numerics', () {
      final row = _row()..['entry'] = '0.2223';
      final s = NewListingShort.fromJson(row);
      expect(s.entry, closeTo(0.2223, 1e-9));
    });

    test('result mapping', () {
      expect(NewListingShort.fromJson(_row(result: 'win')).isWin, isTrue);
      expect(NewListingShort.fromJson(_row(result: 'loss')).isLoss, isTrue);
      expect(NewListingShort.fromJson(_row(result: 'pending')).isPending,
          isTrue);
    });

    test('exit reason labels', () {
      expect(
          NewListingShort.fromJson(_row(exitReason: 'STOP')).exitReasonLabel,
          'Stop-loss hit');
      expect(
          NewListingShort.fromJson(_row(exitReason: 'LOCK')).exitReasonLabel,
          'Profit locked early');
      expect(
          NewListingShort.fromJson(_row(exitReason: 'TIME')).exitReasonLabel,
          'Closed at time limit');
    });
  });

  group('ShortStats', () {
    test('win rate excludes pending, avg pnl only over closed trades', () {
      final signals = [
        NewListingShort.fromJson(_row(result: 'win', pnlPct: 50.0)),
        NewListingShort.fromJson(_row(result: 'loss', pnlPct: -30.0)),
        NewListingShort.fromJson(_row(result: 'loss', pnlPct: -27.0)),
        NewListingShort.fromJson(_row(result: 'pending')),
      ];
      final st = ShortStats.from(signals);
      expect(st.total, 4);
      expect(st.wins, 1);
      expect(st.losses, 2);
      expect(st.pending, 1);
      expect(st.closed, 3);
      expect(st.winRate, closeTo(1 / 3, 1e-9));
      // avg over the 3 CLOSED trades: (50 - 30 - 27) / 3
      expect(st.avgPnlPct, closeTo(-7 / 3, 1e-9));
    });

    test('no closed trades gives 0 win rate and 0 avg, not NaN', () {
      final st = ShortStats.from(
          [NewListingShort.fromJson(_row(result: 'pending'))]);
      expect(st.winRate, 0);
      expect(st.avgPnlPct, 0);
      expect(st.winRate.isNaN, isFalse);
    });
  });
}
