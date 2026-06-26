import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'app_colors.dart';

class AppTheme {
  static ThemeData get dark => _build(
        brightness: Brightness.dark,
        colors: AppColors.dark,
        primary: const Color(0xFF3B82F6),
        surfaceColor: const Color(0xFF111827),
      );

  static ThemeData get light => _build(
        brightness: Brightness.light,
        colors: AppColors.light,
        primary: const Color(0xFF2563EB),
        surfaceColor: const Color(0xFFFFFFFF),
      );

  static ThemeData _build({
    required Brightness brightness,
    required AppColors colors,
    required Color primary,
    required Color surfaceColor,
  }) {
    final isLight = brightness == Brightness.light;
    final interBase = GoogleFonts.interTextTheme(
      ThemeData(brightness: brightness).textTheme,
    ).apply(bodyColor: colors.t1, displayColor: colors.t1);

    return ThemeData(
      brightness: brightness,
      useMaterial3: true,
      scaffoldBackgroundColor: colors.bg,
      extensions: [colors],
      fontFamily: GoogleFonts.inter().fontFamily,
      colorScheme: ColorScheme(
        brightness: brightness,
        primary: primary,
        onPrimary: Colors.white,
        secondary: primary,
        onSecondary: Colors.white,
        error: colors.short,
        onError: Colors.white,
        surface: surfaceColor,
        onSurface: colors.t1,
        // M3 tonal surface — same as surface to keep our custom bg
        surfaceContainerHighest: colors.card,
        outline: colors.border,
      ),
      textTheme: interBase,
      appBarTheme: AppBarTheme(
        backgroundColor: colors.bg,
        surfaceTintColor: Colors.transparent,
        scrolledUnderElevation: 0,
        elevation: 0,
        iconTheme: IconThemeData(color: colors.t1),
        titleTextStyle: GoogleFonts.inter(
          color: colors.t1,
          fontSize: 18,
          fontWeight: FontWeight.w800,
          letterSpacing: -0.3,
        ),
      ),
      cardTheme: CardThemeData(
        color: colors.card,
        elevation: isLight ? 2 : 0,
        shadowColor: Colors.black.withValues(alpha: 0.10),
        surfaceTintColor: Colors.transparent,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(16),
          side: BorderSide(color: colors.border),
        ),
        margin: EdgeInsets.zero,
      ),
      navigationBarTheme: NavigationBarThemeData(
        backgroundColor: colors.surface,
        surfaceTintColor: Colors.transparent,
        shadowColor: Colors.transparent,
        indicatorColor: primary.withValues(alpha: 0.13),
        labelTextStyle: WidgetStateProperty.resolveWith((states) {
          final selected = states.contains(WidgetState.selected);
          return GoogleFonts.inter(
            fontSize: 11,
            fontWeight: selected ? FontWeight.w700 : FontWeight.w500,
            color: selected ? primary : colors.t3,
          );
        }),
        iconTheme: WidgetStateProperty.resolveWith((states) {
          final selected = states.contains(WidgetState.selected);
          return IconThemeData(color: selected ? primary : colors.t3, size: 24);
        }),
        elevation: 0,
        height: 66,
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          elevation: 0,
          backgroundColor: primary,
          foregroundColor: Colors.white,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
          padding: const EdgeInsets.symmetric(vertical: 14),
          textStyle: GoogleFonts.inter(fontSize: 15, fontWeight: FontWeight.w700),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: colors.t2,
          side: BorderSide(color: colors.border),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
          padding: const EdgeInsets.symmetric(vertical: 14),
          textStyle: GoogleFonts.inter(fontSize: 15, fontWeight: FontWeight.w600),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: colors.card,
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide(color: colors.border),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide(color: colors.border),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide(color: primary, width: 1.5),
        ),
      ),
      dividerColor: colors.border,
      dividerTheme: DividerThemeData(color: colors.border, space: 1),
    );
  }
}
