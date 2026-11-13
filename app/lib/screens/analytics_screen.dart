import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../models/signal.dart';
import '../models/new_listing_short.dart';
import '../models/monthly_summary.dart';
import '../services/supabase_service.dart';
import '../theme/app_colors.dart';
import '../widgets/error_view.dart';
import '../widgets/shimmer.dart';

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
  int _selectedMarketIndex = 0; // 0: Algo Futures, 1: New Listing Shorts

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
      body: SafeArea(
        child: FutureBuilder(
          future: _future,
          builder: (context, snap) {
            if (snap.connectionState == ConnectionState.waiting) {
              return _buildLoading(c);
            }
            if (snap.hasError) {
              return ErrorView(error: snap.error!, onRetry: () => setState(_load));
            }

            final data = snap.data!;
            final signals = data.signals;
            final shorts = data.shorts;
            final summaries = data.summaries;

            return RefreshIndicator(
              onRefresh: () async => setState(_load),
              color: c.accent,
              backgroundColor: c.card,
              child: ListView(
                padding: const EdgeInsets.symmetric(horizontal: 20),
                physics: const AlwaysScrollableScrollPhysics(
                  parent: BouncingScrollPhysics(),
                ),
                children: [
                  const SizedBox(height: 20),
                  _buildHeader(c),
                  const SizedBox(height: 16),

                  // 1. Capital Estimator Card
                  _buildCapitalEstimatorCard(c),
                  const SizedBox(height: 14),

                  // 2. Segment selector (Algo Futures vs New Listing Shorts)
                  _buildMarketSelector(c),
                  const SizedBox(height: 16),

                  if (_selectedMarketIndex == 0) ...[
                    // Algo Performance Hero Card
                    _buildAlgoHeroCard(c, signals, summaries),
                    const SizedBox(height: 18),

                    // Engine Breakdown (Algo 1, Algo 2, Algo 3)
                    _buildEngineBreakdown(c, signals),
                    const SizedBox(height: 18),

                    // Monthly Performance Table
                    _buildMonthlyTable(c, summaries, signals),
                  ] else ...[
                    // New Listing Shorts Hero Card
                    _buildShortsHeroCard(c, shorts),
                    const SizedBox(height: 18),

                    // Shorts Breakdown List
                    _buildShortsList(c, shorts),
                  ],

                  const SizedBox(height: 32),
                ],
              ),
            );
          },
        ),
      ),
    );
  }

  Widget _buildLoading(AppColors c) {
    return ListView(
      padding: const EdgeInsets.symmetric(horizontal: 20),
      physics: const NeverScrollableScrollPhysics(),
      children: [
        const SizedBox(height: 20),
        _buildHeader(c),
        const SizedBox(height: 20),
        ...[160.0, 48.0, 200.0, 110.0, 110.0, 110.0].map(
          (h) => Padding(
            padding: const EdgeInsets.only(bottom: 14),
            child: ShimmerBox(height: h),
          ),
        ),
      ],
    );
  }

  Widget _buildHeader(AppColors c) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              'Analytics & Estimator',
              style: TextStyle(
                color: c.t1,
                fontSize: 24,
                fontWeight: FontWeight.w800,
                letterSpacing: -0.5,
              ),
            ),
            const SizedBox(height: 2),
            Text(
              'Simulate returns & track multi-engine P&L',
              style: TextStyle(color: c.t2, fontSize: 12),
            ),
          ],
        ),
        GestureDetector(
          onTap: () {
            HapticFeedback.selectionClick();
            setState(_load);
          },
          child: Container(
            width: 38,
            height: 38,
            decoration: BoxDecoration(
              color: c.accentBg,
              shape: BoxShape.circle,
              border: Border.all(color: c.accent.withValues(alpha: 0.3)),
            ),
            child: Icon(Icons.refresh_rounded, color: c.accent, size: 19),
          ),
        ),
      ],
    );
  }

  // --- CAPITAL ESTIMATOR CARD ---
  Widget _buildCapitalEstimatorCard(AppColors c) {
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
              Text(
                'CAPITAL ESTIMATOR',
                style: TextStyle(
                  color: c.t3,
                  fontSize: 11,
                  fontWeight: FontWeight.w700,
                  letterSpacing: 0.8,
                ),
              ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                decoration: BoxDecoration(
                  color: c.accentBg,
                  borderRadius: BorderRadius.circular(6),
                  border: Border.all(color: c.accent.withValues(alpha: 0.3)),
                ),
                child: Text(
                  'Simulated \$${_capital.toStringAsFixed(0)}',
                  style: TextStyle(
                    color: c.accent,
                    fontSize: 11,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            'See your projected dollar earnings if you trade each signal with \$${_capital.toStringAsFixed(0)} capital.',
            style: TextStyle(color: c.t2, fontSize: 12, height: 1.4),
          ),
          const SizedBox(height: 14),

          // Preset Chips ($25, $50, $100, $250, $500)
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
                        borderRadius: BorderRadius.circular(8),
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
                          fontWeight: isSel ? FontWeight.w700 : FontWeight.w600,
                        ),
                      ),
                    ),
                  ),
                ),
              );
            }).toList(),
          ),
          const SizedBox(height: 10),

          // Slider
          SliderTheme(
            data: SliderTheme.of(context).copyWith(
              activeTrackColor: c.accent,
              inactiveTrackColor: c.border,
              thumbColor: c.accent,
              trackHeight: 4,
              overlayShape: const RoundSliderOverlayShape(overlayRadius: 14),
              thumbShape: const RoundSliderThumbShape(enabledThumbRadius: 7),
            ),
            child: Slider(
              value: _capital,
              min: 10.0,
              max: 1000.0,
              divisions: 99,
              onChanged: (v) => setState(() => _capital = v),
            ),
          ),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 6),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text('\$10 min', style: TextStyle(color: c.t3, fontSize: 10, fontWeight: FontWeight.w500)),
                Text('Drag to adjust custom capital', style: TextStyle(color: c.t3, fontSize: 10)),
                Text('\$1,000 max', style: TextStyle(color: c.t3, fontSize: 10, fontWeight: FontWeight.w500)),
              ],
            ),
          ),
        ],
      ),
    );
  }

  // --- SEGMENT SELECTOR ---
  Widget _buildMarketSelector(AppColors c) {
    return Container(
      padding: const EdgeInsets.all(4),
      decoration: BoxDecoration(
        color: c.surface,
        borderRadius: BorderRadius.circular(12),
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
        padding: const EdgeInsets.symmetric(vertical: 9),
        decoration: BoxDecoration(
          color: selected ? color.accent : Colors.transparent,
          borderRadius: BorderRadius.circular(8),
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              icon,
              size: 15,
              color: selected ? Colors.white : color.t2,
            ),
            const SizedBox(width: 6),
            Flexible(
              child: Text(
                label,
                style: TextStyle(
                  color: selected ? Colors.white : color.t2,
                  fontSize: 12,
                  fontWeight: selected ? FontWeight.w700 : FontWeight.w600,
                ),
                overflow: TextOverflow.ellipsis,
              ),
            ),
          ],
        ),
      ),
    );
  }

  // --- ALGO HERO PERFORMANCE CARD (Standard Zenviq Blue Gradient) ---
  Widget _buildAlgoHeroCard(
    AppColors c,
    List<TradeSignal> signals,
    List<MonthlySummaryRow> summaries,
  ) {
    final stats = summaries.isNotEmpty
        ? SignalStats.fromMonthlySummaries(summaries, signals)
        : SignalStats.from(signals);
    final totalR = stats.totalR;
    final dollarPerR = _capital * 0.05;
    final estimatedDollars = totalR * dollarPerR;
    final isPos = estimatedDollars >= 0;
    final sign = isPos ? '+' : '-';
    final dollarStr = '$sign\$${estimatedDollars.abs().toStringAsFixed(1)}';
    final rStr = '${isPos ? '+' : ''}${totalR.toStringAsFixed(1)}R';
    final winPct = stats.winRate;

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(20, 20, 20, 18),
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [Color(0xFF1E3A8A), Color(0xFF1D4ED8), Color(0xFF2563EB)],
          stops: [0.0, 0.5, 1.0],
        ),
        borderRadius: BorderRadius.circular(18),
        boxShadow: [
          BoxShadow(
            color: const Color(0xFF2563EB).withValues(alpha: 0.35),
            blurRadius: 24,
            offset: const Offset(0, 10),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                'PROJECTED RETURN (1 YEAR)',
                style: TextStyle(
                  color: Colors.white.withValues(alpha: 0.7),
                  fontSize: 11,
                  fontWeight: FontWeight.w700,
                  letterSpacing: 0.8,
                ),
              ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                decoration: BoxDecoration(
                  color: Colors.white.withValues(alpha: 0.16),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Text(
                  'Based on \$${_capital.toStringAsFixed(0)} / trade',
                  style: TextStyle(
                    color: Colors.white.withValues(alpha: 0.9),
                    fontSize: 11,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 14),

          // Big Dollar Figure
          Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Text(
                dollarStr,
                style: TextStyle(
                  color: isPos ? const Color(0xFF86EFAC) : const Color(0xFFFCA5A5),
                  fontSize: 44,
                  fontWeight: FontWeight.w900,
                  letterSpacing: -1.5,
                  height: 1.0,
                ),
              ),
              const SizedBox(width: 10),
              Padding(
                padding: const EdgeInsets.only(bottom: 4),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      'Profit (USD)',
                      style: TextStyle(
                        color: Colors.white.withValues(alpha: 0.8),
                        fontSize: 13,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    const SizedBox(height: 1),
                    Text(
                      '$rStr realized',
                      style: TextStyle(
                        color: Colors.white.withValues(alpha: 0.65),
                        fontSize: 11,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),

          // Win Rate Indicator Bar
          ClipRRect(
            borderRadius: BorderRadius.circular(6),
            child: Stack(
              children: [
                Container(
                  height: 6,
                  width: double.infinity,
                  color: Colors.white.withValues(alpha: 0.15),
                ),
                FractionallySizedBox(
                  widthFactor: winPct.clamp(0.0, 1.0),
                  child: Container(
                    height: 6,
                    decoration: BoxDecoration(
                      color: Colors.white,
                      borderRadius: BorderRadius.circular(6),
                    ),
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),

          // 4 Stats Columns
          Row(
            children: [
              _heroStat(
                value: '${(winPct * 100).toStringAsFixed(0)}%',
                label: 'Win Rate',
                color: const Color(0xFF86EFAC),
              ),
              _heroStatDivider(),
              _heroStat(
                value: '${stats.wins}',
                label: 'Won',
                color: const Color(0xFF86EFAC),
              ),
              _heroStatDivider(),
              _heroStat(
                value: '${stats.losses}',
                label: 'Lost',
                color: const Color(0xFFFCA5A5),
              ),
              _heroStatDivider(),
              _heroStat(
                value: stats.profitFactor == double.infinity ? '∞' : stats.profitFactor.toStringAsFixed(2),
                label: 'Profit Factor',
                color: Colors.white,
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _heroStat({
    required String value,
    required String label,
    required Color color,
  }) {
    return Expanded(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          Text(
            value,
            style: TextStyle(
              color: color,
              fontSize: 18,
              fontWeight: FontWeight.w800,
              letterSpacing: -0.5,
            ),
          ),
          const SizedBox(height: 2),
          Text(
            label,
            style: TextStyle(
              color: Colors.white.withValues(alpha: 0.55),
              fontSize: 10,
              fontWeight: FontWeight.w500,
            ),
          ),
        ],
      ),
    );
  }

  Widget _heroStatDivider() {
    return Container(
      width: 1,
      height: 28,
      color: Colors.white.withValues(alpha: 0.15),
      margin: const EdgeInsets.symmetric(horizontal: 2),
    );
  }

  // --- ALGORITHM BREAKDOWN (3 CARDS) ---
  Widget _buildEngineBreakdown(AppColors c, List<TradeSignal> signals) {
    final a1Signals = signals.where((s) => s.strategy == 'donchian').toList();
    final a2Signals = signals.where((s) => s.strategy == 'algo2').toList();
    final a3Signals = signals.where((s) => s.strategy == 'algo3').toList();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'ALGORITHM BREAKDOWN',
          style: TextStyle(
            color: c.t3,
            fontSize: 11,
            fontWeight: FontWeight.w700,
            letterSpacing: 0.8,
          ),
        ),
        const SizedBox(height: 10),
        _engineCard(
          title: 'Algo 1: Donchian Breakout 55',
          ratio: '1:3 R:R (+15% / -5%) · 10d max hold',
          signals: a1Signals,
          accentColor: c.long,
          c: c,
        ),
        const SizedBox(height: 10),
        _engineCard(
          title: 'Algo 2: Sideways Regime Range',
          ratio: '1:2 R:R (+8% / -4%) · 6d max hold',
          signals: a2Signals,
          accentColor: c.accent,
          c: c,
        ),
        const SizedBox(height: 10),
        _engineCard(
          title: 'Algo 3: Bearish Macro Short',
          ratio: '1:2 R:R (+10% / -5%) · 10d max hold',
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
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Container(
                          width: 8,
                          height: 8,
                          decoration: BoxDecoration(
                            color: accentColor,
                            shape: BoxShape.circle,
                          ),
                        ),
                        const SizedBox(width: 8),
                        Expanded(
                          child: Text(
                            title,
                            style: TextStyle(
                              color: c.t1,
                              fontSize: 14,
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 4),
                    Padding(
                      padding: const EdgeInsets.only(left: 16),
                      child: Text(
                        ratio,
                        style: TextStyle(color: c.t3, fontSize: 11),
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 8),
              Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Text(
                    dollarStr,
                    style: TextStyle(
                      color: isPos ? c.long : c.short,
                      fontSize: 17,
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    rStr,
                    style: TextStyle(
                      color: c.t3,
                      fontSize: 11,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ],
              ),
            ],
          ),
          const SizedBox(height: 14),
          Divider(color: c.border.withValues(alpha: 0.6), height: 1),
          const SizedBox(height: 12),

          // 4 Aligned Columns
          Row(
            children: [
              _statColumn(label: 'TRADES', value: '${stats.total}', color: c.t1, c: c),
              _statColumn(label: 'W / L', value: '${stats.wins}W / ${stats.losses}L', color: c.t1, c: c),
              _statColumn(
                label: 'WIN RATE',
                value: stats.closed == 0 ? '—' : '${(stats.winRate * 100).toStringAsFixed(0)}%',
                color: accentColor,
                c: c,
              ),
              _statColumn(
                label: 'PF',
                value: stats.closed == 0
                    ? '—'
                    : (stats.profitFactor == double.infinity ? '∞' : stats.profitFactor.toStringAsFixed(2)),
                color: c.t1,
                c: c,
                alignRight: true,
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _statColumn({
    required String label,
    required String value,
    required Color color,
    required AppColors c,
    bool alignRight = false,
  }) {
    return Expanded(
      child: Column(
        crossAxisAlignment: alignRight ? CrossAxisAlignment.end : CrossAxisAlignment.start,
        children: [
          Text(
            label,
            style: TextStyle(
              color: c.t3,
              fontSize: 10,
              fontWeight: FontWeight.w600,
              letterSpacing: 0.5,
            ),
          ),
          const SizedBox(height: 2),
          Text(
            value,
            style: TextStyle(
              color: color,
              fontSize: 13,
              fontWeight: FontWeight.w700,
            ),
          ),
        ],
      ),
    );
  }

  // --- MONTHLY PERFORMANCE TABLE ---
  Widget _buildMonthlyTable(
    AppColors c,
    List<MonthlySummaryRow> summaries,
    List<TradeSignal> signals,
  ) {
    final cryptoSummaries = summaries.where((m) => m.market == 'crypto').toList();
    if (cryptoSummaries.isEmpty) {
      return const SizedBox.shrink();
    }

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
              Text(
                'MONTHLY PERFORMANCE',
                style: TextStyle(
                  color: c.t3,
                  fontSize: 11,
                  fontWeight: FontWeight.w700,
                  letterSpacing: 0.8,
                ),
              ),
              Text(
                'Est. for \$${_capital.toStringAsFixed(0)} / trade',
                style: TextStyle(
                  color: c.accent,
                  fontSize: 11,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ],
          ),
          const SizedBox(height: 14),

          // Table Column Headers
          Row(
            children: [
              Expanded(
                flex: 4,
                child: Text('MONTH', style: TextStyle(color: c.t3, fontSize: 10, fontWeight: FontWeight.w700)),
              ),
              Expanded(
                flex: 3,
                child: Text('RECORD', style: TextStyle(color: c.t3, fontSize: 10, fontWeight: FontWeight.w700)),
              ),
              Expanded(
                flex: 3,
                child: Text('WIN RATE', textAlign: TextAlign.center, style: TextStyle(color: c.t3, fontSize: 10, fontWeight: FontWeight.w700)),
              ),
              Expanded(
                flex: 4,
                child: Text('EST. P&L', textAlign: TextAlign.end, style: TextStyle(color: c.t3, fontSize: 10, fontWeight: FontWeight.w700)),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Divider(color: c.border, height: 1),
          const SizedBox(height: 8),

          // Table Rows
          ...cryptoSummaries.map((m) {
            final pnlPct = m.pnl;
            final estMonthUsd = _capital * (pnlPct / 100);
            final isPos = estMonthUsd >= 0;
            final monthStr = _formatMonth(m.month);
            final dollarStr = '${isPos ? '+' : '-'}\$${estMonthUsd.abs().toStringAsFixed(1)}';

            return Padding(
              padding: const EdgeInsets.symmetric(vertical: 8),
              child: Row(
                children: [
                  Expanded(
                    flex: 4,
                    child: Text(
                      monthStr,
                      style: TextStyle(color: c.t1, fontSize: 13, fontWeight: FontWeight.w600),
                    ),
                  ),
                  Expanded(
                    flex: 3,
                    child: Text(
                      '${m.wins}W / ${m.losses}L',
                      style: TextStyle(color: c.t2, fontSize: 12),
                    ),
                  ),
                  Expanded(
                    flex: 3,
                    child: Text(
                      m.winRate != null ? '${m.winRate!.toStringAsFixed(0)}%' : '—',
                      textAlign: TextAlign.center,
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

  // --- NEW LISTING SHORTS HERO CARD ---
  Widget _buildShortsHeroCard(AppColors c, List<NewListingShort> shorts) {
    final closed = shorts.where((s) => s.result != ShortResult.pending).toList();
    final wins = closed.where((s) => s.result == ShortResult.win).length;
    final losses = closed.where((s) => s.result == ShortResult.loss).length;
    final winRate = closed.isNotEmpty ? (wins / closed.length) : 0.0;

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
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(20, 20, 20, 18),
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [Color(0xFF1E3A8A), Color(0xFF1D4ED8), Color(0xFF2563EB)],
          stops: [0.0, 0.5, 1.0],
        ),
        borderRadius: BorderRadius.circular(18),
        boxShadow: [
          BoxShadow(
            color: const Color(0xFF2563EB).withValues(alpha: 0.35),
            blurRadius: 24,
            offset: const Offset(0, 10),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                'NEW LISTING SHORTS (PROJECTED)',
                style: TextStyle(
                  color: Colors.white.withValues(alpha: 0.7),
                  fontSize: 11,
                  fontWeight: FontWeight.w700,
                  letterSpacing: 0.8,
                ),
              ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                decoration: BoxDecoration(
                  color: Colors.white.withValues(alpha: 0.16),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Text(
                  'Based on \$${_capital.toStringAsFixed(0)} / trade',
                  style: TextStyle(
                    color: Colors.white.withValues(alpha: 0.9),
                    fontSize: 11,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 14),

          // Big Dollar Figure
          Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Text(
                dollarStr,
                style: TextStyle(
                  color: isPos ? const Color(0xFF86EFAC) : const Color(0xFFFCA5A5),
                  fontSize: 44,
                  fontWeight: FontWeight.w900,
                  letterSpacing: -1.5,
                  height: 1.0,
                ),
              ),
              const SizedBox(width: 10),
              Padding(
                padding: const EdgeInsets.only(bottom: 4),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      'Profit (USD)',
                      style: TextStyle(
                        color: Colors.white.withValues(alpha: 0.8),
                        fontSize: 13,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    const SizedBox(height: 1),
                    Text(
                      '${totalPnlPct >= 0 ? '+' : ''}${totalPnlPct.toStringAsFixed(1)}% cumulative',
                      style: TextStyle(
                        color: Colors.white.withValues(alpha: 0.65),
                        fontSize: 11,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),

          // Win Rate Indicator Bar
          ClipRRect(
            borderRadius: BorderRadius.circular(6),
            child: Stack(
              children: [
                Container(
                  height: 6,
                  width: double.infinity,
                  color: Colors.white.withValues(alpha: 0.15),
                ),
                FractionallySizedBox(
                  widthFactor: winRate.clamp(0.0, 1.0),
                  child: Container(
                    height: 6,
                    decoration: BoxDecoration(
                      color: Colors.white,
                      borderRadius: BorderRadius.circular(6),
                    ),
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),

          // 4 Stats Columns
          Row(
            children: [
              _heroStat(
                value: '${(winRate * 100).toStringAsFixed(0)}%',
                label: 'Win Rate',
                color: const Color(0xFF86EFAC),
              ),
              _heroStatDivider(),
              _heroStat(
                value: '$wins',
                label: 'Captured',
                color: const Color(0xFF86EFAC),
              ),
              _heroStatDivider(),
              _heroStat(
                value: '$losses',
                label: 'Stopped Out',
                color: const Color(0xFFFCA5A5),
              ),
              _heroStatDivider(),
              _heroStat(
                value: '${avgDrop >= 0 ? '+' : ''}${avgDrop.toStringAsFixed(1)}%',
                label: 'Avg Drop',
                color: Colors.white,
              ),
            ],
          ),
        ],
      ),
    );
  }

  // --- NEW LISTING SHORTS BREAKDOWN LIST ---
  Widget _buildShortsList(AppColors c, List<NewListingShort> shorts) {
    if (shorts.isEmpty) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 24),
          child: Text('No listing shorts recorded yet.', style: TextStyle(color: c.t3)),
        ),
      );
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'RECENT LISTING DUMPS',
          style: TextStyle(
            color: c.t3,
            fontSize: 11,
            fontWeight: FontWeight.w700,
            letterSpacing: 0.8,
          ),
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
                      Row(
                        children: [
                          Text(
                            s.symbol,
                            style: TextStyle(
                              color: c.t1,
                              fontSize: 14,
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                          const SizedBox(width: 8),
                          Container(
                            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                            decoration: BoxDecoration(
                              color: (isPending ? c.gold : isWin ? c.long : c.short).withValues(alpha: 0.12),
                              borderRadius: BorderRadius.circular(6),
                            ),
                            child: Text(
                              isPending ? 'ACTIVE' : isWin ? 'WON' : 'LOSS',
                              style: TextStyle(
                                color: isPending ? c.gold : isWin ? c.long : c.short,
                                fontSize: 10,
                                fontWeight: FontWeight.w800,
                              ),
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 3),
                      Text(
                        'Entry: \$${s.entry.toStringAsFixed(4)} · 28-33d post-listing dump',
                        style: TextStyle(color: c.t3, fontSize: 11),
                      ),
                    ],
                  ),
                ),
                const SizedBox(width: 10),
                Column(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    Text(
                      isPending ? '—' : estUsdStr,
                      style: TextStyle(
                        color: pnl >= 0 ? c.long : c.short,
                        fontSize: 15,
                        fontWeight: FontWeight.w800,
                      ),
                    ),
                    const SizedBox(height: 1),
                    Text(
                      isPending ? 'Pending' : pnlPctStr,
                      style: TextStyle(
                        color: isPending ? c.t3 : (pnl >= 0 ? c.long : c.short),
                        fontSize: 11,
                        fontWeight: FontWeight.w600,
                      ),
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

  String _formatMonth(String m) {
    if (m.length < 7) return m;
    final parts = m.split('-');
    if (parts.length >= 2) {
      const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
      final monthIdx = int.tryParse(parts[1]) ?? 0;
      if (monthIdx >= 1 && monthIdx <= 12) {
        return '${months[monthIdx - 1]} ${parts[0]}';
      }
      return '${parts[0]}-${parts[1]}';
    }
    return m;
  }
}
