import 'dart:math';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

class SplashScreen extends StatefulWidget {
  const SplashScreen({super.key});

  @override
  State<SplashScreen> createState() => _SplashScreenState();
}

class _SplashScreenState extends State<SplashScreen>
    with TickerProviderStateMixin {
  // Entrance — runs once
  late final AnimationController _enterCtrl;
  // Continuous logo glow pulse
  late final AnimationController _pulseCtrl;
  // Spinning arc rings
  late final AnimationController _spinCtrl;
  // Bouncing loading dots
  late final AnimationController _dotCtrl;

  @override
  void initState() {
    super.initState();
    SystemChrome.setSystemUIOverlayStyle(const SystemUiOverlayStyle(
      statusBarColor: Colors.transparent,
      statusBarIconBrightness: Brightness.light,
    ));

    _enterCtrl = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1800),
    );
    _pulseCtrl = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 2200),
    )..repeat(reverse: true);
    _spinCtrl = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 6),
    )..repeat();
    _dotCtrl = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1100),
    )..repeat();

    _enterCtrl.forward();

    Future.delayed(const Duration(milliseconds: 3200), () {
      if (mounted) Navigator.of(context).pushReplacementNamed('/disclaimer');
    });
  }

  @override
  void dispose() {
    _enterCtrl.dispose();
    _pulseCtrl.dispose();
    _spinCtrl.dispose();
    _dotCtrl.dispose();
    super.dispose();
  }

  // Convenience: create an animated value from the entrance controller
  Animation<T> _enter<T>(
    Tween<T> tween,
    double start,
    double end, {
    Curve curve = Curves.easeOut,
  }) =>
      tween.animate(
        CurvedAnimation(
          parent: _enterCtrl,
          curve: Interval(start, end, curve: curve),
        ),
      );

  @override
  Widget build(BuildContext context) {
    // ── entrance animations ──────────────────────────────
    final logoScale = _enter(
      Tween(begin: 0.0, end: 1.0), 0.0, 0.55,
      curve: Curves.elasticOut,
    );
    final logoFade = _enter(Tween(begin: 0.0, end: 1.0), 0.0, 0.35);

    final titleFade = _enter(Tween(begin: 0.0, end: 1.0), 0.38, 0.65);
    final titleSlide = _enter(
      Tween(begin: const Offset(0, 0.35), end: Offset.zero), 0.38, 0.65,
      curve: Curves.easeOutCubic,
    );

    final tagFade  = _enter(Tween(begin: 0.0, end: 1.0), 0.60, 0.90);
    final tagSlide = _enter(
      Tween(begin: const Offset(0, 0.5), end: Offset.zero), 0.60, 0.90,
      curve: Curves.easeOutCubic,
    );

    final bottomFade = _enter(Tween(begin: 0.0, end: 1.0), 0.75, 1.0);

    return Scaffold(
      backgroundColor: const Color(0xFF060C16),
      body: Stack(
        children: [
          // ── Layer 1: background grid + glows ──
          const Positioned.fill(child: _Background()),

          // ── Layer 2: main content ──
          Center(
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                // ── Logo area: spinning rings + icon box ──
                SizedBox(
                  width: 168,
                  height: 168,
                  child: Stack(
                    alignment: Alignment.center,
                    children: [
                      // Outer spinning arc (blue, clockwise)
                      AnimatedBuilder(
                        animation: _spinCtrl,
                        builder: (context, child) => CustomPaint(
                          size: const Size(164, 164),
                          painter: _ArcPainter(
                            angle: _spinCtrl.value * 2 * pi,
                            color: const Color(0xFF3B82F6),
                            sweep: 2.0,
                            strokeWidth: 2.0,
                            opacity: 0.75,
                          ),
                        ),
                      ),

                      // Inner spinning arc (green, counter-clockwise)
                      AnimatedBuilder(
                        animation: _spinCtrl,
                        builder: (context, child) => CustomPaint(
                          size: const Size(134, 134),
                          painter: _ArcPainter(
                            angle: pi + _spinCtrl.value * 2 * pi * -0.65,
                            color: const Color(0xFF22C55E),
                            sweep: 1.3,
                            strokeWidth: 1.5,
                            opacity: 0.55,
                          ),
                        ),
                      ),

                      // Logo with pulsing glow
                      FadeTransition(
                        opacity: logoFade,
                        child: ScaleTransition(
                          scale: logoScale,
                          child: AnimatedBuilder(
                            animation: _pulseCtrl,
                            builder: (_, child) => Container(
                              width: 100,
                              height: 100,
                              decoration: BoxDecoration(
                                borderRadius: BorderRadius.circular(30),
                                boxShadow: [
                                  BoxShadow(
                                    color: const Color(0xFF3B82F6).withValues(
                                      alpha: 0.35 + _pulseCtrl.value * 0.45,
                                    ),
                                    blurRadius: 28 + _pulseCtrl.value * 24,
                                    spreadRadius: 2 + _pulseCtrl.value * 8,
                                  ),
                                ],
                              ),
                              child: child,
                            ),
                            child: ClipRRect(
                              borderRadius: BorderRadius.circular(30),
                              child: Image.asset(
                                'assets/images/logo.png',
                                width: 100,
                                height: 100,
                                fit: BoxFit.cover,
                              ),
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),

                const SizedBox(height: 40),

                // ── App name ──
                FadeTransition(
                  opacity: titleFade,
                  child: SlideTransition(
                    position: titleSlide,
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        ShaderMask(
                          shaderCallback: (bounds) => const LinearGradient(
                            colors: [Color(0xFFEEF2FF), Color(0xFF93C5FD)],
                          ).createShader(bounds),
                          child: const Text(
                            'Zenviq',
                            style: TextStyle(
                              color: Colors.white,
                              fontSize: 40,
                              fontWeight: FontWeight.w900,
                              letterSpacing: -1.4,
                              height: 1.0,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),

                const SizedBox(height: 14),

                // ── Tagline pill ──
                FadeTransition(
                  opacity: tagFade,
                  child: SlideTransition(
                    position: tagSlide,
                    child: Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 18, vertical: 8),
                      decoration: BoxDecoration(
                        color: const Color(0xFF3B82F6).withValues(alpha: 0.10),
                        borderRadius: BorderRadius.circular(30),
                        border: Border.all(
                          color: const Color(0xFF3B82F6).withValues(alpha: 0.35),
                        ),
                      ),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Container(
                            width: 6,
                            height: 6,
                            decoration: const BoxDecoration(
                              color: Color(0xFF22C55E),
                              shape: BoxShape.circle,
                            ),
                          ),
                          const SizedBox(width: 8),
                          const Text(
                            'Professional Trading Signals',
                            style: TextStyle(
                              color: Color(0xFF93C5FD),
                              fontSize: 13,
                              fontWeight: FontWeight.w500,
                              letterSpacing: 0.2,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),

          // ── Layer 3: bottom loading indicator ──
          Positioned(
            bottom: 52,
            left: 0,
            right: 0,
            child: FadeTransition(
              opacity: bottomFade,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  _BouncingDots(controller: _dotCtrl),
                  const SizedBox(height: 14),
                  const Text(
                    'Loading signals...',
                    style: TextStyle(
                      color: Color(0xFF475569),
                      fontSize: 12,
                      fontWeight: FontWeight.w500,
                      letterSpacing: 0.3,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────
// Background: subtle grid + radial glows
// ─────────────────────────────────────────────────────────────

class _Background extends StatelessWidget {
  const _Background();

  @override
  Widget build(BuildContext context) {
    return Stack(
      children: [
        // Subtle dot grid
        Positioned.fill(
          child: CustomPaint(painter: _DotGridPainter()),
        ),
        // Top-right blue glow
        Positioned(
          top: -140,
          right: -100,
          child: _RadialGlow(
            color: const Color(0xFF3B82F6),
            size: 420,
            opacity: 0.14,
          ),
        ),
        // Bottom-left green glow
        Positioned(
          bottom: -80,
          left: -80,
          child: _RadialGlow(
            color: const Color(0xFF22C55E),
            size: 300,
            opacity: 0.07,
          ),
        ),
        // Center subtle glow
        Positioned(
          top: MediaQuery.of(context).size.height * 0.3,
          left: MediaQuery.of(context).size.width * 0.2,
          child: _RadialGlow(
            color: const Color(0xFF6366F1),
            size: 200,
            opacity: 0.08,
          ),
        ),
      ],
    );
  }
}

class _RadialGlow extends StatelessWidget {
  final Color color;
  final double size;
  final double opacity;

  const _RadialGlow({required this.color, required this.size, required this.opacity});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        gradient: RadialGradient(
          colors: [color.withValues(alpha: opacity), Colors.transparent],
        ),
      ),
    );
  }
}

class _DotGridPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = const Color(0xFF1E293B).withValues(alpha: 0.45)
      ..strokeWidth = 1.0
      ..style = PaintingStyle.fill;

    const spacing = 36.0;
    const dotRadius = 0.8;

    for (double x = spacing; x < size.width; x += spacing) {
      for (double y = spacing; y < size.height; y += spacing) {
        canvas.drawCircle(Offset(x, y), dotRadius, paint);
      }
    }
  }

  @override
  bool shouldRepaint(_DotGridPainter old) => false;
}

// ─────────────────────────────────────────────────────────────
// Spinning arc ring (CustomPainter)
// ─────────────────────────────────────────────────────────────

class _ArcPainter extends CustomPainter {
  final double angle;
  final Color color;
  final double sweep;
  final double strokeWidth;
  final double opacity;

  const _ArcPainter({
    required this.angle,
    required this.color,
    this.sweep = 2.0,
    this.strokeWidth = 2.0,
    this.opacity = 1.0,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final radius = size.width / 2 - strokeWidth;

    // Main arc
    final paint = Paint()
      ..color = color.withValues(alpha: opacity)
      ..style = PaintingStyle.stroke
      ..strokeWidth = strokeWidth
      ..strokeCap = StrokeCap.round;

    canvas.drawArc(
      Rect.fromCircle(center: center, radius: radius),
      angle,
      sweep,
      false,
      paint,
    );

    // Fading tail
    paint.color = color.withValues(alpha: opacity * 0.2);
    canvas.drawArc(
      Rect.fromCircle(center: center, radius: radius),
      angle + sweep,
      sweep * 0.35,
      false,
      paint,
    );
  }

  @override
  bool shouldRepaint(_ArcPainter old) => old.angle != angle;
}

// ─────────────────────────────────────────────────────────────
// Three bouncing dots loading indicator
// ─────────────────────────────────────────────────────────────

class _BouncingDots extends StatelessWidget {
  final AnimationController controller;

  const _BouncingDots({required this.controller});

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: controller,
      builder: (context, child) {
        return Row(
          mainAxisSize: MainAxisSize.min,
          children: List.generate(3, (i) {
            // Stagger each dot by 0.22 of the cycle
            final offset = i * 0.22;
            final raw = (controller.value - offset) % 1.0;
            // Half-sine to get 0→1→0 within first half of cycle
            final t = raw < 0.5 ? raw * 2 : 0.0;
            final bounce = sin(t * pi);

            return Padding(
              padding: const EdgeInsets.symmetric(horizontal: 4),
              child: Transform.translate(
                offset: Offset(0, -bounce * 10),
                child: Container(
                  width: 8,
                  height: 8,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: Color.lerp(
                      const Color(0xFF1E293B),
                      const Color(0xFF3B82F6),
                      bounce,
                    ),
                    boxShadow: bounce > 0.3
                        ? [
                            BoxShadow(
                              color: const Color(0xFF3B82F6)
                                  .withValues(alpha: bounce * 0.6),
                              blurRadius: 8,
                              spreadRadius: 1,
                            )
                          ]
                        : null,
                  ),
                ),
              ),
            );
          }),
        );
      },
    );
  }
}
