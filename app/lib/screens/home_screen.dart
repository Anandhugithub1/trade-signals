import 'package:flutter/material.dart';
import '../models/signal.dart';
import '../models/market_sentiment.dart';
import '../services/supabase_service.dart';
import '../theme/app_colors.dart';
import '../widgets/signal_card.dart';
import '../widgets/disclaimer_banner.dart';
import '../widgets/error_view.dart';
import '../widgets/shimmer.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  late Future<({List<TradeSignal> signals, MarketSentiment? sentiment})> _future;

  @override
  void initState() {
    super.initState();
    _future = SupabaseService.fetchAll();
  }

  void _refresh() => setState(() => _future = SupabaseService.fetchAll());

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
              return const _LoadingBody();
            }
            if (snap.hasError) {
              return ErrorView(error: snap.error!, onRetry: _refresh);
            }
            final data = snap.data!;
            final signals = data.signals;
            final sentiment = data.sentiment ?? MarketSentiment.placeholder;
            final stats = SignalStats.from(signals);
            final active = signals.where((s) => s.isPending).toList();
            final feed = signals;

            return RefreshIndicator(
              onRefresh: () async => _refresh(),
              color: c.accent,
              backgroundColor: c.card,
              child: ListView(
                padding: const EdgeInsets.symmetric(horizontal: 20),
                physics: const AlwaysScrollableScrollPhysics(
                    parent: BouncingScrollPhysics()),
                children: [
                  const SizedBox(height: 22),
                  _Header(),
                  const SizedBox(height: 14),
                  const FadeIn(child: DisclaimerBanner()),
                  const SizedBox(height: 14),
                  FadeIn(delayMs: 60, child: _HeroPerformanceCard(stats: stats)),
                  const SizedBox(height: 14),
                  FadeIn(delayMs: 120, child: _SentimentCard(sentiment: sentiment)),
                  const SizedBox(height: 16),
                  if (feed.isNotEmpty)
                    FadeIn(delayMs: 180, child: _FeaturedCard(signal: feed.first)),
                  const SizedBox(height: 24),
                  _SectionHeader(
                    title: 'Recent Signals',
                    tag: '${active.length} active',
                  ),
                  const SizedBox(height: 10),
                  if (feed.isEmpty)
                    const _EmptyFeed()
                  else ...[
                    ...feed.take(4).toList().asMap().entries.map((e) => FadeIn(
                          delayMs: 220 + e.key * 60,
                          child: SignalCard(signal: e.value, compact: true),
                        )),
                    const SizedBox(height: 12),
                    _ViewAllBtn(),
                  ],
                  const SizedBox(height: 28),
                ],
              ),
            );
          },
        ),
      ),
    );
  }
}

class _LoadingBody extends StatelessWidget {
  const _LoadingBody();

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.symmetric(horizontal: 20),
      physics: const NeverScrollableScrollPhysics(),
      children: [
        const SizedBox(height: 22),
        _Header(),
        const SizedBox(height: 24),
        ...[180.0, 130.0, 170.0, 72.0, 72.0, 72.0].map((h) => Padding(
              padding: const EdgeInsets.only(bottom: 14),
              child: ShimmerBox(height: h),
            )),
      ],
    );
  }
}

class _EmptyFeed extends StatelessWidget {
  const _EmptyFeed();

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return FadeIn(
      delayMs: 220,
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.symmetric(vertical: 36, horizontal: 24),
        decoration: BoxDecoration(
          color: c.card,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: c.border),
        ),
        child: Column(
          children: [
            Container(
              width: 56,
              height: 56,
              decoration: BoxDecoration(
                color: c.accentBg,
                shape: BoxShape.circle,
              ),
              child: Icon(Icons.radar_rounded, color: c.accent, size: 26),
            ),
            const SizedBox(height: 14),
            Text('Scanning the market',
                style: TextStyle(
                    color: c.t1, fontSize: 15, fontWeight: FontWeight.w700)),
            const SizedBox(height: 6),
            Text(
              'No signals right now. The algorithm only trades\nconfirmed trends — new signals land every 4 hours.',
              textAlign: TextAlign.center,
              style: TextStyle(color: c.t2, fontSize: 12, height: 1.5),
            ),
          ],
        ),
      ),
    );
  }
}


class _Header extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final hour = DateTime.now().hour;
    final greeting = hour < 12
        ? 'Good morning'
        : hour < 17
            ? 'Good afternoon'
            : 'Good evening';

    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                ClipRRect(
                  borderRadius: BorderRadius.circular(8),
                  child: Image.asset(
                    'assets/images/logo.png',
                    width: 28,
                    height: 28,
                    fit: BoxFit.cover,
                  ),
                ),
                const SizedBox(width: 8),
                Text(
                  'Zenviq',
                  style: TextStyle(
                    color: c.t1,
                    fontSize: 22,
                    fontWeight: FontWeight.w900,
                    letterSpacing: -0.6,
                  ),
                ),
                const SizedBox(width: 8),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
                  decoration: BoxDecoration(
                    color: c.longBg,
                    borderRadius: BorderRadius.circular(5),
                    border: Border.all(color: c.long.withValues(alpha: 0.4)),
                  ),
                  child: Text(
                    'FREE',
                    style: TextStyle(
                      color: c.long,
                      fontSize: 9,
                      fontWeight: FontWeight.w800,
                      letterSpacing: 1.2,
                    ),
                  ),
                ),
                const SizedBox(width: 5),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
                  decoration: BoxDecoration(
                    color: c.accentBg,
                    borderRadius: BorderRadius.circular(5),
                    border: Border.all(color: c.accent.withValues(alpha: 0.4)),
                  ),
                  child: Text(
                    'FUTURES',
                    style: TextStyle(
                      color: c.accent,
                      fontSize: 9,
                      fontWeight: FontWeight.w800,
                      letterSpacing: 1.0,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 4),
            Text(
              '$greeting · Perpetual Futures Signals',
              style: TextStyle(color: c.t2, fontSize: 13, fontWeight: FontWeight.w500),
            ),
          ],
        ),
        Container(
          width: 40,
          height: 40,
          decoration: BoxDecoration(
            color: c.accentBg,
            shape: BoxShape.circle,
            border: Border.all(color: c.accent.withValues(alpha: 0.3)),
          ),
          child: Icon(Icons.notifications_none_rounded, color: c.accent, size: 20),
        ),
      ],
    );
  }
}

// Gradient hero performance card
class _HeroPerformanceCard extends StatelessWidget {
  final SignalStats stats;

  const _HeroPerformanceCard({required this.stats});

  @override
  Widget build(BuildContext context) {
    final winPct = stats.winRate;
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(22, 20, 22, 20),
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [Color(0xFF1E3A8A), Color(0xFF1D4ED8), Color(0xFF2563EB)],
          stops: [0.0, 0.5, 1.0],
        ),
        borderRadius: BorderRadius.circular(20),
        boxShadow: [
          BoxShadow(
            color: const Color(0xFF2563EB).withValues(alpha: 0.4),
            blurRadius: 28,
            offset: const Offset(0, 12),
          ),
        ],
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Card header
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                'PERFORMANCE',
                style: TextStyle(
                  color: Colors.white.withValues(alpha: 0.6),
                  fontSize: 11,
                  fontWeight: FontWeight.w700,
                  letterSpacing: 1.0,
                ),
              ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                decoration: BoxDecoration(
                  color: Colors.white.withValues(alpha: 0.14),
                  borderRadius: BorderRadius.circular(20),
                ),
                child: Text(
                  '90 Days',
                  style: TextStyle(
                    color: Colors.white.withValues(alpha: 0.9),
                    fontSize: 11,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),

          // Big win rate
          Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Text(
                '${(winPct * 100).toStringAsFixed(0)}%',
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 52,
                  fontWeight: FontWeight.w900,
                  letterSpacing: -2,
                  height: 1.0,
                ),
              ),
              const SizedBox(width: 10),
              Padding(
                padding: const EdgeInsets.only(bottom: 6),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Win Rate',
                      style: TextStyle(
                        color: Colors.white.withValues(alpha: 0.7),
                        fontSize: 14,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Row(
                      children: [
                        Icon(
                          winPct >= 0.6 ? Icons.trending_up_rounded : Icons.trending_down_rounded,
                          color: Colors.white.withValues(alpha: 0.6),
                          size: 14,
                        ),
                        const SizedBox(width: 3),
                        Text(
                          winPct >= 0.6 ? 'Strong' : winPct >= 0.45 ? 'Moderate' : 'Weak',
                          style: TextStyle(
                            color: Colors.white.withValues(alpha: 0.55),
                            fontSize: 12,
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 18),

          // Win/Loss progress bar
          ClipRRect(
            borderRadius: BorderRadius.circular(6),
            child: Stack(
              children: [
                Container(
                  height: 7,
                  color: Colors.white.withValues(alpha: 0.15),
                ),
                FractionallySizedBox(
                  widthFactor: winPct.clamp(0.0, 1.0),
                  child: Container(
                    height: 7,
                    decoration: BoxDecoration(
                      color: Colors.white,
                      borderRadius: BorderRadius.circular(6),
                    ),
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 20),

          // Stats row
          Row(
            children: [
              _HeroStat(value: '${stats.wins}', label: 'Won', color: const Color(0xFF86EFAC)),
              _HeroStatDivider(),
              _HeroStat(value: '${stats.losses}', label: 'Lost', color: const Color(0xFFFCA5A5)),
              _HeroStatDivider(),
              _HeroStat(value: '${stats.pending}', label: 'Active', color: const Color(0xFF93C5FD)),
              _HeroStatDivider(),
              _HeroStat(value: '${stats.total}', label: 'Total', color: Colors.white),
            ],
          ),
        ],
      ),
    );
  }
}

class _HeroStat extends StatelessWidget {
  final String value;
  final String label;
  final Color color;

  const _HeroStat({required this.value, required this.label, required this.color});

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            value,
            style: TextStyle(color: color, fontSize: 20, fontWeight: FontWeight.w800, letterSpacing: -0.5),
          ),
          const SizedBox(height: 2),
          Text(
            label,
            style: TextStyle(color: Colors.white.withValues(alpha: 0.5), fontSize: 11),
          ),
        ],
      ),
    );
  }
}

class _HeroStatDivider extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Container(
      width: 1,
      height: 32,
      color: Colors.white.withValues(alpha: 0.15),
      margin: const EdgeInsets.symmetric(horizontal: 4),
    );
  }
}

class _SentimentCard extends StatelessWidget {
  final MarketSentiment sentiment;

  const _SentimentCard({required this.sentiment});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final isPlaceholder = sentiment.id == 'placeholder';
    final dominantColor = sentiment.dominant == 'bullish'
        ? c.long
        : sentiment.dominant == 'bearish'
            ? c.short
            : c.gold;

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: c.card,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: c.border),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                'MARKET SENTIMENT',
                style: TextStyle(
                  color: c.t3,
                  fontSize: 11,
                  letterSpacing: 0.8,
                  fontWeight: FontWeight.w600,
                ),
              ),
              Row(
                children: [
                  if (!isPlaceholder && sentiment.fearGreedValue != null) ...[
                    Text(
                      'F&G ${sentiment.fearGreedValue}',
                      style: TextStyle(color: c.t2, fontSize: 11),
                    ),
                    const SizedBox(width: 8),
                  ],
                  Container(
                    width: 8,
                    height: 8,
                    decoration: BoxDecoration(color: dominantColor, shape: BoxShape.circle),
                  ),
                ],
              ),
            ],
          ),
          const SizedBox(height: 14),
          Row(
            children: [
              _SentPill(label: 'Bullish', pct: sentiment.bullishPct, color: c.long,
                  active: sentiment.dominant == 'bullish'),
              const SizedBox(width: 8),
              _SentPill(label: 'Neutral', pct: sentiment.neutralPct, color: c.gold,
                  active: sentiment.dominant == 'neutral'),
              const SizedBox(width: 8),
              _SentPill(label: 'Bearish', pct: sentiment.bearishPct, color: c.short,
                  active: sentiment.dominant == 'bearish'),
            ],
          ),
          const SizedBox(height: 14),
          ClipRRect(
            borderRadius: BorderRadius.circular(4),
            child: Row(
              children: [
                Flexible(flex: sentiment.bullishPct.clamp(1, 100),
                    child: Container(height: 6, color: c.long)),
                Flexible(flex: sentiment.neutralPct.clamp(1, 100),
                    child: Container(height: 6, color: c.gold)),
                Flexible(flex: sentiment.bearishPct.clamp(1, 100),
                    child: Container(height: 6, color: c.short)),
              ],
            ),
          ),
          const SizedBox(height: 10),
          Text(
            isPlaceholder
                ? 'Run generate_signals to update sentiment'
                : '${sentiment.activeLongs} active longs  ·  ${sentiment.activeShorts} shorts',
            style: TextStyle(color: c.t2, fontSize: 12),
          ),
        ],
      ),
    );
  }
}

class _SentPill extends StatelessWidget {
  final String label;
  final int pct;
  final Color color;
  final bool active;

  const _SentPill({required this.label, required this.pct, required this.color, required this.active});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return Expanded(
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 10),
        decoration: BoxDecoration(
          color: active ? color.withValues(alpha: 0.1) : c.surface,
          borderRadius: BorderRadius.circular(10),
          border: Border.all(color: active ? color.withValues(alpha: 0.4) : c.border),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              '$pct%',
              style: TextStyle(
                color: active ? color : c.t2,
                fontSize: 16,
                fontWeight: FontWeight.w800,
              ),
            ),
            const SizedBox(height: 2),
            Text(
              label,
              style: TextStyle(
                color: active ? color.withValues(alpha: 0.7) : c.t3,
                fontSize: 11,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _FeaturedCard extends StatelessWidget {
  final TradeSignal signal;

  const _FeaturedCard({required this.signal});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final isLong = signal.direction == SignalDirection.long;
    final color = isLong ? c.long : c.short;
    final label = isLong ? 'LONG' : 'SHORT';

    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: c.card,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: c.border),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                'FEATURED SIGNAL',
                style: TextStyle(
                  color: c.t3,
                  fontSize: 11,
                  letterSpacing: 0.8,
                  fontWeight: FontWeight.w600,
                ),
              ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                decoration: BoxDecoration(
                  color: color.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(7),
                  border: Border.all(color: color.withValues(alpha: 0.3)),
                ),
                child: Text(
                  label,
                  style: TextStyle(
                    color: color,
                    fontSize: 11,
                    fontWeight: FontWeight.w800,
                    letterSpacing: 0.8,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 14),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                signal.pair,
                style: TextStyle(
                  color: c.t1,
                  fontSize: 26,
                  fontWeight: FontWeight.w900,
                  letterSpacing: -0.8,
                ),
              ),
              Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Text(
                    '${signal.confidence}%',
                    style: TextStyle(
                      color: color,
                      fontSize: 26,
                      fontWeight: FontWeight.w900,
                      letterSpacing: -0.5,
                    ),
                  ),
                  Text('strength', style: TextStyle(color: c.t3, fontSize: 11)),
                ],
              ),
            ],
          ),
          const SizedBox(height: 14),
          Row(
            children: [
              _InfoTile(label: 'ENTRY', value: '\$${signal.entry.toStringAsFixed(2)}', valueColor: c.t1),
              const SizedBox(width: 8),
              _InfoTile(label: 'STOP LOSS', value: '\$${signal.stopLoss.toStringAsFixed(2)}', valueColor: c.short),
              const SizedBox(width: 8),
              _InfoTile(label: 'TARGET', value: '\$${signal.takeProfit.toStringAsFixed(2)}', valueColor: c.long),
            ],
          ),
        ],
      ),
    );
  }
}

class _InfoTile extends StatelessWidget {
  final String label;
  final String value;
  final Color valueColor;

  const _InfoTile({required this.label, required this.value, required this.valueColor});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return Expanded(
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 9),
        decoration: BoxDecoration(
          color: c.surface,
          borderRadius: BorderRadius.circular(9),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              label,
              style: TextStyle(
                color: c.t3,
                fontSize: 10,
                letterSpacing: 0.5,
                fontWeight: FontWeight.w600,
              ),
            ),
            const SizedBox(height: 3),
            Text(
              value,
              style: TextStyle(color: valueColor, fontSize: 13, fontWeight: FontWeight.w700),
            ),
          ],
        ),
      ),
    );
  }
}

class _SectionHeader extends StatelessWidget {
  final String title;
  final String tag;

  const _SectionHeader({required this.title, required this.tag});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text(
          title,
          style: TextStyle(color: c.t1, fontSize: 17, fontWeight: FontWeight.w700),
        ),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
          decoration: BoxDecoration(
            color: c.accentBg,
            borderRadius: BorderRadius.circular(20),
            border: Border.all(color: c.accent.withValues(alpha: 0.25)),
          ),
          child: Text(
            tag,
            style: TextStyle(color: c.accent, fontSize: 11, fontWeight: FontWeight.w600),
          ),
        ),
      ],
    );
  }
}

class _ViewAllBtn extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return SizedBox(
      width: double.infinity,
      child: ElevatedButton(
        onPressed: () {},
        style: ElevatedButton.styleFrom(
          backgroundColor: c.accent,
          foregroundColor: Colors.white,
          padding: const EdgeInsets.symmetric(vertical: 15),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
          elevation: 0,
        ),
        child: const Text(
          'View All Signals',
          style: TextStyle(fontSize: 15, fontWeight: FontWeight.w700),
        ),
      ),
    );
  }
}
