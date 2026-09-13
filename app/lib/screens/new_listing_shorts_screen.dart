import 'package:flutter/material.dart';
import '../models/new_listing_short.dart';
import '../services/supabase_service.dart';
import '../theme/app_colors.dart';
import '../widgets/new_listing_short_card.dart';
import '../widgets/error_view.dart';
import '../widgets/disclaimer_banner.dart';
import '../widgets/shimmer.dart';

/// "Short New Listings" tab — replaces the old US Stock Signals tab.
/// Short-only signals on newly-listed Binance perps (27-33 days old),
/// with a defined stop-loss and an early profit-lock exit. Read-only feed
/// from the `new_listing_shorts` Supabase table.
class NewListingShortsScreen extends StatefulWidget {
  const NewListingShortsScreen({super.key});

  @override
  State<NewListingShortsScreen> createState() => _NewListingShortsScreenState();
}

class _NewListingShortsScreenState extends State<NewListingShortsScreen> {
  String _resFilter = 'All';
  List<NewListingShort> _signals = [];
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
      final data = await SupabaseService.fetchNewListingShorts();
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

  List<NewListingShort> get _filtered {
    return _signals.where((s) {
      return _resFilter == 'All' ||
          (_resFilter == 'Active' && s.isPending) ||
          (_resFilter == 'Won' && s.isWin) ||
          (_resFilter == 'Lost' && s.isLoss);
    }).toList();
  }

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final stats = ShortStats.from(_signals);

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
                  _buildHeader(c),
                  const SizedBox(height: 12),
                  const DisclaimerBanner(
                    message: 'Short-only signals with no proven edge over just '
                        'shorting the broader altcoin market — see the note below. '
                        'Never risk more than 2-3% of capital per trade.',
                  ),
                  const SizedBox(height: 12),
                  _buildStatsCard(c, stats),
                  const SizedBox(height: 12),
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

  Widget _buildHeader(AppColors c) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            Text('New Listing Shorts',
                style: TextStyle(color: c.t1, fontSize: 26, fontWeight: FontWeight.w800, letterSpacing: -0.5)),
            Text('Short coins 27-33 days after listing',
                style: TextStyle(color: c.t2, fontSize: 12)),
          ],
        ),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 5),
          decoration: BoxDecoration(
            color: c.shortBg,
            borderRadius: BorderRadius.circular(7),
            border: Border.all(color: c.short.withValues(alpha: 0.35)),
          ),
          child: Text('SHORT ONLY',
              style: TextStyle(color: c.short, fontSize: 11, fontWeight: FontWeight.w800, letterSpacing: 0.6)),
        ),
      ],
    );
  }

  Widget _buildStatsCard(AppColors c, ShortStats stats) {
    final positive = stats.avgPnlPct >= 0;
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
                Text('AVG P&L / CLOSED TRADE',
                    style: TextStyle(color: c.t3, fontSize: 11, letterSpacing: 0.6, fontWeight: FontWeight.w600)),
                const SizedBox(height: 6),
                Text(
                  stats.closed == 0
                      ? '—'
                      : '${positive ? '+' : ''}${stats.avgPnlPct.toStringAsFixed(1)}%',
                  style: TextStyle(
                    color: stats.closed == 0 ? c.t2 : (positive ? c.long : c.short),
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
              value: stats.closed == 0 ? '—' : '${(stats.winRate * 100).toStringAsFixed(0)}%',
              color: c.accent),
        ],
      ),
    );
  }

  Widget _buildResFilters(AppColors c, ShortStats stats) {
    return Row(
      children: [
        _Pill(label: 'All', active: _resFilter == 'All', color: c.accent,
            onTap: () => setState(() => _resFilter = 'All')),
        const SizedBox(width: 7),
        _Pill(label: 'Active ${stats.pending}', active: _resFilter == 'Active', color: c.accent,
            onTap: () => setState(() => _resFilter = 'Active')),
        const SizedBox(width: 7),
        _Pill(label: 'Won ${stats.wins}', active: _resFilter == 'Won', color: c.long,
            onTap: () => setState(() => _resFilter = 'Won')),
        const SizedBox(width: 7),
        _Pill(label: 'Lost ${stats.losses}', active: _resFilter == 'Lost', color: c.short,
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
            child: ShimmerBox(height: 130, borderRadius: BorderRadius.all(Radius.circular(12))),
          ),
        ),
      );
    }
    if (_error != null) {
      return ErrorView(error: _error!, onRetry: _load);
    }
    if (_filtered.isEmpty) {
      return EmptyView(
        icon: _signals.isEmpty ? Icons.trending_down_rounded : Icons.search_off_rounded,
        title: _signals.isEmpty ? 'No signals yet' : 'No matches',
        subtitle: _signals.isEmpty
            ? 'Signals appear here when a Binance perp turns 27-33 days old.'
            : 'Try adjusting your filters.',
      );
    }
    return RefreshIndicator(
      onRefresh: _load,
      color: c.accent,
      backgroundColor: c.card,
      child: ListView.builder(
        padding: const EdgeInsets.symmetric(horizontal: 20),
        physics: const AlwaysScrollableScrollPhysics(parent: BouncingScrollPhysics()),
        itemCount: _filtered.length,
        itemBuilder: (_, i) => NewListingShortCard(signal: _filtered[i]),
      ),
    );
  }
}

class _MiniStat extends StatelessWidget {
  final String label;
  final String value;
  final Color color;

  const _MiniStat({required this.label, required this.value, required this.color});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(value, style: TextStyle(color: color, fontSize: 16, fontWeight: FontWeight.w800)),
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

  const _Pill({required this.label, required this.active, required this.color, required this.onTap});

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
          border: Border.all(color: active ? color.withValues(alpha: 0.5) : c.border),
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
