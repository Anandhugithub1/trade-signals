import 'package:flutter/material.dart';
import '../theme/app_colors.dart';
import '../utils/app_error.dart';

/// Full-screen error state with optional retry button.
class ErrorView extends StatelessWidget {
  final Object error;
  final VoidCallback? onRetry;

  const ErrorView({super.key, required this.error, this.onRetry});

  @override
  Widget build(BuildContext context) {
    final c   = context.colors;
    final msg = friendlyError(error);
    final isNetwork = error is NetworkError ||
        msg.contains('connection') || msg.contains('internet');

    return Center(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 64,
              height: 64,
              decoration: BoxDecoration(
                color: c.short.withValues(alpha: 0.1),
                shape: BoxShape.circle,
              ),
              child: Icon(
                isNetwork
                    ? Icons.wifi_off_rounded
                    : Icons.error_outline_rounded,
                color: c.short,
                size: 30,
              ),
            ),
            const SizedBox(height: 16),
            Text(
              isNetwork ? 'No Connection' : 'Something went wrong',
              style: TextStyle(
                  color: c.t1, fontSize: 17, fontWeight: FontWeight.w700),
            ),
            const SizedBox(height: 6),
            Text(
              msg,
              textAlign: TextAlign.center,
              style: TextStyle(color: c.t2, fontSize: 13, height: 1.5),
            ),
            if (onRetry != null) ...[
              const SizedBox(height: 24),
              ElevatedButton.icon(
                onPressed: onRetry,
                style: ElevatedButton.styleFrom(
                  backgroundColor: c.accent,
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
                  shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(10)),
                  elevation: 0,
                ),
                icon: const Icon(Icons.refresh_rounded, size: 18),
                label: const Text('Retry',
                    style: TextStyle(fontWeight: FontWeight.w700)),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

/// Inline error banner (used inside cards/lists).
class ErrorBanner extends StatelessWidget {
  final Object error;
  final VoidCallback? onDismiss;

  const ErrorBanner({super.key, required this.error, this.onDismiss});

  @override
  Widget build(BuildContext context) {
    final c   = context.colors;
    final msg = friendlyError(error);
    return Container(
      margin: const EdgeInsets.symmetric(vertical: 6),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      decoration: BoxDecoration(
        color: c.short.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: c.short.withValues(alpha: 0.25)),
      ),
      child: Row(
        children: [
          Icon(Icons.warning_amber_rounded, color: c.short, size: 16),
          const SizedBox(width: 10),
          Expanded(
            child: Text(msg,
                style: TextStyle(color: c.short, fontSize: 13)),
          ),
          if (onDismiss != null)
            GestureDetector(
              onTap: onDismiss,
              child: Icon(Icons.close_rounded, color: c.short, size: 16),
            ),
        ],
      ),
    );
  }
}

/// Empty state widget.
class EmptyView extends StatelessWidget {
  final String title;
  final String subtitle;
  final IconData icon;
  final Widget? action;

  const EmptyView({
    super.key,
    required this.title,
    this.subtitle = '',
    this.icon = Icons.inbox_outlined,
    this.action,
  });

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return Center(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 64,
              height: 64,
              decoration: BoxDecoration(
                color: c.accentBg,
                shape: BoxShape.circle,
              ),
              child: Icon(icon, color: c.accent, size: 28),
            ),
            const SizedBox(height: 16),
            Text(title,
                style: TextStyle(
                    color: c.t1, fontSize: 16, fontWeight: FontWeight.w700)),
            if (subtitle.isNotEmpty) ...[
              const SizedBox(height: 6),
              Text(subtitle,
                  textAlign: TextAlign.center,
                  style: TextStyle(color: c.t2, fontSize: 13, height: 1.5)),
            ],
            if (action != null) ...[
              const SizedBox(height: 20),
              action!,
            ],
          ],
        ),
      ),
    );
  }
}

/// Shows a SnackBar error message using the global scaffold messenger.
void showErrorSnack(BuildContext context, Object error) {
  final c   = context.colors;
  final msg = friendlyError(error);
  ScaffoldMessenger.of(context).clearSnackBars();
  ScaffoldMessenger.of(context).showSnackBar(
    SnackBar(
      content: Row(
        children: [
          Icon(Icons.error_outline_rounded, color: Colors.white, size: 18),
          const SizedBox(width: 10),
          Expanded(
            child: Text(msg,
                style: const TextStyle(color: Colors.white, fontSize: 13)),
          ),
        ],
      ),
      backgroundColor: c.short,
      behavior: SnackBarBehavior.floating,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
      margin: const EdgeInsets.all(16),
      duration: const Duration(seconds: 4),
    ),
  );
}
