import 'package:flutter/material.dart';
import '../models/signal.dart';
import '../theme/app_colors.dart';

class ProfileScreen extends StatelessWidget {
  const ProfileScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return Scaffold(
      backgroundColor: c.bg,
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.symmetric(horizontal: 20),
          physics: const BouncingScrollPhysics(),
          children: const [
            SizedBox(height: 20),
            _TopBar(),
            SizedBox(height: 28),
            _Avatar(),
            SizedBox(height: 24),
            _SubscriptionCard(),
            SizedBox(height: 16),
            _StatsCard(),
            SizedBox(height: 16),
            _MenuCard(),
            SizedBox(height: 28),
          ],
        ),
      ),
    );
  }
}

class _TopBar extends StatelessWidget {
  const _TopBar();

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text('Profile',
            style: TextStyle(
                color: c.t1,
                fontSize: 26,
                fontWeight: FontWeight.w800,
                letterSpacing: -0.5)),
        Icon(Icons.settings_outlined, color: c.t2, size: 22),
      ],
    );
  }
}

class _Avatar extends StatelessWidget {
  const _Avatar();

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return Column(
      children: [
        Container(
          width: 72,
          height: 72,
          decoration: BoxDecoration(
            color: c.accentBg,
            shape: BoxShape.circle,
            border: Border.all(color: c.accent.withValues(alpha: 0.4), width: 2),
          ),
          child: Center(
            child: Text('A',
                style: TextStyle(
                    color: c.accent, fontSize: 28, fontWeight: FontWeight.w800)),
          ),
        ),
        const SizedBox(height: 12),
        Text('Alex Johnson',
            style: TextStyle(
                color: c.t1, fontSize: 20, fontWeight: FontWeight.w700)),
        const SizedBox(height: 3),
        Text('alex.johnson@email.com',
            style: TextStyle(color: c.t2, fontSize: 13)),
      ],
    );
  }
}

class _SubscriptionCard extends StatelessWidget {
  const _SubscriptionCard();

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: c.card,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: c.gold.withValues(alpha: 0.35)),
      ),
      child: Row(
        children: [
          Container(
            width: 44,
            height: 44,
            decoration: BoxDecoration(
              color: c.goldBg,
              borderRadius: BorderRadius.circular(11),
              border: Border.all(color: c.gold.withValues(alpha: 0.3)),
            ),
            child: Icon(Icons.workspace_premium_rounded, color: c.gold, size: 22),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Text('Pro Plan',
                        style: TextStyle(
                            color: c.t1,
                            fontSize: 15,
                            fontWeight: FontWeight.w700)),
                    const SizedBox(width: 8),
                    Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 6, vertical: 2),
                      decoration: BoxDecoration(
                          color: c.longBg,
                          borderRadius: BorderRadius.circular(4)),
                      child: Text('ACTIVE',
                          style: TextStyle(
                              color: c.long,
                              fontSize: 9,
                              fontWeight: FontWeight.w800,
                              letterSpacing: 0.8)),
                    ),
                  ],
                ),
                const SizedBox(height: 2),
                Text('Renews Jul 24, 2026 · \$29/mo',
                    style: TextStyle(color: c.t2, fontSize: 12)),
                const SizedBox(height: 8),
                ClipRRect(
                  borderRadius: BorderRadius.circular(3),
                  child: LinearProgressIndicator(
                    value: 0.73,
                    backgroundColor: c.border,
                    valueColor: AlwaysStoppedAnimation<Color>(c.gold),
                    minHeight: 3,
                  ),
                ),
                const SizedBox(height: 3),
                Text('22 days remaining',
                    style: TextStyle(color: c.t3, fontSize: 10)),
              ],
            ),
          ),
          const SizedBox(width: 8),
          Icon(Icons.chevron_right_rounded, color: c.t3, size: 18),
        ],
      ),
    );
  }
}

// Stats derived from real signal data
class _StatsCard extends StatelessWidget {
  const _StatsCard();

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final stats = signalStats;

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: c.card,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: c.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text('90-Day Statistics',
                  style: TextStyle(
                      color: c.t1, fontSize: 15, fontWeight: FontWeight.w700)),
              Text('Last 3 months',
                  style: TextStyle(color: c.t3, fontSize: 11)),
            ],
          ),
          const SizedBox(height: 16),
          Row(
            children: [
              _StatItem(
                  value: '${stats.total}',
                  label: 'Total\nSignals',
                  color: c.accent),
              _VDivider(),
              _StatItem(
                  value: '${stats.wins}',
                  label: 'Signals\nWon',
                  color: c.long),
              _VDivider(),
              _StatItem(
                  value: '${stats.losses}',
                  label: 'Signals\nLost',
                  color: c.short),
              _VDivider(),
              _StatItem(
                  value: '${(stats.winRate * 100).toStringAsFixed(0)}%',
                  label: 'Win\nRate',
                  color: stats.winRate >= 0.6 ? c.long : c.gold),
            ],
          ),
          const SizedBox(height: 14),
          // Win/loss bar
          ClipRRect(
            borderRadius: BorderRadius.circular(4),
            child: SizedBox(
              height: 5,
              child: Row(
                children: [
                  if (stats.wins > 0)
                    Flexible(flex: stats.wins, child: Container(color: c.long)),
                  if (stats.wins > 0 && stats.losses > 0)
                    const SizedBox(width: 2),
                  if (stats.losses > 0)
                    Flexible(
                        flex: stats.losses, child: Container(color: c.short)),
                ],
              ),
            ),
          ),
          const SizedBox(height: 6),
          Text('Based on ${stats.closed} closed signals',
              style: TextStyle(color: c.t3, fontSize: 11)),
        ],
      ),
    );
  }
}

class _StatItem extends StatelessWidget {
  final String value;
  final String label;
  final Color color;

  const _StatItem(
      {required this.value, required this.label, required this.color});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return Expanded(
      child: Column(
        children: [
          Text(value,
              style: TextStyle(
                  color: color,
                  fontSize: 20,
                  fontWeight: FontWeight.w800,
                  letterSpacing: -0.3)),
          const SizedBox(height: 3),
          Text(label,
              textAlign: TextAlign.center,
              style: TextStyle(color: c.t3, fontSize: 10, height: 1.3)),
        ],
      ),
    );
  }
}

class _VDivider extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return Container(
        width: 1,
        height: 44,
        color: c.border,
        margin: const EdgeInsets.symmetric(horizontal: 6));
  }
}

class _MenuCard extends StatelessWidget {
  const _MenuCard();

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final items = [
      (Icons.notifications_outlined, 'Notifications', 'Alerts & push settings', c.accent, null),
      (Icons.workspace_premium_outlined, 'Subscription', 'Pro · Renews Jul 2026', c.gold, null),
      (Icons.warning_amber_rounded, 'Risk Disclaimer', 'Read before trading', const Color(0xFFF59E0B), '/disclaimer/info'),
      (Icons.help_outline_rounded, 'Help & Support', 'FAQs, live chat', c.long, null),
      (Icons.info_outline_rounded, 'About', 'Version 1.0.0', c.t2, null),
    ];

    return Container(
      decoration: BoxDecoration(
        color: c.card,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: c.border),
      ),
      child: Column(
        children: items.asMap().entries.map((e) {
          final (icon, label, sub, color, route) = e.value;
          final isLast = e.key == items.length - 1;
          return Column(
            children: [
              _MenuRow(
                icon: icon,
                label: label,
                sub: sub,
                color: color,
                onTap: route != null
                    ? () => Navigator.of(context).pushNamed(route)
                    : null,
              ),
              if (!isLast) Divider(height: 1, color: c.border, indent: 58),
            ],
          );
        }).toList(),
      ),
    );
  }
}

class _MenuRow extends StatelessWidget {
  final IconData icon;
  final String label;
  final String sub;
  final Color color;
  final VoidCallback? onTap;

  const _MenuRow({
    required this.icon,
    required this.label,
    required this.sub,
    required this.color,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(14),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 13),
        child: Row(
          children: [
            Container(
              width: 38,
              height: 38,
              decoration: BoxDecoration(
                color: color.withValues(alpha: 0.1),
                borderRadius: BorderRadius.circular(10),
              ),
              child: Icon(icon, color: color, size: 18),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(label,
                      style: TextStyle(
                          color: c.t1, fontSize: 14, fontWeight: FontWeight.w600)),
                  const SizedBox(height: 1),
                  Text(sub, style: TextStyle(color: c.t3, fontSize: 12)),
                ],
              ),
            ),
            Icon(Icons.chevron_right_rounded, color: c.t3, size: 18),
          ],
        ),
      ),
    );
  }
}
