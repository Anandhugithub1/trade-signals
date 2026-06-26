import 'package:flutter/material.dart';
import '../models/signal.dart';
import '../theme/app_colors.dart';
import '../widgets/signal_card.dart';
import '../widgets/disclaimer_banner.dart';
import 'signal_detail_screen.dart';

class SignalsScreen extends StatefulWidget {
  const SignalsScreen({super.key});

  @override
  State<SignalsScreen> createState() => _SignalsScreenState();
}

class _SignalsScreenState extends State<SignalsScreen> {
  String _dirFilter = 'All';   // All | Long | Short
  String _resFilter = 'All';   // All | Active | Won | Lost
  String _search = '';
  final _ctrl = TextEditingController();

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  List<TradeSignal> get _filtered {
    final q = _search.toLowerCase();
    return signalsFeed.where((s) {
      final matchSearch = q.isEmpty || s.pair.toLowerCase().contains(q);
      final matchDir = _dirFilter == 'All' ||
          (_dirFilter == 'Long' && s.direction == SignalDirection.long) ||
          (_dirFilter == 'Short' && s.direction == SignalDirection.short);
      final matchRes = _resFilter == 'All' ||
          (_resFilter == 'Active' && s.isPending) ||
          (_resFilter == 'Won' && s.isWin) ||
          (_resFilter == 'Lost' && s.isLoss);
      return matchSearch && matchDir && matchRes;
    }).toList();
  }

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final stats = signalStats;

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
                  _buildSearch(c),
                  const SizedBox(height: 12),
                  _buildDirFilters(c),
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

  Widget _buildHeader(AppColors c, SignalStats stats) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text('Signals',
            style: TextStyle(
                color: c.t1, fontSize: 26, fontWeight: FontWeight.w800, letterSpacing: -0.5)),
        // Win/Loss ratio summary
        Row(
          children: [
            _StatChip(label: '${stats.wins}W', color: c.long, bg: c.longBg),
            const SizedBox(width: 5),
            _StatChip(label: '${stats.losses}L', color: c.short, bg: c.shortBg),
            const SizedBox(width: 5),
            _StatChip(
              label: '${(stats.winRate * 100).toStringAsFixed(0)}%',
              color: stats.winRate >= 0.6 ? c.long : c.gold,
              bg: stats.winRate >= 0.6 ? c.longBg : c.goldBg,
            ),
          ],
        ),
      ],
    );
  }

  Widget _buildSearch(AppColors c) {
    return Container(
      height: 46,
      decoration: BoxDecoration(
        color: c.card,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: c.border),
      ),
      child: TextField(
        controller: _ctrl,
        onChanged: (v) => setState(() => _search = v),
        style: TextStyle(color: c.t1, fontSize: 14),
        decoration: InputDecoration(
          hintText: 'Search pair...',
          hintStyle: TextStyle(color: c.t3, fontSize: 14),
          prefixIcon: Icon(Icons.search, color: c.t3, size: 18),
          suffixIcon: _search.isNotEmpty
              ? GestureDetector(
                  onTap: () => setState(() {
                    _search = '';
                    _ctrl.clear();
                  }),
                  child: Icon(Icons.close, color: c.t3, size: 16),
                )
              : null,
          border: InputBorder.none,
          contentPadding: const EdgeInsets.symmetric(vertical: 12),
        ),
      ),
    );
  }

  // Direction filter row
  Widget _buildDirFilters(AppColors c) {
    return Row(
      children: [
        _FilterPill(
          label: 'All',
          active: _dirFilter == 'All',
          color: c.accent,
          onTap: () => setState(() => _dirFilter = 'All'),
        ),
        const SizedBox(width: 7),
        _FilterPill(
          label: 'Long',
          active: _dirFilter == 'Long',
          color: c.long,
          onTap: () => setState(() => _dirFilter = 'Long'),
        ),
        const SizedBox(width: 7),
        _FilterPill(
          label: 'Short',
          active: _dirFilter == 'Short',
          color: c.short,
          onTap: () => setState(() => _dirFilter = 'Short'),
        ),
      ],
    );
  }

  // Result filter row
  Widget _buildResFilters(AppColors c, SignalStats stats) {
    return Row(
      children: [
        _FilterPill(
          label: 'All results',
          active: _resFilter == 'All',
          color: c.accent,
          onTap: () => setState(() => _resFilter = 'All'),
        ),
        const SizedBox(width: 7),
        _FilterPill(
          label: 'Active ${stats.pending}',
          active: _resFilter == 'Active',
          color: c.accent,
          onTap: () => setState(() => _resFilter = 'Active'),
        ),
        const SizedBox(width: 7),
        _FilterPill(
          label: 'Won ${stats.wins}',
          active: _resFilter == 'Won',
          color: c.long,
          onTap: () => setState(() => _resFilter = 'Won'),
        ),
        const SizedBox(width: 7),
        _FilterPill(
          label: 'Lost ${stats.losses}',
          active: _resFilter == 'Lost',
          color: c.short,
          onTap: () => setState(() => _resFilter = 'Lost'),
        ),
      ],
    );
  }

  Widget _buildList(AppColors c) {
    if (_filtered.isEmpty) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.search_off_rounded, color: c.t3, size: 40),
            const SizedBox(height: 10),
            Text('No signals found', style: TextStyle(color: c.t2, fontSize: 15)),
            const SizedBox(height: 4),
            Text('Try a different filter', style: TextStyle(color: c.t3, fontSize: 12)),
          ],
        ),
      );
    }
    return ListView.builder(
      padding: const EdgeInsets.symmetric(horizontal: 20),
      physics: const BouncingScrollPhysics(),
      itemCount: _filtered.length,
      itemBuilder: (_, i) => SignalCard(
        signal: _filtered[i],
        onTap: () => Navigator.push(
          context,
          MaterialPageRoute(
              builder: (_) => SignalDetailScreen(signal: _filtered[i])),
        ),
      ),
    );
  }
}

class _StatChip extends StatelessWidget {
  final String label;
  final Color color;
  final Color bg;

  const _StatChip({required this.label, required this.color, required this.bg});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: color.withValues(alpha: 0.3)),
      ),
      child: Text(label,
          style: TextStyle(color: color, fontSize: 11, fontWeight: FontWeight.w700)),
    );
  }
}

class _FilterPill extends StatelessWidget {
  final String label;
  final bool active;
  final Color color;
  final VoidCallback onTap;

  const _FilterPill(
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
