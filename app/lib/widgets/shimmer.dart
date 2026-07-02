import 'package:flutter/material.dart';
import '../theme/app_colors.dart';

/// Animated shimmer placeholder — a highlight band sweeps left→right.
/// Used by loading skeletons instead of static grey boxes.
class ShimmerBox extends StatefulWidget {
  final double height;
  final double? width;
  final BorderRadius borderRadius;

  const ShimmerBox({
    super.key,
    required this.height,
    this.width,
    this.borderRadius = const BorderRadius.all(Radius.circular(16)),
  });

  @override
  State<ShimmerBox> createState() => _ShimmerBoxState();
}

class _ShimmerBoxState extends State<ShimmerBox>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 1400),
  )..repeat();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return AnimatedBuilder(
      animation: _controller,
      builder: (context, _) {
        final t = _controller.value;
        return Container(
          height: widget.height,
          width: widget.width ?? double.infinity,
          decoration: BoxDecoration(
            borderRadius: widget.borderRadius,
            gradient: LinearGradient(
              // Band sweeps from off-screen left to off-screen right
              begin: Alignment(-1.5 + t * 4, -0.2),
              end: Alignment(0.0 + t * 4, 0.2),
              colors: [c.card, c.surface, c.card],
            ),
          ),
        );
      },
    );
  }
}

/// One-shot fade + slide-up entrance. Give each list item an increasing
/// [delayMs] for a staggered reveal.
class FadeIn extends StatelessWidget {
  final Widget child;
  final int delayMs;

  const FadeIn({super.key, required this.child, this.delayMs = 0});

  @override
  Widget build(BuildContext context) {
    final total = 350 + delayMs;
    return TweenAnimationBuilder<double>(
      tween: Tween(begin: 0.0, end: 1.0),
      duration: Duration(milliseconds: total),
      curve: Interval(delayMs / total, 1.0, curve: Curves.easeOutCubic),
      builder: (context, v, child) => Opacity(
        opacity: v.clamp(0.0, 1.0),
        child: Transform.translate(
          offset: Offset(0, 14 * (1 - v)),
          child: child,
        ),
      ),
      child: child,
    );
  }
}
