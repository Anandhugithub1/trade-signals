import 'package:flutter/material.dart';
import '../../theme/app_colors.dart';

class AuthGlowBlob extends StatelessWidget {
  final Color color;
  final double size;
  final double opacity;

  const AuthGlowBlob({super.key, required this.color, required this.size, this.opacity = 0.12});

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

class AuthFieldLabel extends StatelessWidget {
  final String label;

  const AuthFieldLabel({super.key, required this.label});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return Text(
      label,
      style: TextStyle(color: c.t2, fontSize: 13, fontWeight: FontWeight.w600),
    );
  }
}

class AuthSocialButton extends StatelessWidget {
  final String label;
  final IconData icon;
  final VoidCallback onTap;

  const AuthSocialButton({
    super.key,
    required this.label,
    required this.icon,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return Material(
      color: c.card,
      borderRadius: BorderRadius.circular(12),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(12),
        child: Container(
          height: 48,
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: c.border),
          ),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(icon, color: c.t1, size: 22),
              const SizedBox(width: 8),
              Text(
                label,
                style: TextStyle(color: c.t1, fontSize: 14, fontWeight: FontWeight.w600),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
