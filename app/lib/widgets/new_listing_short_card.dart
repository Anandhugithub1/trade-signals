import 'package:flutter/material.dart';
import '../models/new_listing_short.dart';
import '../theme/app_colors.dart';

/// Compact card for a "short new listing" signal. Mirrors the other
/// signal cards' styling but always shows SHORT (this strategy is
/// short-only by design) with its stop/lock levels and listing age.
class NewListingShortCard extends StatelessWidget {
  final NewListingShort signal;
  final VoidCallback? onTap;

  const NewListingShortCard({super.key, required this.signal, this.onTap});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final color = c.short; // this strategy is short-only
    final resultColor = switch (signal.result) {
      ShortResult.win => c.long,
      ShortResult.loss => c.short,
      ShortResult.expired => c.t3,
      ShortResult.pending => c.accent,
    };

    return GestureDetector(
      onTap: onTap,
      child: Container(
        margin: const EdgeInsets.only(bottom: 10),
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
                Expanded(
                  child: Text(
                    signal.assetLabel,
                    style: TextStyle(
                      color: c.t1,
                      fontSize: 17,
                      fontWeight: FontWeight.w800,
                      letterSpacing: -0.4,
                    ),
                  ),
                ),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 4),
                  decoration: BoxDecoration(
                    color: color.withValues(alpha: 0.12),
                    borderRadius: BorderRadius.circular(7),
                    border: Border.all(color: color.withValues(alpha: 0.35)),
                  ),
                  child: Text(
                    'SHORT',
                    style: TextStyle(
                      color: color,
                      fontSize: 11,
                      fontWeight: FontWeight.w800,
                      letterSpacing: 0.6,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 4),
            Text(
              signal.ageLabel,
              style: TextStyle(color: c.t3, fontSize: 11),
            ),
            const SizedBox(height: 10),

            Container(
              width: double.infinity,
              padding: const EdgeInsets.symmetric(horizontal: 11, vertical: 9),
              decoration: BoxDecoration(
                color: color.withValues(alpha: 0.08),
                borderRadius: BorderRadius.circular(9),
                border: Border.all(color: color.withValues(alpha: 0.25)),
              ),
              child: Text(
                signal.actionLabel,
                style: TextStyle(color: c.t1, fontSize: 13, fontWeight: FontWeight.w700),
              ),
            ),
            const SizedBox(height: 10),

            Row(
              children: [
                _Tile(label: 'ENTRY', value: _fmt(signal.entry), valueColor: c.t1),
                const SizedBox(width: 8),
                _Tile(label: 'STOP (+30%)', value: _fmt(signal.stopPrice), valueColor: c.short),
                const SizedBox(width: 8),
                _Tile(label: 'LOCK (-50%)', value: _fmt(signal.lockPrice), valueColor: c.long),
              ],
            ),
            const SizedBox(height: 10),

            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                  decoration: BoxDecoration(
                    color: resultColor.withValues(alpha: 0.1),
                    borderRadius: BorderRadius.circular(6),
                  ),
                  child: Text(
                    signal.isPending ? 'Open' : signal.result.name.toUpperCase(),
                    style: TextStyle(color: resultColor, fontSize: 10, fontWeight: FontWeight.w700),
                  ),
                ),
                if (signal.pnlPct != null)
                  Text(
                    '${signal.pnlPct! >= 0 ? '+' : ''}${signal.pnlPct!.toStringAsFixed(1)}%',
                    style: TextStyle(
                      color: signal.pnlPct! >= 0 ? c.long : c.short,
                      fontSize: 13,
                      fontWeight: FontWeight.w800,
                    ),
                  )
                else if (signal.isPending && signal.hasExpiry)
                  Text(signal.expiryLabel, style: TextStyle(color: c.t3, fontSize: 11)),
              ],
            ),

            const SizedBox(height: 10),
            Divider(height: 1, color: c.border),
            const SizedBox(height: 8),
            Row(
              children: [
                _TimeCol(label: 'CREATED', value: signal.createdLabel),
                _TimeCol(
                  label: signal.isPending ? 'EXPIRES' : 'CLOSED',
                  value: signal.closedLabel,
                  sub: signal.isPending ? null : signal.exitReasonLabel,
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  static String _fmt(double v) {
    // Many of these coins trade at sub-cent prices; show enough precision
    // to be meaningful either way.
    if (v >= 1) return v.toStringAsFixed(2);
    if (v >= 0.01) return v.toStringAsFixed(4);
    return v.toStringAsFixed(6);
  }
}

class _TimeCol extends StatelessWidget {
  final String label;
  final String value;
  final String? sub;

  const _TimeCol({required this.label, required this.value, this.sub});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return Expanded(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label,
              style: TextStyle(color: c.t3, fontSize: 9, letterSpacing: 0.5, fontWeight: FontWeight.w600)),
          const SizedBox(height: 2),
          Text(value, style: TextStyle(color: c.t2, fontSize: 12, fontWeight: FontWeight.w600)),
          if (sub != null) ...[
            const SizedBox(height: 1),
            Text(sub!, style: TextStyle(color: c.t3, fontSize: 10)),
          ],
        ],
      ),
    );
  }
}

class _Tile extends StatelessWidget {
  final String label;
  final String value;
  final Color valueColor;

  const _Tile({required this.label, required this.value, required this.valueColor});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return Expanded(
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 9),
        decoration: BoxDecoration(color: c.surface, borderRadius: BorderRadius.circular(9)),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(label, style: TextStyle(color: c.t3, fontSize: 9, letterSpacing: 0.3, fontWeight: FontWeight.w600)),
            const SizedBox(height: 3),
            Text(value, style: TextStyle(color: valueColor, fontSize: 12, fontWeight: FontWeight.w700)),
          ],
        ),
      ),
    );
  }
}
