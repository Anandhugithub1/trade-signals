import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../models/signal.dart';
import '../models/new_listing_short.dart';
import '../models/monthly_summary.dart';
import '../services/supabase_service.dart';
import '../theme/app_colors.dart';
import '../widgets/error_view.dart';

class AnalyticsScreen extends StatefulWidget {
  const AnalyticsScreen({super.key});

  @override
  State<AnalyticsScreen> createState() => _AnalyticsScreenState();
}

class _AnalyticsScreenState extends State<AnalyticsScreen> {
  late Future<({
    List<TradeSignal> signals,
    List<NewListingShort> shorts,
    List<MonthlySummaryRow> summaries,
  })> _future;

  double _capital = 50.0;
  int _selectedMarketIndex = 0; // 0: All Algo Trades, 1: New Listing Shorts

  @override
  void initState() {
    super.initState();
    _load();
  }

  void _load() {
    _future = _fetchAnalyticsData();
  }

  Future<({
    List<TradeSignal> signals,
    List<NewListingShort> shorts,
    List<MonthlySummaryRow> summaries,
  })> _fetchAnalyticsData() async {
    final (signals, shorts, summaries) = await (
      SupabaseService.fetchSignals(),
      SupabaseService.fetchNewListingShorts(),
      SupabaseService.fetchMonthlySummary(market: 'crypto', limitMonths: 12),
    ).wait;
    return (signals: signals, shorts: shorts, summaries: summaries);
  }

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return Scaffold(
      backgroundColor: c.bg,
      appBar: AppBar(
        backgroundColor: c.surface,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        title: Text(
          'Analytics & Estimator',
          style: TextStyle(color: c.t1, fontSize: 18, fontWeight: FontWeight.w700),
        ),
        actions: [
          IconButton(
            icon: Icon(Icons.refresh_rounded, color: c.t2),
            onPressed: () => setState(_load),
          ),
        ],
      ),
      body: FutureBuilder(
        future: _future,
        builder: (context, snap) {
          if (snap.connectionState == ConnectionState.waiting) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snap.hasError) {
            return ErrorView(error: snap.error!, onRetry: () => setState(_load));
          }

          final data = snap.data!;
          final signals = data.signals;
          final shorts = data.shorts;
          final summaries = data.summaries;

          return ListView(
            padding: const EdgeInsets.all(20),
            physics: const BouncingScrollPhysics(),
            children: [
              // 1. Capital Estimator Widget
              _buildCapitalCard(c),
              const SizedBox(height: 16),

              // 2. Segment selector (Algo Trades vs New Listing Shorts)
              _buildMarketSelector(c),
              const SizedBox(height: 16),

              if (_selectedMarketIndex == 0) ...[
                // Algo Performance Overview
                _buildAlgoOverview(c, signals, summaries),
                const SizedBox(height: 20),

                // Per-Engine Comparison Breakdown (Algo 1, Algo 2, Algo 3)
                _buildEngineBreakdown(c, signals),
                const SizedBox(height: 20),

                // Monthly Performance Table
                _buildMonthlyTable(c, summaries, signals),
              ] else ...[
                // New Listing Shorts Overview
                _buildShortsOverview(c, shorts),
                const SizedBox(height: 20),

                // Shorts Trade List Analysis
                _buildShortsList(c, shorts),
              ],

              const SizedBox(height: 30),
            ],
          );
        },
      ),
    );
  }

  Widget _buildCapitalCard(AppColors c) {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: c.card,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: c.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                'CAPITAL ESTIMATOR',
                style: TextStyle(
                  color: c.t3,
                  fontSize: 11,
                  fontWeight: FontWeight.w700,
                  letterSpacing: 1.0,
                ),
              ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                decoration: BoxDecoration(
                  color: c.accent.withValues(alpha: 0.15),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Text(
                  'Simulated \$${_capital.toStringAsFixed(0)}',
                  style: TextStyle(color: c.accent, fontSize: 12, fontWeight: FontWeight.w700),
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Text(
            'See your projected dollar earnings if you trade each signal with \$${_capital.toStringAsFixed(0)} capital.',
            style: TextStyle(color: c.t2, fontSize: 13),
          ),
          const SizedBox(height: 16),

          // Quick preset buttons
          Row(
            children: [25, 50, 100, 250, 500].map((val) {
              final isSel = _capital == val.toDouble();
              return Expanded(
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 3),
                  child: GestureDetector(
                    onTap: () {
                      HapticFeedback.selectionClick();
                      setState(() => _capital = val.toDouble());
                    },
                    child: Container(
                      padding: const EdgeInsets.symmetric(vertical: 8),
                      decoration: BoxDecoration(
                        color: isSel ? c.accent : c.surface,
                        borderRadius: BorderRadius.circular(10),
                        border: Border.all(
                          color: isSel ? c.accent : c.border,
                        ),
                      ),
                      alignment: Alignment.center,
                      child: Text(
                        '\$$val',
                        style: TextStyle(
                          color: isSel ? Colors.white : c.t1,
                          fontSize: 12,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ),
                  ),
                ),
              );
            }).toList(),
          ),
          const SizedBox(height: 14),

          // Slider
          SliderTheme(
            data: SliderTheme.of(context).copyWith(
              activeTrackColor: c.accent,
              inactiveTrackColor: c.border,
              thumbColor: c.accent,
              trackHeight: 4,
            ),
            child: Slider(
              value: _capital,
              min: 10.0,
              max: 1000.0,
              divisions: 99,
              onChanged: (v) => setState(() => _capital = v),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildMarketSelector(AppColors c) {
    return Container(
      padding: const EdgeInsets.all(4),
      decoration: BoxDecoration(
        color: c.surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: c.border),
      ),
      child: Row(
        children: [
          Expanded(
            child: _marketTab(
              label: 'Algo Futures (3 Engines)',
              icon: Icons.bolt_rounded,
              selected: _selectedMarketIndex == 0,
              color: c,
              onTap: () => setState(() => _selectedMarketIndex = 0),
            ),
          ),
          Expanded(
            child: _marketTab(
              label: 'New Listing Shorts',
              icon: Icons.trending_down_rounded,
              selected: _selectedMarketIndex == 1,
              color: c,
              onTap: () => setState(() => _selectedMarketIndex = 1),
            ),
          ),
        ],
      ),
    );
  }

  Widget _marketTab({
    required String label,
    required IconData icon,
    required bool selected,
    required AppColors color,
    required VoidCallback onTap,
  }) {
    return GestureDetector(
      onTap: () {
        HapticFeedback.selectionClick();
        onTap();
      },
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 10),
        decoration: BoxDecoration(
          color: selected ? color.accent : Colors.transparent,
          borderRadius: BorderRadius.circular(10),
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(icon, size: 16, color: selected ? Colors.white : color.t2),
            const SizedBox(width: 6),
            Flexible(
              child: Text(
                label,
                style: TextStyle(
                  color: selected ? Colors.white : color.t2,
                  fontSize: 12,
                  fontWeight: selected ? FontWeight.w700 : FontWeight.w500,
                ),
                overflow: TextOverflow.ellipsis,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildAlgoOverview(AppColors c, List<TradeSignal> signals, List<MonthlySummaryRow> summaries) {
    final stats = summaries.isNotEmpty
        ? SignalStats.fromMonthlySummaries(summaries, signals)
        : SignalStats.from(signals);
    final totalR = stats.totalR;
    // Each 1R with 2x leverage on capital = capital * 2 * target_risk (~5% of stake)
    final dollarPerR = _capital * 0.05;
    final estimatedDollars = totalR * dollarPerR;
    final isPos = estimatedDollars >= 0;
    final dollarStr = '${isPos ? '+' : '-'}\$${estimatedDollars.abs().toStringAsFixed(1)}';
    final rStr = '${isPos ? '+' : ''}${totalR.toStringAsFixed(1)}R';
    final roiPct = _capital > 0 ? (estimatedDollars / _capital * 100) : 0.0;

    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            isPos ? const Color(0xFF064E3B) : const Color(0xFF7F1D1D),
            isPos ? const Color(0xFF047857) : const Color(0xFF991B1B),
          ],
        ),
        borderRadius: BorderRadius.circular(20),
        boxShadow: [
          BoxShadow(
            color: (isPos ? const Color(0xFF059669) : const Color(0xFFDC2626)).withValues(alpha: 0.3),
            blurRadius: 20,
            offset: const Offset(0, 8),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'ESTIMATED RETURN ON \$${_capital.toStringAsFixed(0)} CAPITAL',
            style: TextStyle(
              color: Colors.white.withValues(alpha: 0.7),
              fontSize: 11,
              fontWeight: FontWeight.w700,
              letterSpacing: 1.0,
            ),
          ),
          const SizedBox(height: 12),
          Row(
            crossAxisAlignment: CrossAxisAlignment.baseline,
            textBaseline: TextBaseline.alphabetic,
            children: [
              Text(
                dollarStr,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 36,
                  fontWeight: FontWeight.w900,
                  letterSpacing: -1,
                ),
              ),
              const SizedBox(width: 8),
              Text(
                '($rStr)',
                style: TextStyle(
                  color: Colors.white.withValues(alpha: 0.8),
                  fontSize: 16,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ],
          ),
          const SizedBox(height: 6),
          Text(
            'ROI: ${roiPct >= 0 ? '+' : ''}${roiPct.toStringAsFixed(1)}% across ${stats.closed} closed signals',
            style: TextStyle(color: Colors.white.withValues(alpha: 0.75), fontSize: 13),
          ),
          const SizedBox(height: 18),
          Divider(color: Colors.white.withValues(alpha: 0.2)),
          const SizedBox(height: 12),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              _metricBlock('Win Rate', '${(stats.winRate * 100).toStringAsFixed(1)}%'),
              _metricBlock('Signals Won', '${stats.wins}'),
              _metricBlock('Signals Lost', '${stats.losses}'),
              _metricBlock('Profit Factor', stats.profitFactor == double.infinity ? '∞' : stats.profitFactor.toStringAsFixed(2)),
            ],
          ),
        ],
      ),
    );
  }

  Widget _metricBlock(String label, String value) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: TextStyle(color: Colors.white.withValues(alpha: 0.6), fontSize: 11)),
        const SizedBox(height: 2),
        Text(value, style: const TextStyle(color: Colors.white, fontSize: 15, fontWeight: FontWeight.w700)),
      ],
    );
  }

  Widget _buildEngineBreakdown(AppColors c, List<TradeSignal> signals) {
    final a1Signals = signals.where((s) => s.strategy == 'donchian').toList();
    final a2Signals = signals.where((s) => s.strategy == 'algo2').toList();
    final a3Signals = signals.where((s) => s.strategy == 'algo3').toList();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'ALGORITHM BREAKDOWN',
          style: TextStyle(color: c.t3, fontSize: 12, fontWeight: FontWeight.w700, letterSpacing: 0.8),
        ),
        const SizedBox(height: 10),
        _engineCard(
          title: 'Algo 1: Trade-Signals Donchian 55',
          ratio: '1:3 R:R (+15% / -5%)',
          signals: a1Signals,
          accentColor: c.long,
          c: c,
        ),
        const SizedBox(height: 10),
        _engineCard(
          title: 'Algo 2: Sideways Regime Range',
          ratio: '1:2 R:R (+8% / -4%)',
          signals: a2Signals,
          accentColor: const Color(0xFF60A5FA),
          c: c,
        ),
        const SizedBox(height: 10),
        _engineCard(
          title: 'Algo 3: Bearish Macro Short',
          ratio: '1:2 R:R (+10% / -5%)',
          signals: a3Signals,
          accentColor: c.gold,
          c: c,
        ),
      ],
    );
  }

  Widget _engineCard({
    required String title,
    required String ratio,
    required List<TradeSignal> signals,
    required Color accentColor,
    required AppColors c,
  }) {
    final stats = SignalStats.from(signals);
    final totalR = stats.totalR;
    final dollarPerR = _capital * 0.05;
    final estDollar = totalR * dollarPerR;
    final isPos = estDollar >= 0;
    final dollarStr = '${isPos ? '+' : '-'}\$${estDollar.abs().toStringAsFixed(1)}';
    final rStr = '${isPos ? '+' : ''}${totalR.toStringAsFixed(1)}R';

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: c.card,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: c.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(title, style: TextStyle(color: c.t1, fontSize: 14, fontWeight: FontWeight.w700)),
                    const SizedBox(height: 2),
                    Text(ratio, style: TextStyle(color: c.t3, fontSize: 11)),
                  ],
                ),
              ),
              Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Text(
                    dollarStr,
                    style: TextStyle(
                      color: isPos ? c.long : c.short,
                      fontSize: 16,
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                  Text(
                    rStr,
                    style: TextStyle(color: c.t3, fontSize: 11, fontWeight: FontWeight.w600),
                  ),
                ],
              ),
            ],
          ),
          const SizedBox(height: 12),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text('Trades: ${stats.total}', style: TextStyle(color: c.t2, fontSize: 12)),
              Text('W/L: ${stats.wins}/${stats.losses}', style: TextStyle(color: c.t2, fontSize: 12)),
              Text('Win Rate: ${(stats.winRate * 100).toStringAsFixed(0)}%', style: TextStyle(color: accentColor, fontSize: 12, fontWeight: FontWeight.w700)),
              Text('PF: ${stats.profitFactor == double.infinity ? '∞' : stats.profitFactor.toStringAsFixed(2)}', style: TextStyle(color: c.t2, fontSize: 12)),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildMonthlyTable(AppColors c, List<MonthlySummaryRow> summaries, List<TradeSignal> signals) {
    final cryptoSummaries = summaries.where((m) => m.market == 'crypto').toList();
    if (cryptoSummaries.isEmpty) {
      return const SizedBox.shrink();
    }

    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: c.card,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: c.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text('MONTHLY PERFORMANCE', style: TextStyle(color: c.t3, fontSize: 11, fontWeight: FontWeight.w700, letterSpacing: 0.8)),
              Text('Est. for \$${_capital.toStringAsFixed(0)}', style: TextStyle(color: c.accent, fontSize: 11, fontWeight: FontWeight.w600)),
            ],
          ),
          const SizedBox(height: 14),
          ...cryptoSummaries.map((m) {
            // pnl in monthly_summary is total cumulative %
            final pnlPct = m.pnl;
            final estMonthUsd = _capital * (pnlPct / 100);
            final isPos = estMonthUsd >= 0;
            final monthStr = m.month.length >= 7 ? m.month.substring(0, 7) : m.month;
            final dollarStr = '${isPos ? '+' : '-'}\$${estMonthUsd.abs().toStringAsFixed(1)}';

            return Padding(
              padding: const EdgeInsets.only(bottom: 12),
              child: Row(
                children: [
                  Expanded(
                    flex: 3,
                    child: Text(monthStr, style: TextStyle(color: c.t1, fontSize: 13, fontWeight: FontWeight.w600)),
                  ),
                  Expanded(
                    flex: 3,
                    child: Text('${m.wins}W / ${m.losses}L', style: TextStyle(color: c.t2, fontSize: 12)),
                  ),
                  Expanded(
                    flex: 3,
                    child: Text(
                      m.winRate != null ? '${m.winRate!.toStringAsFixed(0)}%' : '—',
                      style: TextStyle(
                        color: (m.winRate ?? 0) >= 50 ? c.long : c.short,
                        fontSize: 12,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ),
                  Expanded(
                    flex: 4,
                    child: Text(
                      dollarStr,
                      textAlign: TextAlign.end,
                      style: TextStyle(
                        color: isPos ? c.long : c.short,
                        fontSize: 13,
                        fontWeight: FontWeight.w800,
                      ),
                    ),
                  ),
                ],
              ),
            );
          }),
        ],
      ),
    );
  }

  Widget _buildShortsOverview(AppColors c, List<NewListingShort> shorts) {
    final closed = shorts.where((s) => s.result != ShortResult.pending).toList();
    final wins = closed.where((s) => s.result == ShortResult.win).length;
    final losses = closed.where((s) => s.result == ShortResult.loss).length;
    final winRate = closed.isNotEmpty ? (wins / closed.length) : 0.0;

    // Cumulative % PnL
    double totalPnlPct = 0;
    for (final s in closed) {
      if (s.pnlPct != null) {
        totalPnlPct += s.pnlPct!;
      }
    }

    final estimatedDollarProfit = _capital * (totalPnlPct / 100);
    final isPos = estimatedDollarProfit >= 0;
    final dollarStr = '${isPos ? '+' : '-'}\$${estimatedDollarProfit.abs().toStringAsFixed(1)}';
    final avgDrop = closed.isNotEmpty ? (totalPnlPct / closed.length) : 0.0;

    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            isPos ? const Color(0xFF1E3A8A) : const Color(0xFF7F1D1D),
            isPos ? const Color(0xFF2563EB) : const Color(0xFF991B1B),
          ],
        ),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'NEW LISTING SHORTS (\$${_capital.toStringAsFixed(0)} CAPITAL)',
            style: TextStyle(color: Colors.white.withValues(alpha: 0.7), fontSize: 11, fontWeight: FontWeight.w700, letterSpacing: 1.0),
          ),
          const SizedBox(height: 12),
          Text(
            dollarStr,
            style: const TextStyle(color: Colors.white, fontSize: 36, fontWeight: FontWeight.w900, letterSpacing: -1),
          ),
          const SizedBox(height: 6),
          Text(
            'Cumulative PnL: ${totalPnlPct >= 0 ? '+' : ''}${totalPnlPct.toStringAsFixed(1)}% across ${closed.length} closed listing dumps',
            style: TextStyle(color: Colors.white.withValues(alpha: 0.8), fontSize: 13),
          ),
          const SizedBox(height: 18),
          Divider(color: Colors.white.withValues(alpha: 0.2)),
          const SizedBox(height: 12),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              _metricBlock('Win Rate', '${(winRate * 100).toStringAsFixed(1)}%'),
              _metricBlock('Dumps Captured', '$wins'),
              _metricBlock('Stopped Out', '$losses'),
              _metricBlock('Avg Drop', '${avgDrop >= 0 ? '+' : ''}${avgDrop.toStringAsFixed(1)}%'),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildShortsList(AppColors c, List<NewListingShort> shorts) {
    if (shorts.isEmpty) {
      return Center(child: Text('No listing shorts recorded yet.', style: TextStyle(color: c.t3)));
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'RECENT LISTING DUMPS',
          style: TextStyle(color: c.t3, fontSize: 12, fontWeight: FontWeight.w700, letterSpacing: 0.8),
        ),
        const SizedBox(height: 10),
        ...shorts.take(8).map((s) {
          final isWin = s.result == ShortResult.win;
          final isPending = s.result == ShortResult.pending;
          final pnl = s.pnlPct ?? 0.0;
          final estUsd = _capital * (pnl / 100);
          final pnlSign = pnl >= 0 ? '+' : '-';
          final estUsdStr = '$pnlSign\$${estUsd.abs().toStringAsFixed(2)}';
          final pnlPctStr = '${pnl >= 0 ? '+' : ''}${pnl.toStringAsFixed(1)}%';

          return Container(
            margin: const EdgeInsets.only(bottom: 8),
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: c.card,
              borderRadius: BorderRadius.circular(14),
              border: Border.all(color: c.border),
            ),
            child: Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(s.symbol, style: TextStyle(color: c.t1, fontSize: 14, fontWeight: FontWeight.w700)),
                      const SizedBox(height: 2),
                      Text('Entry: \$${s.entry.toStringAsFixed(4)}', style: TextStyle(color: c.t3, fontSize: 11)),
                    ],
                  ),
                ),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                  decoration: BoxDecoration(
                    color: (isPending ? c.gold : isWin ? c.long : c.short).withValues(alpha: 0.15),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Text(
                    isPending ? 'ACTIVE' : isWin ? 'WON' : 'LOSS',
                    style: TextStyle(
                      color: isPending ? c.gold : isWin ? c.long : c.short,
                      fontSize: 11,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ),
                const SizedBox(width: 14),
                Column(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    Text(
                      isPending ? '—' : estUsdStr,
                      style: TextStyle(
                        color: pnl >= 0 ? c.long : c.short,
                        fontSize: 14,
                        fontWeight: FontWeight.w800,
                      ),
                    ),
                    Text(
                      isPending ? 'Pending' : pnlPctStr,
                      style: TextStyle(color: c.t3, fontSize: 11),
                    ),
                  ],
                ),
              ],
            ),
          );
        }),
      ],
    );
  }
}
