import 'package:flutter/material.dart';
import '../models/stock_signal.dart';
import '../services/supabase_service.dart';
import '../theme/app_colors.dart';
import '../widgets/stock_signal_card.dart';
import '../widgets/error_view.dart';
import '../widgets/disclaimer_banner.dart';
import '../widgets/shimmer.dart';

/// "US Stocks" tab — swing signals on the top 50 US large-caps, from
/// backend/generate_stock_signals. Read-only feed off `stock_signals`.
class StocksScreen extends StatefulWidget {
  const StocksScreen({super.key});

  @override
  State<StocksScreen> createState() => _StocksScreenState();
}

class _StocksScreenState extends State<StocksScreen> {
  String _resFilter = 'All';
  List<StockSignal> _signals = [];
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
      final data = await SupabaseService.fetchStockSignals();
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

  List<StockSignal> get _filtered => _signals.where((s) {
        return _resFilter == 'All' ||
            (_resFilter == 'Active' && s.isPending) ||
            (_resFilter == 'Won' && s.isWin) ||
            (_resFilter == 'Lost' && s.isLoss);
      }).toList();

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final stats = StockStats.from(_signals);

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
                  _header(c),
                  const SizedBox(height: 12),
                  const DisclaimerBanner(
                      message: DisclaimerBanner.stocksMessage),
                  const SizedBox(height: 12),
                  _statsCard(c, stats),
                  const SizedBox(height: 12),
                  _filters(c, stats),
                ],
              ),
            ),
            const SizedBox(height: 12),
            Expanded(child: _list(c)),
          ],
        ),
      ),
    );
  }

  Widget _header(AppColors c) => Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Text('US Stocks',
                  style: TextStyle(
                      color: c.t1,
                      fontSize: 26,
                      fontWeight: FontWeight.w800,
                      letterSpacing: -0.5)),
              Text('Swing signals · top 50 stocks + gold/silver',
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
            child: Text('NYSE',
                style: TextStyle(
                    color: c.accent,
                    fontSize: 11,
                    fontWeight: FontWeight.w800,
                    letterSpacing: 0.8)),
          ),
        ],
      );

  Widget _statsCard(AppColors c, StockStats s) {
    final positive = s.netPct >= 0;
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
                Text('NET RETURN (90d, sum of trades)',
                    style: TextStyle(
                        color: c.t3,
                        fontSize: 11,
                        letterSpacing: 0.6,
                        fontWeight: FontWeight.w600)),
                const SizedBox(height: 6),
                Text(
                  '${positive ? '+' : ''}${s.netPct.toStringAsFixed(1)}%',
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
          _MiniStat(label: 'Won', value: '${s.wins}', color: c.long),
          const SizedBox(width: 14),
          _MiniStat(label: 'Lost', value: '${s.losses}', color: c.short),
          const SizedBox(width: 14),
          _MiniStat(
              label: 'Win%',
              value: '${(s.winRate * 100).toStringAsFixed(0)}%',
              color: c.accent),
        ],
      ),
    );
  }

  Widget _filters(AppColors c, StockStats s) => Row(
        children: [
          _Pill(
              label: 'All',
              active: _resFilter == 'All',
              color: c.accent,
              onTap: () => setState(() => _resFilter = 'All')),
          const SizedBox(width: 7),
          _Pill(
              label: 'Active ${s.pending}',
              active: _resFilter == 'Active',
              color: c.accent,
              onTap: () => setState(() => _resFilter = 'Active')),
          const SizedBox(width: 7),
          _Pill(
              label: 'Won ${s.wins}',
              active: _resFilter == 'Won',
              color: c.long,
              onTap: () => setState(() => _resFilter = 'Won')),
          const SizedBox(width: 7),
          _Pill(
              label: 'Lost ${s.losses}',
              active: _resFilter == 'Lost',
              color: c.short,
              onTap: () => setState(() => _resFilter = 'Lost')),
        ],
      );

  Widget _list(AppColors c) {
    if (_loading) {
      return ListView(
        padding: const EdgeInsets.symmetric(horizontal: 20),
        physics: const NeverScrollableScrollPhysics(),
        children: List.generate(
          5,
          (_) => const Padding(
            padding: EdgeInsets.only(bottom: 10),
            child: ShimmerBox(
                height: 190,
                borderRadius: BorderRadius.all(Radius.circular(12))),
          ),
        ),
      );
    }
    if (_error != null) return ErrorView(error: _error!, onRetry: _load);
    if (_filtered.isEmpty) {
      return EmptyView(
        icon: _signals.isEmpty
            ? Icons.trending_up_rounded
            : Icons.search_off_rounded,
        title: _signals.isEmpty ? 'No stock signals yet' : 'No matches',
        subtitle: _signals.isEmpty
            ? 'Signals are generated after the US close (weekdays), and only '
                'while the broad market is in an uptrend.'
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
        itemBuilder: (_, i) => StockSignalCard(signal: _filtered[i]),
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
