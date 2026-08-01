import 'package:flutter/material.dart';
import '../models/nifty_option_signal.dart';
import '../theme/app_colors.dart';

/// Compact card for a NIFTY option signal. Mirrors [SignalCard] styling but
/// shows option-specific info: BUY CE/PE, strike, rupee stop, premium.
class NiftyOptionCard extends StatelessWidget {
  final NiftyOptionSignal signal;
  final VoidCallback? onTap;

  const NiftyOptionCard({super.key, required this.signal, this.onTap});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final color = signal.isBullish ? c.long : c.short;
    final resultColor = switch (signal.result) {
      OptionResult.win => c.long,
      OptionResult.loss => c.short,
      OptionResult.expired => c.t3,
      OptionResult.pending => c.accent,
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
            // Top row: instrument + side badge
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Expanded(
                  child: Text(
                    signal.instrumentLabel,
                    style: TextStyle(
                      color: c.t1,
                      fontSize: 17,
                      fontWeight: FontWeight.w800,
                      letterSpacing: -0.4,
                    ),
                  ),
                ),
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 9, vertical: 4),
                  decoration: BoxDecoration(
                    color: color.withValues(alpha: 0.12),
                    borderRadius: BorderRadius.circular(7),
                    border: Border.all(color: color.withValues(alpha: 0.35)),
                  ),
                  child: Text(
                    signal.sideLabel,
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
            const SizedBox(height: 12),

            // Level tiles: entry / stop / premium
            Row(
              children: [
                _Tile(
                  label: 'INDEX ENTRY',
                  value: signal.indexEntry.toStringAsFixed(0),
                  valueColor: c.t1,
                ),
                const SizedBox(width: 8),
                _Tile(
                  label: 'STOP (₹)',
                  value: '₹${signal.maxLossRs.toStringAsFixed(0)}',
                  valueColor: c.short,
                ),
                const SizedBox(width: 8),
                _Tile(
                  label: signal.premium != null ? 'PREMIUM' : 'STYLE',
                  value: signal.premium != null
                      ? '₹${signal.premium!.toStringAsFixed(0)}'
                      : signal.strikeStyle,
                  valueColor: c.accent,
                ),
              ],
            ),
            const SizedBox(height: 10),

            // Bottom row: result + P&L / expiry
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                  decoration: BoxDecoration(
                    color: resultColor.withValues(alpha: 0.1),
                    borderRadius: BorderRadius.circular(6),
                  ),
                  child: Text(
                    signal.isPending
                        ? (signal.entryConfirmed ? 'In trade' : 'Waiting')
                        : signal.result.name.toUpperCase(),
                    style: TextStyle(
                      color: resultColor,
                      fontSize: 10,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ),
                if (signal.pnlRs != null)
                  Text(
                    '${signal.pnlRs! >= 0 ? '+' : ''}₹${signal.pnlRs!.toStringAsFixed(0)}',
                    style: TextStyle(
                      color: signal.pnlRs! >= 0 ? c.long : c.short,
                      fontSize: 13,
                      fontWeight: FontWeight.w800,
                    ),
                  )
                else if (signal.isPending && signal.hasExpiry)
                  Text(
                    signal.expiryLabel,
                    style: TextStyle(color: c.t3, fontSize: 11),
                  ),
              ],
            ),

            // Lifecycle: when the trade was created and when it ended.
            const SizedBox(height: 10),
            Divider(height: 1, color: c.border),
            const SizedBox(height: 8),
            Row(
              children: [
                _TimeCol(
                  label: 'CREATED',
                  value: signal.createdLabel,
                ),
                _TimeCol(
                  label: signal.isPending ? 'EXPIRES' : 'CLOSED',
                  value: signal.closedLabel,
                  // Once closed, say *why* it ended and how long it ran.
                  sub: signal.isPending
                      ? null
                      : [
                          signal.exitReasonLabel,
                          if (signal.holdDurationLabel.isNotEmpty)
                            signal.holdDurationLabel,
                        ].join(' · '),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

/// One half of the created/closed footer row.
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
          Text(
            label,
            style: TextStyle(
              color: c.t3,
              fontSize: 9,
              letterSpacing: 0.5,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: 2),
          Text(
            value,
            style: TextStyle(
                color: c.t2, fontSize: 12, fontWeight: FontWeight.w600),
          ),
          if (sub != null) ...[
            const SizedBox(height: 1),
            Text(
              sub!,
              style: TextStyle(color: c.t3, fontSize: 10),
            ),
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

  const _Tile(
      {required this.label, required this.value, required this.valueColor});

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
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              label,
              style: TextStyle(
                color: c.t3,
                fontSize: 10,
                letterSpacing: 0.4,
                fontWeight: FontWeight.w600,
              ),
            ),
            const SizedBox(height: 3),
            Text(
              value,
              style: TextStyle(
                  color: valueColor, fontSize: 13, fontWeight: FontWeight.w700),
            ),
          ],
        ),
      ),
    );
  }
}
