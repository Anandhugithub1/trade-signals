import 'package:flutter/material.dart';
import '../models/nifty_option_signal.dart';
import '../services/supabase_service.dart';
import '../theme/app_colors.dart';
import '../widgets/nifty_option_card.dart';
import '../widgets/error_view.dart';
import '../widgets/disclaimer_banner.dart';
import '../widgets/shimmer.dart';

/// "NIFTY Options Trading" section — intraday CE/PE signals from the options
/// algo. Read-only feed from the `nifty_option_signals` Supabase table.
class NiftyOptionsScreen extends StatefulWidget {
  const NiftyOptionsScreen({super.key});

  @override
  State<NiftyOptionsScreen> createState() => _NiftyOptionsScreenState();
}

class _NiftyOptionsScreenState extends State<NiftyOptionsScreen> {
  String _sideFilter = 'All';
  String _resFilter = 'All';
  List<NiftyOptionSignal> _signals = [];
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final data = await SupabaseService.fetchNiftyOptionSignals();
      if (mounted) {
        setState(() {
          _signals = data;
          _loading = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _error = e.toString();
          _loading = false;
        });
      }
    }
  }

  List<NiftyOptionSignal> get _filtered {
    return _signals.where((s) {
      final matchSide = _sideFilter == 'All' ||
          (_sideFilter == 'CE' && s.side == OptionSide.ce) ||
          (_sideFilter == 'PE' && s.side == OptionSide.pe);
      final matchRes = _resFilter == 'All' ||
          (_resFilter == 'Active' && s.isPending) ||
          (_resFilter == 'Won' && s.isWin) ||
          (_resFilter == 'Lost' && s.isLoss);
      return matchSide && matchRes;
    }).toList();
  }

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final stats = OptionStats.from(_signals);

    return Scaffold(
      backgroundColor: c.bg,
      body: SafeArea(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 20, 20, 0),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _buildHeader(c, stats),
                  const SizedBox(height: 12),
                  const DisclaimerBanner(),
                  const SizedBox(height: 12),
                  _buildPnlCard(c, stats),
                  const SizedBox(height: 12),
                  _buildSideFilters(c),
                  const SizedBox(height: 8),
                  _buildResFilters(c, stats),
                ],
              ),
            ),
            const SizedBox(height: 12),
            Expanded(child: _buildList(c)),
          ],
        ),
      ),
    );
  }

  Widget _buildHeader(AppColors c, OptionStats stats) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            Text('NIFTY Options',
                style: TextStyle(
                    color: c.t1,
                    fontSize: 26,
                    fontWeight: FontWeight.w800,
                    letterSpacing: -0.5)),
            Text('Intraday CE / PE signals',
                style: TextStyle(color: c.t2, fontSize: 12)),
          ],
        ),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 5),
          decoration: BoxDecoration(
            color: c.accentBg,
            borderRadius: BorderRadius.circular(7),
            border: Border.all(color: c.accent.withValues(alpha: 0.35)),
          ),
          child: Text('NSE',
              style: TextStyle(
                  color: c.accent,
                  fontSize: 11,
                  fontWeight: FontWeight.w800,
                  letterSpacing: 0.8)),
        ),
      ],
    );
  }

  // Net rupee P&L hero card (the metric that matters for options).
  Widget _buildPnlCard(AppColors c, OptionStats stats) {
    final positive = stats.netPnlRs >= 0;
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: c.card,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: c.border),
      ),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text('NET P&L (90d, per lot)',
                    style: TextStyle(
                        color: c.t3,
                        fontSize: 11,
                        letterSpacing: 0.6,
                        fontWeight: FontWeight.w600)),
                const SizedBox(height: 6),
                Text(
                  '${positive ? '+' : ''}₹${stats.netPnlRs.toStringAsFixed(0)}',
                  style: TextStyle(
                    color: positive ? c.long : c.short,
                    fontSize: 28,
                    fontWeight: FontWeight.w900,
                    letterSpacing: -0.8,
                  ),
                ),
              ],
            ),
          ),
          _MiniStat(label: 'Won', value: '${stats.wins}', color: c.long),
          const SizedBox(width: 14),
          _MiniStat(label: 'Lost', value: '${stats.losses}', color: c.short),
          const SizedBox(width: 14),
          _MiniStat(
              label: 'Win%',
              value: '${(stats.winRate * 100).toStringAsFixed(0)}%',
              color: c.accent),
        ],
      ),
    );
  }

  Widget _buildSideFilters(AppColors c) {
    return Row(
      children: [
        _Pill(
            label: 'All',
            active: _sideFilter == 'All',
            color: c.accent,
            onTap: () => setState(() => _sideFilter = 'All')),
        const SizedBox(width: 7),
        _Pill(
            label: 'CE (Bullish)',
            active: _sideFilter == 'CE',
            color: c.long,
            onTap: () => setState(() => _sideFilter = 'CE')),
        const SizedBox(width: 7),
        _Pill(
            label: 'PE (Bearish)',
            active: _sideFilter == 'PE',
            color: c.short,
            onTap: () => setState(() => _sideFilter = 'PE')),
      ],
    );
  }

  Widget _buildResFilters(AppColors c, OptionStats stats) {
    return Row(
      children: [
        _Pill(
            label: 'All',
            active: _resFilter == 'All',
            color: c.accent,
            onTap: () => setState(() => _resFilter = 'All')),
        const SizedBox(width: 7),
        _Pill(
            label: 'Active ${stats.pending}',
            active: _resFilter == 'Active',
            color: c.accent,
            onTap: () => setState(() => _resFilter = 'Active')),
        const SizedBox(width: 7),
        _Pill(
            label: 'Won ${stats.wins}',
            active: _resFilter == 'Won',
            color: c.long,
            onTap: () => setState(() => _resFilter = 'Won')),
        const SizedBox(width: 7),
        _Pill(
            label: 'Lost ${stats.losses}',
            active: _resFilter == 'Lost',
            color: c.short,
            onTap: () => setState(() => _resFilter = 'Lost')),
      ],
    );
  }

  Widget _buildList(AppColors c) {
    if (_loading) {
      return ListView(
        padding: const EdgeInsets.symmetric(horizontal: 20),
        physics: const NeverScrollableScrollPhysics(),
        children: List.generate(
          6,
          (_) => const Padding(
            padding: EdgeInsets.only(bottom: 10),
            child: ShimmerBox(
                height: 130,
                borderRadius: BorderRadius.all(Radius.circular(12))),
          ),
        ),
      );
    }
    if (_error != null) {
      return ErrorView(error: _error!, onRetry: _load);
    }
    if (_filtered.isEmpty) {
      return EmptyView(
        icon: _signals.isEmpty
            ? Icons.candlestick_chart_outlined
            : Icons.search_off_rounded,
        title: _signals.isEmpty ? 'No option signals yet' : 'No matches',
        subtitle: _signals.isEmpty
            ? 'CE/PE signals appear here during market hours (9:15–15:30 IST).'
            : 'Try adjusting your filters.',
      );
    }
    return RefreshIndicator(
      onRefresh: _load,
      color: c.accent,
      backgroundColor: c.card,
      child: ListView.builder(
        padding: const EdgeInsets.symmetric(horizontal: 20),
        physics: const AlwaysScrollableScrollPhysics(
            parent: BouncingScrollPhysics()),
        itemCount: _filtered.length,
        itemBuilder: (_, i) => NiftyOptionCard(signal: _filtered[i]),
      ),
    );
  }
}

class _MiniStat extends StatelessWidget {
  final String label;
  final String value;
  final Color color;

  const _MiniStat(
      {required this.label, required this.value, required this.color});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(value,
            style: TextStyle(
                color: color, fontSize: 16, fontWeight: FontWeight.w800)),
        const SizedBox(height: 2),
        Text(label, style: TextStyle(color: c.t3, fontSize: 10)),
      ],
    );
  }
}

class _Pill extends StatelessWidget {
  final String label;
  final bool active;
  final Color color;
  final VoidCallback onTap;

  const _Pill(
      {required this.label,
      required this.active,
      required this.color,
      required this.onTap});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
        decoration: BoxDecoration(
          color: active ? color.withValues(alpha: 0.12) : c.card,
          borderRadius: BorderRadius.circular(8),
          border: Border.all(
              color: active ? color.withValues(alpha: 0.5) : c.border),
        ),
        child: Text(label,
            style: TextStyle(
                color: active ? color : c.t2,
                fontSize: 12,
                fontWeight: active ? FontWeight.w700 : FontWeight.w500)),
      ),
    );
  }
}
