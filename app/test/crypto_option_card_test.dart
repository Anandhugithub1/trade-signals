// Widget tests for the Options tab card: it must render the real contract
// cost, and must visibly warn when the named contract settles before the
// trade is due to close (the 2026-08-26 live bug).
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:zenviq/models/crypto_option_signal.dart';
import 'package:zenviq/widgets/crypto_option_card.dart';
import 'package:zenviq/theme/app_theme.dart';

CryptoOptionSignal _sig({
  double? premiumUsd = 972.34,
  double? premiumCostUsd = 415.56,
  double? markIv = 31.21,
  DateTime? optionExpiry,
  DateTime? expiresAt,
  OptionResult result = OptionResult.pending,
  double? pnlUsd,
}) =>
    CryptoOptionSignal(
      id: 'x',
      symbol: 'BTCUSDT',
      side: OptionSide.put,
      strike: 81000,
      optionExpiry: optionExpiry ?? DateTime.now().add(const Duration(days: 4)),
      instrument: 'BTC-8SEP26-81000-P',
      size: 0.427378,
      premiumUsd: premiumUsd,
      premiumCostUsd: premiumCostUsd,
      markIv: markIv,
      spot: 81104.4,
      entry: 77307.7,
      stopPrice: 78243.64,
      targetPrice: 76137.76,
      maxLossUsd: 200,
      rsi: 49.88,
      atr: 467.97,
      result: result,
      pnlUsd: pnlUsd,
      timestamp: DateTime.now().subtract(const Duration(hours: 2)),
      expiresAt: expiresAt ?? DateTime.now().add(const Duration(days: 3)),
      note: 'Downtrend: Supertrend down, EMA9<EMA21, RSI lost 50, ADX 26.',
    );

Future<void> _pump(WidgetTester tester, CryptoOptionSignal s,
    {double width = 411}) async {
  tester.view.physicalSize = Size(width, 1200);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    theme: AppTheme.dark,
    home: Scaffold(body: SingleChildScrollView(child: CryptoOptionCard(signal: s))),
  ));
}

void main() {
  testWidgets('shows the contract, premium and true outlay', (tester) async {
    await _pump(tester, _sig());
    expect(find.text('BTC-8SEP26-81000-P'), findsOneWidget);
    expect(find.text('BUY PUT'), findsOneWidget);
    // Premium per contract AND the amount actually paid must both appear.
    expect(
      find.textContaining(r'$972.34'),
      findsOneWidget,
      reason: 'premium per contract should be shown',
    );
    expect(
      find.textContaining(r'$415.56'),
      findsWidgets,
      reason: 'total outlay should be shown',
    );
  });

  testWidgets('states max-at-risk is the full premium, not the modelled stop',
      (tester) async {
    await _pump(tester, _sig());
    // The stop-out figure and the true capital at risk are different numbers
    // and the card must not present $200 as the worst case.
    expect(find.textContaining('max at risk'), findsOneWidget);
    expect(find.textContaining('full premium'), findsOneWidget);
  });

  testWidgets('falls back gracefully when Deribit gave no premium',
      (tester) async {
    await _pump(tester,
        _sig(premiumUsd: null, premiumCostUsd: null, markIv: null));
    expect(find.textContaining('check Deribit'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('warns when the contract expires before the trade closes',
      (tester) async {
    // Reproduces the real bug: contract settles a day before square-off.
    await _pump(
      tester,
      _sig(
        optionExpiry: DateTime.now().add(const Duration(days: 1)),
        expiresAt: DateTime.now().add(const Duration(days: 3)),
      ),
    );
    expect(find.textContaining('expires before the trade'), findsOneWidget);
    expect(find.byIcon(Icons.warning_amber_rounded), findsOneWidget);
  });

  testWidgets('no warning for a correctly-dated contract', (tester) async {
    await _pump(
      tester,
      _sig(
        optionExpiry: DateTime.now().add(const Duration(days: 5)),
        expiresAt: DateTime.now().add(const Duration(days: 3)),
      ),
    );
    expect(find.byIcon(Icons.warning_amber_rounded), findsNothing);
  });

  testWidgets('renders a closed losing trade with its P&L', (tester) async {
    await _pump(tester, _sig(result: OptionResult.loss, pnlUsd: -200));
    expect(find.textContaining('-200'), findsWidgets);
  });

  // Narrow-phone overflow guard, same convention as signal_card_overflow_test.
  for (final w in [320.0, 360.0, 411.0]) {
    testWidgets('no overflow at ${w}dp', (tester) async {
      await _pump(tester, _sig(), width: w);
      expect(tester.takeException(), isNull);
    });

    testWidgets('no overflow at ${w}dp with expiry warning', (tester) async {
      await _pump(
        tester,
        _sig(
          optionExpiry: DateTime.now().add(const Duration(days: 1)),
          expiresAt: DateTime.now().add(const Duration(days: 3)),
        ),
        width: w,
      );
      expect(tester.takeException(), isNull);
    });
  }
}
