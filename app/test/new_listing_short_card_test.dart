// Overflow guard for the "Short New Listings" card, matching the
// convention in signal_card_overflow_test.dart / crypto_option_card_test.dart.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:zenviq/models/new_listing_short.dart';
import 'package:zenviq/widgets/new_listing_short_card.dart';
import 'package:zenviq/theme/app_theme.dart';

NewListingShort _sig({
  ShortResult result = ShortResult.pending,
  double? pnlPct,
  String? exitReason,
}) =>
    NewListingShort(
      id: 'x',
      symbol: 'DOSUSDT',
      listingDate: DateTime.now().subtract(const Duration(days: 33)),
      daysSinceListing: 32.8,
      entry: 0.2223,
      stopPrice: 0.28899,
      lockPrice: 0.11115,
      result: result,
      pnlPct: pnlPct,
      exitReason: exitReason,
      timestamp: DateTime.now().subtract(const Duration(hours: 2)),
      expiresAt: DateTime.now().add(const Duration(days: 28)),
      note: 'Listed 33d ago. Short at 0.2223.',
    );

Future<void> _pump(WidgetTester tester, NewListingShort s, {double width = 411}) async {
  tester.view.physicalSize = Size(width, 1000);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    theme: AppTheme.dark,
    home: Scaffold(body: SingleChildScrollView(child: NewListingShortCard(signal: s))),
  ));
}

void main() {
  testWidgets('shows asset, SHORT badge, and price levels', (tester) async {
    await _pump(tester, _sig());
    expect(find.text('DOS'), findsOneWidget);
    expect(find.text('SHORT'), findsOneWidget);
    expect(find.textContaining('Listed'), findsOneWidget);
  });

  testWidgets('shows pnl for a closed loss', (tester) async {
    await _pump(tester,
        _sig(result: ShortResult.loss, pnlPct: -27.0, exitReason: 'STOP'));
    expect(find.textContaining('-27.0%'), findsOneWidget);
    expect(find.textContaining('Stop-loss hit'), findsOneWidget);
  });

  testWidgets('shows pnl for a locked-in win', (tester) async {
    await _pump(tester,
        _sig(result: ShortResult.win, pnlPct: 50.0, exitReason: 'LOCK'));
    expect(find.textContaining('+50.0%'), findsOneWidget);
    expect(find.textContaining('Profit locked early'), findsOneWidget);
  });

  for (final w in [320.0, 360.0, 411.0]) {
    testWidgets('no overflow at ${w}dp / pending', (tester) async {
      await _pump(tester, _sig(), width: w);
      expect(tester.takeException(), isNull);
    });

    testWidgets('no overflow at ${w}dp / closed', (tester) async {
      await _pump(
          tester,
          _sig(result: ShortResult.win, pnlPct: 50.0, exitReason: 'LOCK'),
          width: w);
      expect(tester.takeException(), isNull);
    });
  }
}
