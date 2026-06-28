import 'package:flutter/material.dart';
import 'package:supabase_flutter/supabase_flutter.dart';
import '../models/signal.dart';
import '../services/supabase_service.dart';
import '../theme/app_colors.dart';

// Derives a display name from an email address.
// "next.anandhu@gmail.com" → "Next"
String _firstName(String email) {
  final local = email.split('@').first;
  final part  = local.split(RegExp(r'[._+\-]')).firstWhere((p) => p.isNotEmpty, orElse: () => 'trader');
  return part[0].toUpperCase() + part.substring(1).toLowerCase();
}

class ProfileScreen extends StatefulWidget {
  const ProfileScreen({super.key});

  @override
  State<ProfileScreen> createState() => _ProfileScreenState();
}

class _ProfileScreenState extends State<ProfileScreen> {
  late Future<List<TradeSignal>> _signalsFuture;

  @override
  void initState() {
    super.initState();
    _signalsFuture = SupabaseService.fetchSignals();
  }

  @override
  Widget build(BuildContext context) {
    final c    = context.colors;
    final user = Supabase.instance.client.auth.currentUser;
    final email   = user?.email ?? '';
    final initial = email.isNotEmpty ? email[0].toUpperCase() : 'T';

    return Scaffold(
      backgroundColor: c.bg,
      body: SafeArea(
        child: FutureBuilder<List<TradeSignal>>(
          future: _signalsFuture,
          builder: (context, snap) {
            final signals = snap.data ?? [];
            final stats   = SignalStats.from(signals);
            return ListView(
              padding: const EdgeInsets.symmetric(horizontal: 20),
              physics: const BouncingScrollPhysics(),
              children: [
                const SizedBox(height: 20),
                _TopBar(),
                const SizedBox(height: 28),
                _AvatarSection(initial: initial, email: email),
                const SizedBox(height: 20),
                _FreePlanCard(),
                const SizedBox(height: 16),
                _StatsCard(stats: stats, loading: snap.connectionState == ConnectionState.waiting),
                const SizedBox(height: 16),
                const _MenuCard(),
                const SizedBox(height: 28),
              ],
            );
          },
        ),
      ),
    );
  }
}

class _TopBar extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text('Profile',
            style: TextStyle(
                color: c.t1, fontSize: 26, fontWeight: FontWeight.w800, letterSpacing: -0.5)),
        Icon(Icons.settings_outlined, color: c.t2, size: 22),
      ],
    );
  }
}

class _AvatarSection extends StatelessWidget {
  final String initial;
  final String email;
  const _AvatarSection({required this.initial, required this.email});

  @override
  Widget build(BuildContext context) {
    final c    = context.colors;
    final name = email.isNotEmpty ? _firstName(email) : 'Trader';
    return Column(
      children: [
        Container(
          width: 76,
          height: 76,
          decoration: BoxDecoration(
            color: c.accentBg,
            shape: BoxShape.circle,
            border: Border.all(color: c.accent.withValues(alpha: 0.45), width: 2.5),
          ),
          child: Center(
            child: Text(initial,
                style: TextStyle(color: c.accent, fontSize: 30, fontWeight: FontWeight.w800)),
          ),
        ),
        const SizedBox(height: 12),
        Text(name,
            style: TextStyle(color: c.t1, fontSize: 20, fontWeight: FontWeight.w700)),
        const SizedBox(height: 3),
        Text(email.isNotEmpty ? email : 'Not signed in',
            style: TextStyle(color: c.t2, fontSize: 13)),
        const SizedBox(height: 8),
        // FREE badge
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
          decoration: BoxDecoration(
            color: c.accentBg,
            borderRadius: BorderRadius.circular(20),
            border: Border.all(color: c.accent.withValues(alpha: 0.3)),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.check_circle_outline_rounded, color: c.accent, size: 13),
              const SizedBox(width: 5),
              Text('Free Access · MVP',
                  style: TextStyle(color: c.accent, fontSize: 11, fontWeight: FontWeight.w700)),
            ],
          ),
        ),
      ],
    );
  }
}

class _FreePlanCard extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: c.card,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: c.accent.withValues(alpha: 0.25)),
      ),
      child: Row(
        children: [
          Container(
            width: 44,
            height: 44,
            decoration: BoxDecoration(
              color: c.accentBg,
              borderRadius: BorderRadius.circular(11),
              border: Border.all(color: c.accent.withValues(alpha: 0.25)),
            ),
            child: Icon(Icons.rocket_launch_rounded, color: c.accent, size: 20),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Text('Free Plan',
                        style: TextStyle(
                            color: c.t1, fontSize: 15, fontWeight: FontWeight.w700)),
                    const SizedBox(width: 8),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                      decoration: BoxDecoration(
                          color: c.accentBg, borderRadius: BorderRadius.circular(4)),
                      child: Text('ACTIVE',
                          style: TextStyle(
                              color: c.accent,
                              fontSize: 9,
                              fontWeight: FontWeight.w800,
                              letterSpacing: 0.8)),
                    ),
                  ],
                ),
                const SizedBox(height: 3),
                Text('All signals free during MVP launch',
                    style: TextStyle(color: c.t2, fontSize: 12)),
                const SizedBox(height: 6),
                Text('Full access · No credit card required',
                    style: TextStyle(color: c.t3, fontSize: 11)),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _StatsCard extends StatelessWidget {
  final SignalStats stats;
  final bool loading;
  const _StatsCard({required this.stats, required this.loading});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
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
              Text('Signal Statistics',
                  style: TextStyle(color: c.t1, fontSize: 15, fontWeight: FontWeight.w700)),
              Text('Last 90 days', style: TextStyle(color: c.t3, fontSize: 11)),
            ],
          ),
          const SizedBox(height: 16),
          if (loading)
            const Center(child: Padding(padding: EdgeInsets.all(12), child: CircularProgressIndicator()))
          else ...[
            Row(
              children: [
                _StatItem(value: '${stats.total}',  label: 'Total\nSignals', color: c.accent),
                _VDivider(),
                _StatItem(value: '${stats.wins}',   label: 'Signals\nWon',  color: c.long),
                _VDivider(),
                _StatItem(value: '${stats.losses}', label: 'Signals\nLost', color: c.short),
                _VDivider(),
                _StatItem(
                    value: '${(stats.winRate * 100).toStringAsFixed(0)}%',
                    label: 'Win\nRate',
                    color: stats.winRate >= 0.6 ? c.long : c.gold),
              ],
            ),
            if (stats.closed > 0) ...[
              const SizedBox(height: 14),
              ClipRRect(
                borderRadius: BorderRadius.circular(4),
                child: SizedBox(
                  height: 5,
                  child: Row(
                    children: [
                      Flexible(flex: stats.wins,   child: Container(color: c.long)),
                      const SizedBox(width: 2),
                      Flexible(flex: stats.losses, child: Container(color: c.short)),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 6),
              Text('Based on ${stats.closed} closed signals',
                  style: TextStyle(color: c.t3, fontSize: 11)),
            ] else ...[
              const SizedBox(height: 10),
              Text('No closed signals yet — check back after signals resolve.',
                  style: TextStyle(color: c.t3, fontSize: 12)),
            ],
          ],
        ],
      ),
    );
  }
}

class _StatItem extends StatelessWidget {
  final String value;
  final String label;
  final Color color;
  const _StatItem({required this.value, required this.label, required this.color});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return Expanded(
      child: Column(
        children: [
          Text(value,
              style: TextStyle(
                  color: color, fontSize: 20, fontWeight: FontWeight.w800, letterSpacing: -0.3)),
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
        width: 1, height: 44, color: c.border,
        margin: const EdgeInsets.symmetric(horizontal: 6));
  }
}

class _MenuCard extends StatelessWidget {
  const _MenuCard();

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final items = [
      (Icons.notifications_outlined,  'Notifications',   'Push alerts for new signals',  c.accent, null as String?),
      (Icons.warning_amber_rounded,   'Risk Disclaimer', 'Read before trading',           const Color(0xFFF59E0B), '/disclaimer/info'),
      (Icons.help_outline_rounded,    'Help & Support',  'FAQs and feedback',             c.long, null),
      (Icons.info_outline_rounded,    'About',           'TradePilot v1.0.0 · MVP',       c.t2, null),
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
                icon: icon, label: label, sub: sub, color: color,
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
    required this.icon, required this.label,
    required this.sub,  required this.color, this.onTap,
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
              width: 38, height: 38,
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
