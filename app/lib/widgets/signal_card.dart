import 'package:flutter/material.dart';
import '../models/signal.dart';
import '../theme/app_colors.dart';

class SignalCard extends StatelessWidget {
  final TradeSignal signal;
  final bool compact;
  final VoidCallback? onTap;

  const SignalCard({super.key, required this.signal, this.compact = false, this.onTap});

  bool get _isLong => signal.direction == SignalDirection.long;

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final dirColor = _isLong ? c.long : c.short;
    final barColor = signal.isWin
        ? c.long
        : signal.isLoss
            ? c.short
            : dirColor;

    const radius = BorderRadius.all(Radius.circular(13));
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Material(
        color: c.card,
        borderRadius: radius,
        child: InkWell(
          onTap: onTap,
          borderRadius: radius,
          child: Container(
            decoration: BoxDecoration(
              borderRadius: radius,
              border: Border.all(color: c.border),
            ),
            child: IntrinsicHeight(
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Container(
                    width: 4,
                    decoration: BoxDecoration(
                      color: barColor,
                      borderRadius: const BorderRadius.only(
                        topLeft: Radius.circular(13),
                        bottomLeft: Radius.circular(13),
                      ),
                    ),
                  ),
                  Expanded(
                    child: Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                      child: compact
                          ? _CompactBody(signal: signal, dirColor: dirColor)
                          : _FullBody(signal: signal, dirColor: dirColor),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _CompactBody extends StatelessWidget {
  final TradeSignal signal;
  final Color dirColor;

  const _CompactBody({required this.signal, required this.dirColor});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return Row(
      children: [
        _CoinIcon(pair: signal.pair, color: dirColor),
        const SizedBox(width: 12),
        Expanded(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Row(
                children: [
                  Text(signal.pair,
                      style: TextStyle(color: c.t1, fontSize: 14, fontWeight: FontWeight.w700)),
                  const SizedBox(width: 5),
                  _PerpChip(),
                  const SizedBox(width: 5),
                  _DirectionBadge(signal: signal, color: dirColor),
                ],
              ),
              const SizedBox(height: 2),
              // Show live price once the limit entry has filled; otherwise
              // show the waiting-for-entry price so it's clear it's not live yet.
              if (signal.latestPrice != null && signal.isPending && signal.entryConfirmed)
                _LivePriceLine(signal: signal)
              else if (signal.isPending && !signal.entryConfirmed)
                Text('Entry (waiting)  ${fmtPrice(signal.entry)}',
                    style: TextStyle(color: c.t2, fontSize: 12))
              else
                Text('Entry  ${fmtPrice(signal.entry)}',
                    style: TextStyle(color: c.t2, fontSize: 12)),
            ],
          ),
        ),
        _ResultOrConfidence(signal: signal),
      ],
    );
  }
}

class _FullBody extends StatelessWidget {
  final TradeSignal signal;
  final Color dirColor;

  const _FullBody({required this.signal, required this.dirColor});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Row(
              children: [
                _CoinIcon(pair: signal.pair, color: dirColor),
                const SizedBox(width: 10),
                Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Text(signal.pair,
                            style: TextStyle(color: c.t1, fontSize: 15, fontWeight: FontWeight.w700)),
                        const SizedBox(width: 5),
                        _PerpChip(),
                      ],
                    ),
                    const SizedBox(height: 1),
                    Text(timeAgo(signal.timestamp),
                        style: TextStyle(color: c.t3, fontSize: 11)),
                  ],
                ),
              ],
            ),
            Row(
              children: [
                _DirectionBadge(signal: signal, color: dirColor),
                const SizedBox(width: 8),
                _ResultOrConfidence(signal: signal),
              ],
            ),
          ],
        ),
        const SizedBox(height: 12),
        // Entry status — waiting for the limit fill, or live price once filled.
        if (signal.isPending && !signal.entryConfirmed) ...[
          _EntryWaitingBanner(signal: signal),
          const SizedBox(height: 8),
        ] else if (signal.latestPrice != null && signal.isPending) ...[
          _LivePriceBanner(signal: signal),
          const SizedBox(height: 8),
        ],
        Row(
          children: [
            _PriceTile(label: 'ENTRY', value: fmtPrice(signal.entry), valueColor: c.t1),
            const SizedBox(width: 8),
            _PriceTile(label: 'STOP', value: fmtPrice(signal.stopLoss), valueColor: c.short),
            const SizedBox(width: 8),
            _PriceTile(label: 'TARGET', value: fmtPrice(signal.takeProfit), valueColor: c.long),
            const SizedBox(width: 8),
            _RRTile(signal: signal),
          ],
        ),
        if (signal.isPending && signal.hasExpiry) ...[
          const SizedBox(height: 8),
          _ExpiryRow(signal: signal),
        ],
        if (!signal.isPending) ...[
          const SizedBox(height: 8),
          _PnlRow(signal: signal),
        ],
      ],
    );
  }
}

// Shows WIN/LOSS badge for closed signals, an ACTIVE badge for pending.
class _ResultOrConfidence extends StatelessWidget {
  final TradeSignal signal;

  const _ResultOrConfidence({required this.signal});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    if (signal.isWin) {
      return _ResultBadge(label: 'WIN', icon: Icons.check_rounded, color: c.long);
    }
    if (signal.isLoss) {
      return _ResultBadge(label: 'LOSS', icon: Icons.close_rounded, color: c.short);
    }
    // Pending — distinguish "limit order waiting to fill" from "filled, active".
    if (!signal.entryConfirmed) {
      return _ResultBadge(
          label: 'WAITING', icon: Icons.hourglass_empty_rounded, color: c.t2);
    }
    return _ResultBadge(
        label: 'ACTIVE', icon: Icons.bolt_rounded, color: c.gold);
  }
}

class _ResultBadge extends StatelessWidget {
  final String label;
  final IconData icon;
  final Color color;

  const _ResultBadge({required this.label, required this.icon, required this.color});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: color.withValues(alpha: 0.3)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, color: color, size: 12),
          const SizedBox(width: 3),
          Text(label,
              style: TextStyle(color: color, fontSize: 11, fontWeight: FontWeight.w800, letterSpacing: 0.5)),
        ],
      ),
    );
  }
}

class _PerpChip extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 2),
      decoration: BoxDecoration(
        color: c.accentBg,
        borderRadius: BorderRadius.circular(4),
        border: Border.all(color: c.accent.withValues(alpha: 0.35)),
      ),
      child: Text(
        'PERP',
        style: TextStyle(
          color: c.accent,
          fontSize: 8,
          fontWeight: FontWeight.w800,
          letterSpacing: 0.8,
        ),
      ),
    );
  }
}

class _DirectionBadge extends StatelessWidget {
  final TradeSignal signal;
  final Color color;

  const _DirectionBadge({required this.signal, required this.color});

  @override
  Widget build(BuildContext context) {
    final label = signal.direction == SignalDirection.long ? 'LONG' : 'SHORT';
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: color.withValues(alpha: 0.3)),
      ),
      child: Text(label,
          style: TextStyle(
              color: color, fontSize: 10, fontWeight: FontWeight.w800, letterSpacing: 0.8)),
    );
  }
}

class _PnlRow extends StatelessWidget {
  final TradeSignal signal;

  const _PnlRow({required this.signal});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final pnl = signal.pnlPercent;
    if (pnl == null) return const SizedBox.shrink();
    final isPos = pnl >= 0;
    final color = isPos ? c.long : c.short;
    return Row(
      children: [
        Icon(isPos ? Icons.arrow_upward_rounded : Icons.arrow_downward_rounded,
            color: color, size: 12),
        const SizedBox(width: 3),
        Text('${pnl.abs().toStringAsFixed(2)}% P&L  ·  Closed at ${fmtPrice(signal.closePrice!)}',
            style: TextStyle(color: color, fontSize: 11, fontWeight: FontWeight.w600)),
      ],
    );
  }
}

class _CoinIcon extends StatelessWidget {
  final String pair;
  final Color color;

  const _CoinIcon({required this.pair, required this.color});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final sym = pair.replaceAll('USDT', '').substring(0, 1);
    return Container(
      width: 38,
      height: 38,
      decoration: BoxDecoration(
        color: c.surface,
        shape: BoxShape.circle,
        border: Border.all(color: color.withValues(alpha: 0.4), width: 1.5),
      ),
      child: Center(
        child: Text(sym,
            style: TextStyle(color: color, fontSize: 15, fontWeight: FontWeight.w800)),
      ),
    );
  }
}

class _PriceTile extends StatelessWidget {
  final String label;
  final String value;
  final Color valueColor;

  const _PriceTile({required this.label, required this.value, required this.valueColor});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return Expanded(
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
        decoration: BoxDecoration(
          color: c.surface,
          borderRadius: BorderRadius.circular(8),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(label,
                style: TextStyle(
                    color: c.t3, fontSize: 10, letterSpacing: 0.4, fontWeight: FontWeight.w600)),
            const SizedBox(height: 3),
            Text(value,
                style: TextStyle(color: valueColor, fontSize: 12, fontWeight: FontWeight.w700)),
          ],
        ),
      ),
    );
  }
}

class _ExpiryRow extends StatelessWidget {
  final TradeSignal signal;
  const _ExpiryRow({required this.signal});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final color = signal.isExpiringSoon ? c.short : c.t3;
    final icon = signal.isExpiringSoon
        ? Icons.timer_outlined
        : Icons.schedule_rounded;
    return Row(
      children: [
        Icon(icon, color: color, size: 12),
        const SizedBox(width: 4),
        Text(
          signal.expiryLabel,
          style: TextStyle(color: color, fontSize: 11),
        ),
      ],
    );
  }
}

/// One-line subtitle in compact card: "Live $68,100  +1.02%"
class _LivePriceLine extends StatelessWidget {
  final TradeSignal signal;
  const _LivePriceLine({required this.signal});

  @override
  Widget build(BuildContext context) {
    final c    = context.colors;
    final pnl  = signal.livePnlPercent;
    final isUp = (pnl ?? 0) >= 0;
    final pnlColor = pnl == null ? c.t2 : isUp ? c.long : c.short;
    return Row(
      children: [
        Text('Last  ${fmtPrice(signal.latestPrice!)}',
            style: TextStyle(color: c.t1, fontSize: 12, fontWeight: FontWeight.w600)),
        if (pnl != null) ...[
          const SizedBox(width: 5),
          Text(
            '${isUp ? '+' : ''}${pnl.toStringAsFixed(2)}%',
            style: TextStyle(color: pnlColor, fontSize: 11, fontWeight: FontWeight.w700),
          ),
        ],
      ],
    );
  }
}

/// Full-width banner shown while the limit order hasn't filled yet.
class _EntryWaitingBanner extends StatelessWidget {
  final TradeSignal signal;
  const _EntryWaitingBanner({required this.signal});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: c.t2.withValues(alpha: 0.07),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: c.t2.withValues(alpha: 0.2)),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Row(
            children: [
              Icon(Icons.hourglass_empty_rounded, color: c.t2, size: 13),
              const SizedBox(width: 6),
              Text('Entry Initiated',
                  style: TextStyle(color: c.t2, fontSize: 11, fontWeight: FontWeight.w600)),
            ],
          ),
          Text('Waiting for fill',
              style: TextStyle(color: c.t2, fontSize: 11, fontWeight: FontWeight.w700)),
        ],
      ),
    );
  }
}

/// Full-width banner in the full card: shows live price + P&L bar
class _LivePriceBanner extends StatelessWidget {
  final TradeSignal signal;
  const _LivePriceBanner({required this.signal});

  @override
  Widget build(BuildContext context) {
    final c     = context.colors;
    final pnl   = signal.livePnlPercent;
    final isUp  = (pnl ?? 0) >= 0;
    final pnlColor = pnl == null ? c.t2 : isUp ? c.long : c.short;

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: pnlColor.withValues(alpha: 0.07),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: pnlColor.withValues(alpha: 0.2)),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Row(
            children: [
              Container(
                width: 6, height: 6,
                decoration: BoxDecoration(color: pnlColor, shape: BoxShape.circle),
              ),
              const SizedBox(width: 6),
              Text('Last Updated',
                  style: TextStyle(color: c.t2, fontSize: 11, fontWeight: FontWeight.w600)),
            ],
          ),
          Row(
            children: [
              Text(fmtPrice(signal.latestPrice!),
                  style: TextStyle(color: c.t1, fontSize: 13, fontWeight: FontWeight.w800)),
              if (pnl != null) ...[
                const SizedBox(width: 8),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                  decoration: BoxDecoration(
                    color: pnlColor.withValues(alpha: 0.12),
                    borderRadius: BorderRadius.circular(5),
                  ),
                  child: Text(
                    '${isUp ? '+' : ''}${pnl.toStringAsFixed(2)}%',
                    style: TextStyle(
                        color: pnlColor, fontSize: 11, fontWeight: FontWeight.w800),
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

class _RRTile extends StatelessWidget {
  final TradeSignal signal;
  const _RRTile({required this.signal});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final rr = signal.rrRatio;
    final color = rr >= 2.0 ? c.long : rr >= 1.5 ? c.gold : c.t2;
    return Expanded(
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.08),
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: color.withValues(alpha: 0.25)),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('RR',
                style: TextStyle(
                    color: c.t3, fontSize: 9, letterSpacing: 0.4, fontWeight: FontWeight.w600)),
            const SizedBox(height: 3),
            Text(signal.rrLabel,
                style: TextStyle(color: color, fontSize: 12, fontWeight: FontWeight.w800)),
          ],
        ),
      ),
    );
  }
}

String fmtPrice(double v) {
  if (v >= 1000) return '\$${v.toStringAsFixed(2)}';
  if (v >= 1) return '\$${v.toStringAsFixed(3)}';
  return '\$${v.toStringAsFixed(4)}';
}

String timeAgo(DateTime dt) {
  final d = DateTime.now().difference(dt);
  if (d.inMinutes < 60) return '${d.inMinutes}m ago';
  if (d.inHours < 24) return '${d.inHours}h ago';
  if (d.inDays < 30) return '${d.inDays}d ago';
  return '${(d.inDays / 30).floor()}mo ago';
}
