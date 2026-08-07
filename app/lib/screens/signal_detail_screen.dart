import 'package:flutter/material.dart';
import '../models/signal.dart';
import '../theme/app_colors.dart';
import '../widgets/signal_card.dart' show fmtPrice, timeAgo;

class SignalDetailScreen extends StatelessWidget {
  final TradeSignal signal;

  const SignalDetailScreen({super.key, required this.signal});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final isLong = signal.direction == SignalDirection.long;
    final dirColor = isLong ? c.long : c.short;
    final dirLabel = isLong ? 'LONG' : 'SHORT';

    return Scaffold(
      backgroundColor: c.bg,
      appBar: AppBar(
        backgroundColor: c.bg,
        elevation: 0,
        leading: IconButton(
          icon: Icon(Icons.arrow_back_ios_new_rounded, color: c.t1, size: 18),
          onPressed: () => Navigator.pop(context),
        ),
        title: Row(
          children: [
            Text(signal.pair,
                style: TextStyle(
                    color: c.t1, fontWeight: FontWeight.w800, fontSize: 18)),
            const SizedBox(width: 6),
            _Badge(label: 'PERP', color: c.accent),
            const SizedBox(width: 6),
            _Badge(
                label: signal.strategyLabel,
                color: signal.isDonchian ? c.long : c.t3),
            const SizedBox(width: 6),
            _Badge(label: dirLabel, color: dirColor),
            if (!signal.isPending) ...[
              const SizedBox(width: 6),
              _ResultBadge(signal: signal),
            ],
          ],
        ),
      ),
      body: ListView(
        padding: const EdgeInsets.all(20),
        physics: const BouncingScrollPhysics(),
        children: [
          // Result banner for closed signals
          if (!signal.isPending) _ResultBanner(signal: signal),
          if (!signal.isPending) const SizedBox(height: 14),

          _PriceLevelsCard(signal: signal),
          const SizedBox(height: 14),
          _RRCard(signal: signal),
          const SizedBox(height: 24),

          // Only show action buttons for active signals
          if (signal.isPending) ...[
            SizedBox(
              width: double.infinity,
              child: ElevatedButton.icon(
                onPressed: () {},
                style: ElevatedButton.styleFrom(
                  backgroundColor: c.accent,
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(vertical: 14),
                  shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(12)),
                  elevation: 0,
                ),
                icon: const Icon(Icons.notifications_active_outlined, size: 18),
                label: const Text('Set Price Alert',
                    style:
                        TextStyle(fontSize: 15, fontWeight: FontWeight.w700)),
              ),
            ),
            const SizedBox(height: 10),
            SizedBox(
              width: double.infinity,
              child: OutlinedButton.icon(
                onPressed: () {},
                style: OutlinedButton.styleFrom(
                  foregroundColor: c.t2,
                  side: BorderSide(color: c.border),
                  padding: const EdgeInsets.symmetric(vertical: 14),
                  shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(12)),
                ),
                icon: const Icon(Icons.bookmark_border_rounded, size: 18),
                label: const Text('Save Signal',
                    style:
                        TextStyle(fontSize: 15, fontWeight: FontWeight.w600)),
              ),
            ),
          ],
        ],
      ),
    );
  }
}

// Closed signal — full-width result banner with P&L
class _ResultBanner extends StatelessWidget {
  final TradeSignal signal;

  const _ResultBanner({required this.signal});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final isWin = signal.isWin;
    final color = isWin ? c.long : c.short;
    final icon = isWin ? Icons.check_circle_rounded : Icons.cancel_rounded;
    final pnl = signal.pnlPercent;

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: color.withValues(alpha: 0.3)),
      ),
      child: Row(
        children: [
          Icon(icon, color: color, size: 28),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(isWin ? 'Signal Closed — Win' : 'Signal Closed — Loss',
                    style: TextStyle(
                        color: color, fontSize: 14, fontWeight: FontWeight.w700)),
                const SizedBox(height: 2),
                if (signal.closePrice != null)
                  Text(
                    'Closed at ${fmtPrice(signal.closePrice!)}',
                    style: TextStyle(color: c.t2, fontSize: 12),
                  ),
              ],
            ),
          ),
          if (pnl != null)
            Column(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Text(
                  '${pnl >= 0 ? '+' : ''}${pnl.toStringAsFixed(2)}%',
                  style: TextStyle(
                      color: color, fontSize: 20, fontWeight: FontWeight.w900),
                ),
                Text('P&L', style: TextStyle(color: c.t3, fontSize: 11)),
              ],
            ),
        ],
      ),
    );
  }
}

class _PriceLevelsCard extends StatelessWidget {
  final TradeSignal signal;

  const _PriceLevelsCard({required this.signal});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return _Card(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Price Levels',
              style: TextStyle(
                  color: c.t1, fontSize: 15, fontWeight: FontWeight.w700)),
          const SizedBox(height: 12),
          // Live price row — only meaningful once the limit entry has filled
          if (signal.latestPrice != null && signal.isPending && signal.entryConfirmed) ...[
            _LivePriceRow(signal: signal),
            Divider(height: 1, color: c.border),
          ],
          _PriceRow(label: 'Entry Price', value: fmtPrice(signal.entry), color: c.t1),
          Divider(height: 1, color: c.border),
          if (signal.isPending) ...[
            _PriceRow(
              label: 'Entry Initiated',
              value: signal.entryConfirmed ? 'Yes' : 'Waiting',
              color: signal.entryConfirmed ? c.long : c.t2,
            ),
            Divider(height: 1, color: c.border),
          ],
          _PriceRow(label: 'Stop Loss', value: fmtPrice(signal.stopLoss), color: c.short),
          Divider(height: 1, color: c.border),
          _PriceRow(label: 'Take Profit', value: fmtPrice(signal.takeProfit), color: c.long),
          Divider(height: 1, color: c.border),
          if (signal.closePrice != null) ...[
            _PriceRow(
              label: 'Closed At',
              value: fmtPrice(signal.closePrice!),
              color: signal.isWin ? c.long : c.short,
            ),
            Divider(height: 1, color: c.border),
          ],
          _PriceRow(label: 'Posted', value: timeAgo(signal.timestamp), color: c.t2),
          Divider(height: 1, color: c.border),
          // Which engine generated this. Given a full row rather than only a
          // header chip: "which algorithm produced this signal" is a primary
          // question while two engines run side by side, and a small badge
          // is easy to miss.
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 10),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Algorithm',
                    style: TextStyle(color: c.t2, fontSize: 14)),
                const Spacer(),
                Flexible(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.end,
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 8, vertical: 3),
                        decoration: BoxDecoration(
                          color: (signal.isDonchian ? c.long : c.t3)
                              .withValues(alpha: 0.12),
                          borderRadius: BorderRadius.circular(6),
                          border: Border.all(
                              color: (signal.isDonchian ? c.long : c.t3)
                                  .withValues(alpha: 0.4)),
                        ),
                        child: Text(
                          signal.strategyFullName,
                          style: TextStyle(
                            color: signal.isDonchian ? c.long : c.t2,
                            fontSize: 12,
                            fontWeight: FontWeight.w800,
                            letterSpacing: 0.3,
                          ),
                        ),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        signal.strategyNote,
                        textAlign: TextAlign.right,
                        style: TextStyle(color: c.t3, fontSize: 11),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          if (signal.hasExpiry && signal.isPending) ...[
            Divider(height: 1, color: c.border),
            _PriceRow(
              label: 'Expires',
              value: signal.expiryLabel,
              color: signal.isExpiringSoon ? c.short : c.t2,
            ),
          ],
        ],
      ),
    );
  }
}

class _PriceRow extends StatelessWidget {
  final String label;
  final String value;
  final Color color;

  const _PriceRow({required this.label, required this.value, required this.color});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 10),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(label, style: TextStyle(color: c.t2, fontSize: 14)),
          // Flexible + right-align: most values are short prices, but the
          // Strategy row carries a full sentence that would otherwise
          // overflow the row on narrow screens.
          Flexible(
            child: Text(
              value,
              textAlign: TextAlign.right,
              style: TextStyle(
                  color: color, fontSize: 14, fontWeight: FontWeight.w700),
            ),
          ),
        ],
      ),
    );
  }
}

class _LivePriceRow extends StatelessWidget {
  final TradeSignal signal;
  const _LivePriceRow({required this.signal});

  @override
  Widget build(BuildContext context) {
    final c    = context.colors;
    final pnl  = signal.livePnlPercent;
    final isPos = (pnl ?? 0) >= 0;
    final pnlColor = pnl == null
        ? c.t2
        : isPos ? c.long : c.short;

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 10),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Row(
            children: [
              Container(
                width: 7, height: 7,
                decoration: BoxDecoration(color: c.long, shape: BoxShape.circle),
              ),
              const SizedBox(width: 6),
              Text('Last Updated Price',
                  style: TextStyle(color: c.t2, fontSize: 14)),
            ],
          ),
          Row(
            children: [
              Text(fmtPrice(signal.latestPrice!),
                  style: TextStyle(
                      color: c.t1, fontSize: 14, fontWeight: FontWeight.w700)),
              if (pnl != null) ...[
                const SizedBox(width: 8),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                  decoration: BoxDecoration(
                    color: pnlColor.withValues(alpha: 0.1),
                    borderRadius: BorderRadius.circular(5),
                  ),
                  child: Text(
                    '${pnl >= 0 ? '+' : ''}${pnl.toStringAsFixed(2)}%',
                    style: TextStyle(
                        color: pnlColor, fontSize: 11, fontWeight: FontWeight.w700),
                  ),
                ),
              ],
            ],
          ),
        ],
      ),
    );
  }
}

class _RRCard extends StatelessWidget {
  final TradeSignal signal;

  const _RRCard({required this.signal});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final risk   = (signal.entry - signal.stopLoss).abs();
    final reward = (signal.takeProfit - signal.entry).abs();
    final rr     = signal.rrRatio;
    final rrColor = rr >= 2.0 ? c.long : rr >= 1.5 ? c.gold : c.short;

    return _Card(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text('Risk / Reward',
                  style: TextStyle(color: c.t1, fontSize: 15, fontWeight: FontWeight.w700)),
              // Quality badge
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                decoration: BoxDecoration(
                  color: rrColor.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: rrColor.withValues(alpha: 0.3)),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(signal.rrLabel,
                        style: TextStyle(
                            color: rrColor, fontSize: 14, fontWeight: FontWeight.w900)),
                    const SizedBox(width: 6),
                    Text(signal.rrQuality,
                        style: TextStyle(
                            color: rrColor.withValues(alpha: 0.75),
                            fontSize: 11,
                            fontWeight: FontWeight.w600)),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 14),
          Row(
            children: [
              _RRItem(label: 'Risk \$', value: fmtPrice(risk), color: c.short),
              Container(
                  width: 1, height: 36, color: c.border,
                  margin: const EdgeInsets.symmetric(horizontal: 16)),
              _RRItem(label: 'Reward \$', value: fmtPrice(reward), color: c.long),
              Container(
                  width: 1, height: 36, color: c.border,
                  margin: const EdgeInsets.symmetric(horizontal: 16)),
              _RRItem(
                  label: 'Multiple',
                  value: '×${rr.toStringAsFixed(2)}',
                  color: rrColor),
            ],
          ),
        ],
      ),
    );
  }
}

class _RRItem extends StatelessWidget {
  final String label;
  final String value;
  final Color color;

  const _RRItem({required this.label, required this.value, required this.color});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return Expanded(
      child: Column(
        children: [
          Text(value,
              textAlign: TextAlign.center,
              style: TextStyle(
                  color: color, fontSize: 14, fontWeight: FontWeight.w700)),
          const SizedBox(height: 3),
          Text(label,
              textAlign: TextAlign.center,
              style: TextStyle(color: c.t3, fontSize: 11)),
        ],
      ),
    );
  }
}

class _Badge extends StatelessWidget {
  final String label;
  final Color color;

  const _Badge({required this.label, required this.color});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: color.withValues(alpha: 0.35)),
      ),
      child: Text(label,
          style: TextStyle(
              color: color,
              fontSize: 11,
              fontWeight: FontWeight.w800,
              letterSpacing: 0.8)),
    );
  }
}

class _ResultBadge extends StatelessWidget {
  final TradeSignal signal;

  const _ResultBadge({required this.signal});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final color = signal.isWin ? c.long : c.short;
    final icon = signal.isWin ? Icons.check_rounded : Icons.close_rounded;
    final label = signal.isWin ? 'WIN' : 'LOSS';

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: color.withValues(alpha: 0.35)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, color: color, size: 11),
          const SizedBox(width: 3),
          Text(label,
              style: TextStyle(
                  color: color,
                  fontSize: 11,
                  fontWeight: FontWeight.w800,
                  letterSpacing: 0.5)),
        ],
      ),
    );
  }
}

class _Card extends StatelessWidget {
  final Widget child;

  const _Card({required this.child});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: c.card,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: c.border),
      ),
      child: child,
    );
  }
}
