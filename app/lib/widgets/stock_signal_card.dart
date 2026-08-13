import 'package:flutter/material.dart';
import '../models/stock_signal.dart';
import '../theme/app_colors.dart';

/// Card for a US stock swing signal. Mirrors NiftyOptionCard's layout so the
/// two feeds read the same way: what to buy, the levels, then the lifecycle.
class StockSignalCard extends StatelessWidget {
  final StockSignal signal;
  final VoidCallback? onTap;

  const StockSignalCard({super.key, required this.signal, this.onTap});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final color = c.long; // long-only strategy
    final resultColor = switch (signal.result) {
      StockResult.win => c.long,
      StockResult.loss => c.short,
      StockResult.expired => c.t3,
      StockResult.pending => c.accent,
    };
    final move = signal.movePct;

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
                    signal.ticker,
                    style: TextStyle(
                      color: c.t1,
                      fontSize: 18,
                      fontWeight: FontWeight.w800,
                      letterSpacing: -0.3,
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
                    'BUY',
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
            const SizedBox(height: 8),

            Container(
              width: double.infinity,
              padding: const EdgeInsets.symmetric(horizontal: 11, vertical: 9),
              decoration: BoxDecoration(
                color: color.withValues(alpha: 0.08),
                borderRadius: BorderRadius.circular(9),
                border: Border.all(color: color.withValues(alpha: 0.25)),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    signal.actionLabel,
                    style: TextStyle(
                      color: c.t1,
                      fontSize: 13,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  const SizedBox(height: 3),
                  Text(
                    'Risk \$${signal.riskPerShare.toStringAsFixed(2)}/share · '
                    'R:R ${signal.rrLabel}',
                    style: TextStyle(color: c.t3, fontSize: 11),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 10),

            Row(
              children: [
                _Tile(
                  label: 'ENTRY',
                  value: '\$${signal.entry.toStringAsFixed(2)}',
                  valueColor: c.t1,
                ),
                const SizedBox(width: 8),
                _Tile(
                  label: 'STOP',
                  value: '\$${signal.stopLoss.toStringAsFixed(2)}',
                  valueColor: c.short,
                ),
                const SizedBox(width: 8),
                _Tile(
                  label: 'TARGET',
                  value: '\$${signal.takeProfit.toStringAsFixed(2)}',
                  valueColor: c.long,
                ),
              ],
            ),
            // Only while open — once closed, exitPrice (folded into the
            // move% above) is the number that matters, and latestPrice
            // stops updating anyway (check_stock_signals only refreshes it
            // for still-open positions).
            if (signal.isPending && signal.latestPrice != null) ...[
              const SizedBox(height: 8),
              _Tile(
                label: 'LATEST (prior close)',
                value: '\$${signal.latestPrice!.toStringAsFixed(2)}',
                valueColor: move != null && move >= 0 ? c.long : c.short,
              ),
            ],
            const SizedBox(height: 10),

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
                    signal.statusLabel,
                    style: TextStyle(
                      color: resultColor,
                      fontSize: 10,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ),
                if (move != null)
                  Text(
                    '${move >= 0 ? '+' : ''}${move.toStringAsFixed(2)}%',
                    style: TextStyle(
                      color: move >= 0 ? c.long : c.short,
                      fontSize: 13,
                      fontWeight: FontWeight.w800,
                    ),
                  ),
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
                  sub: signal.holdLabel.isEmpty ? null : signal.holdLabel,
                ),
              ],
            ),
          ],
        ),
      ),
    );
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
              style: TextStyle(
                  color: c.t3,
                  fontSize: 9,
                  letterSpacing: 0.5,
                  fontWeight: FontWeight.w600)),
          const SizedBox(height: 2),
          Text(value,
              style: TextStyle(
                  color: c.t2, fontSize: 12, fontWeight: FontWeight.w600)),
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
            Text(label,
                style: TextStyle(
                    color: c.t3,
                    fontSize: 10,
                    letterSpacing: 0.4,
                    fontWeight: FontWeight.w600)),
            const SizedBox(height: 3),
            Text(value,
                style: TextStyle(
                    color: valueColor,
                    fontSize: 13,
                    fontWeight: FontWeight.w700)),
          ],
        ),
      ),
    );
  }
}
