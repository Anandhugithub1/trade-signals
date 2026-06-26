import 'package:flutter/material.dart';

@immutable
class AppColors extends ThemeExtension<AppColors> {
  const AppColors({
    required this.bg,
    required this.surface,
    required this.card,
    required this.border,
    required this.long,
    required this.longBg,
    required this.short,
    required this.shortBg,
    required this.accent,
    required this.accentBg,
    required this.gold,
    required this.goldBg,
    required this.t1,
    required this.t2,
    required this.t3,
  });

  final Color bg;
  final Color surface;
  final Color card;
  final Color border;
  final Color long;
  final Color longBg;
  final Color short;
  final Color shortBg;
  final Color accent;
  final Color accentBg;
  final Color gold;
  final Color goldBg;
  final Color t1;
  final Color t2;
  final Color t3;

  // Dark theme — familiar to crypto traders (Binance/Bybit style)
  static const dark = AppColors(
    bg: Color(0xFF0A0F1A),
    surface: Color(0xFF111827),
    card: Color(0xFF162032),
    border: Color(0xFF243047),
    long: Color(0xFF22C55E),
    longBg: Color(0xFF0F2A1A),
    short: Color(0xFFEF4444),
    shortBg: Color(0xFF2A0F0F),
    accent: Color(0xFF3B82F6),
    accentBg: Color(0xFF0F1F3D),
    gold: Color(0xFFF59E0B),
    goldBg: Color(0xFF2A1F0A),
    t1: Color(0xFFEEF2FF),
    t2: Color(0xFF94A3B8),
    t3: Color(0xFF64748B),
  );

  // Light theme — Coinbase / Robinhood style for day traders
  static const light = AppColors(
    bg: Color(0xFFF5F7FA),
    surface: Color(0xFFFFFFFF),
    card: Color(0xFFFFFFFF),
    border: Color(0xFFE2E8F0),
    long: Color(0xFF16A34A),
    longBg: Color(0xFFF0FDF4),
    short: Color(0xFFDC2626),
    shortBg: Color(0xFFFEF2F2),
    accent: Color(0xFF2563EB),
    accentBg: Color(0xFFEFF6FF),
    gold: Color(0xFFB45309),
    goldBg: Color(0xFFFFFBEB),
    t1: Color(0xFF0F172A),
    t2: Color(0xFF475569),
    t3: Color(0xFF94A3B8),
  );

  @override
  AppColors copyWith({
    Color? bg, Color? surface, Color? card, Color? border,
    Color? long, Color? longBg, Color? short, Color? shortBg,
    Color? accent, Color? accentBg, Color? gold, Color? goldBg,
    Color? t1, Color? t2, Color? t3,
  }) {
    return AppColors(
      bg: bg ?? this.bg, surface: surface ?? this.surface,
      card: card ?? this.card, border: border ?? this.border,
      long: long ?? this.long, longBg: longBg ?? this.longBg,
      short: short ?? this.short, shortBg: shortBg ?? this.shortBg,
      accent: accent ?? this.accent, accentBg: accentBg ?? this.accentBg,
      gold: gold ?? this.gold, goldBg: goldBg ?? this.goldBg,
      t1: t1 ?? this.t1, t2: t2 ?? this.t2, t3: t3 ?? this.t3,
    );
  }

  @override
  AppColors lerp(AppColors? other, double t) {
    if (other is! AppColors) return this;
    return AppColors(
      bg: Color.lerp(bg, other.bg, t)!,
      surface: Color.lerp(surface, other.surface, t)!,
      card: Color.lerp(card, other.card, t)!,
      border: Color.lerp(border, other.border, t)!,
      long: Color.lerp(long, other.long, t)!,
      longBg: Color.lerp(longBg, other.longBg, t)!,
      short: Color.lerp(short, other.short, t)!,
      shortBg: Color.lerp(shortBg, other.shortBg, t)!,
      accent: Color.lerp(accent, other.accent, t)!,
      accentBg: Color.lerp(accentBg, other.accentBg, t)!,
      gold: Color.lerp(gold, other.gold, t)!,
      goldBg: Color.lerp(goldBg, other.goldBg, t)!,
      t1: Color.lerp(t1, other.t1, t)!,
      t2: Color.lerp(t2, other.t2, t)!,
      t3: Color.lerp(t3, other.t3, t)!,
    );
  }
}

// Shorthand — context.colors.bg, context.colors.long, etc.
extension AppColorsX on BuildContext {
  AppColors get colors => Theme.of(this).extension<AppColors>()!;
}
