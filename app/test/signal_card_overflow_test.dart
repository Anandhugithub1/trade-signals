// Regression test: the feed card header must not overflow on a narrow phone.
// Adding the engine chip pushed the direction/result badges off-screen at
// 360dp, which is a common Android width (the reported bug).
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:zenviq/models/signal.dart';
import 'package:zenviq/widgets/signal_card.dart';
import 'package:zenviq/theme/app_theme.dart';

TradeSignal _sig(String strategy, {bool confirmed = false}) => TradeSignal(
      entryConfirmed: confirmed,
      id: 'x',
      pair: 'LTCUSDT',
      direction: SignalDirection.long,
      entry: 45.854,
      stopLoss: 45.417,
      takeProfit: 46.729,
      confidence: 75,
      timestamp: DateTime.now().subtract(const Duration(minutes: 57)),
      expiresAt: DateTime.now().add(const Duration(days: 2)),
      strategy: strategy,
    );

void main() {
  for (final w in [320.0, 360.0, 411.0]) {
    for (final s in ['legacy', 'donchian']) {
      testWidgets('no overflow at ${w}dp / $s', (tester) async {
        tester.view.physicalSize = Size(w, 800);
        tester.view.devicePixelRatio = 1.0;
        addTearDown(tester.view.reset);
        await tester.pumpWidget(MaterialApp(
          theme: AppTheme.dark,
          home: Scaffold(body: SignalCard(signal: _sig(s))),
        ));
        expect(tester.takeException(), isNull);
      });

      testWidgets('no overflow at ${w}dp / $s / compact', (tester) async {
        tester.view.physicalSize = Size(w, 800);
        tester.view.devicePixelRatio = 1.0;
        addTearDown(tester.view.reset);
        await tester.pumpWidget(MaterialApp(
          theme: AppTheme.dark,
          home: Scaffold(body: SignalCard(signal: _sig(s), compact: true)),
        ));
        expect(tester.takeException(), isNull);
      });

      // The "Entry Initiated / Waiting for fill" strip overflowed at narrow
      // widths even before the engine chip was added.
      testWidgets('no overflow at ${w}dp / $s / awaiting fill', (tester) async {
        tester.view.physicalSize = Size(w, 800);
        tester.view.devicePixelRatio = 1.0;
        addTearDown(tester.view.reset);
        await tester.pumpWidget(MaterialApp(
          theme: AppTheme.dark,
          home: Scaffold(
              body: SignalCard(signal: _sig(s, confirmed: false))),
        ));
        expect(tester.takeException(), isNull);
      });
    }
  }
}
