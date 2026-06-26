import 'package:flutter/material.dart';
import '../theme/app_colors.dart';

class DisclaimerBanner extends StatelessWidget {
  const DisclaimerBanner({super.key});

  static const _amber = Color(0xFFF59E0B);
  static const _amberBg = Color(0xFF2A1F0A);

  @override
  Widget build(BuildContext context) {
    final c = context.colors;

    return Container(
      decoration: BoxDecoration(
        color: _amberBg,
        borderRadius: BorderRadius.circular(13),
        border: Border.all(color: _amber.withValues(alpha: 0.35)),
      ),
      child: IntrinsicHeight(
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // Left accent bar
            Container(
              width: 4,
              decoration: const BoxDecoration(
                color: _amber,
                borderRadius: BorderRadius.only(
                  topLeft: Radius.circular(13),
                  bottomLeft: Radius.circular(13),
                ),
              ),
            ),
            // Content
            Expanded(
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 11),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Padding(
                      padding: EdgeInsets.only(top: 1),
                      child: Icon(
                        Icons.warning_amber_rounded,
                        color: _amber,
                        size: 16,
                      ),
                    ),
                    const SizedBox(width: 9),
                    Expanded(
                      child: Text(
                        'Crypto is highly volatile. Never risk more than 2–3% of capital per trade. Signals are not financial advice.',
                        style: TextStyle(
                          color: c.t2,
                          fontSize: 12,
                          height: 1.5,
                        ),
                      ),
                    ),
                    const SizedBox(width: 8),
                    GestureDetector(
                      onTap: () => Navigator.of(context).pushNamed('/disclaimer/info'),
                      child: const Padding(
                        padding: EdgeInsets.only(top: 1),
                        child: Text(
                          'Read more',
                          style: TextStyle(
                            color: _amber,
                            fontSize: 12,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
