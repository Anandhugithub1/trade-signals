import 'package:flutter/material.dart';
import '../theme/app_colors.dart';

class DisclaimerScreen extends StatefulWidget {
  /// [isOnboarding] true → shows Accept & Continue button (first launch flow)
  /// false → shows as a normal page with a back button (from Profile)
  final bool isOnboarding;

  const DisclaimerScreen({super.key, this.isOnboarding = false});

  @override
  State<DisclaimerScreen> createState() => _DisclaimerScreenState();
}

class _DisclaimerScreenState extends State<DisclaimerScreen>
    with SingleTickerProviderStateMixin {
  bool _accepted = false;

  late AnimationController _animCtrl;
  late Animation<double> _fadeAnim;
  late Animation<Offset> _slideAnim;

  @override
  void initState() {
    super.initState();
    _animCtrl = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 500),
    );
    _fadeAnim = CurvedAnimation(parent: _animCtrl, curve: Curves.easeOut);
    _slideAnim = Tween<Offset>(
      begin: const Offset(0, 0.06),
      end: Offset.zero,
    ).animate(CurvedAnimation(parent: _animCtrl, curve: Curves.easeOut));
    _animCtrl.forward();
  }

  @override
  void dispose() {
    _animCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final c = context.colors;

    return Scaffold(
      backgroundColor: c.bg,
      appBar: widget.isOnboarding
          ? null
          : AppBar(
              backgroundColor: c.bg,
              elevation: 0,
              leading: IconButton(
                icon: Icon(Icons.arrow_back_ios_new_rounded, color: c.t1, size: 18),
                onPressed: () => Navigator.pop(context),
              ),
              title: Text(
                'Disclaimer',
                style: TextStyle(color: c.t1, fontWeight: FontWeight.w800, fontSize: 18),
              ),
            ),
      body: FadeTransition(
        opacity: _fadeAnim,
        child: SlideTransition(
          position: _slideAnim,
          child: Column(
            children: [
              Expanded(
                child: ListView(
                  padding: const EdgeInsets.fromLTRB(20, 24, 20, 0),
                  physics: const BouncingScrollPhysics(),
                  children: [
                    _buildHeader(c),
                    const SizedBox(height: 24),
                    _buildWarningCard(
                      c: c,
                      icon: Icons.pie_chart_outline_rounded,
                      iconColor: const Color(0xFFF59E0B),
                      iconBg: const Color(0xFF2A1F0A),
                      title: 'Risk No More Than 3% Per Trade',
                      body:
                          'Never allocate more than 2–3% of your total trading capital to a single position. This protects your account from catastrophic loss if a trade goes against you, and keeps you in the game long-term.',
                    ),
                    const SizedBox(height: 12),
                    _buildWarningCard(
                      c: c,
                      icon: Icons.trending_down_rounded,
                      iconColor: const Color(0xFFEF4444),
                      iconBg: const Color(0xFF2A0F0F),
                      title: 'Signals Are Not a Get-Rich Scheme',
                      body:
                          'These signals are analytical tools — not guarantees. No signal service, algorithm, or analyst can consistently predict market direction. Past win rates do not guarantee future results. Treat every signal critically.',
                    ),
                    const SizedBox(height: 12),
                    _buildWarningCard(
                      c: c,
                      icon: Icons.waves_rounded,
                      iconColor: const Color(0xFF3B82F6),
                      iconBg: const Color(0xFF0F1F3D),
                      title: 'Crypto Is Extremely Volatile',
                      body:
                          'Cryptocurrency markets can move 10–50% in hours without warning. Flash crashes, whale manipulation, exchange halts, and extreme spreads are common. Prices you see may not reflect the price you actually fill at.',
                    ),
                    const SizedBox(height: 12),
                    _buildWarningCard(
                      c: c,
                      icon: Icons.water_drop_outlined,
                      iconColor: const Color(0xFF8B5CF6),
                      iconBg: const Color(0xFF1A0F2E),
                      title: 'Liquidity & Market Risks',
                      body:
                          'Low-cap tokens and altcoins can have extremely thin order books. You may be unable to exit a position at your desired price, resulting in significant slippage. Always check liquidity before entering a trade.',
                    ),
                    const SizedBox(height: 12),
                    _buildWarningCard(
                      c: c,
                      icon: Icons.account_balance_wallet_outlined,
                      iconColor: const Color(0xFF22C55E),
                      iconBg: const Color(0xFF0F2A1A),
                      title: 'Only Invest What You Can Afford to Lose',
                      body:
                          'Never trade with money earmarked for rent, food, healthcare, or emergency funds. The crypto market has wiped out portfolios overnight. Your financial wellbeing must always come before any trade.',
                    ),
                    const SizedBox(height: 12),
                    _buildWarningCard(
                      c: c,
                      icon: Icons.gavel_rounded,
                      iconColor: const Color(0xFF94A3B8),
                      iconBg: const Color(0xFF1E2A3D),
                      title: 'Not Financial or Legal Advice',
                      body:
                          'Zenviq signals are provided for informational and educational purposes only. They do not constitute financial, investment, legal, or tax advice. Always consult a qualified financial advisor before making investment decisions.',
                    ),
                    const SizedBox(height: 28),
                    _buildResponsibilityBanner(c),
                    const SizedBox(height: 28),
                    if (widget.isOnboarding) ...[
                      _buildAcceptRow(c),
                      const SizedBox(height: 16),
                    ],
                  ],
                ),
              ),
              if (widget.isOnboarding) _buildBottomBar(c),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildHeader(AppColors c) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Container(
          width: 56,
          height: 56,
          decoration: BoxDecoration(
            color: const Color(0xFFF59E0B).withValues(alpha: 0.12),
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: const Color(0xFFF59E0B).withValues(alpha: 0.3)),
          ),
          child: const Icon(
            Icons.warning_amber_rounded,
            color: Color(0xFFF59E0B),
            size: 28,
          ),
        ),
        const SizedBox(height: 16),
        Text(
          'Risk Disclaimer',
          style: TextStyle(
            color: c.t1,
            fontSize: 28,
            fontWeight: FontWeight.w900,
            letterSpacing: -0.7,
          ),
        ),
        const SizedBox(height: 8),
        Text(
          'Please read carefully before using Zenviq signals. Trading involves substantial risk of loss.',
          style: TextStyle(color: c.t2, fontSize: 14, height: 1.5),
        ),
      ],
    );
  }

  Widget _buildWarningCard({
    required AppColors c,
    required IconData icon,
    required Color iconColor,
    required Color iconBg,
    required String title,
    required String body,
  }) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: c.card,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: c.border),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 42,
            height: 42,
            decoration: BoxDecoration(
              color: iconBg,
              borderRadius: BorderRadius.circular(11),
              border: Border.all(color: iconColor.withValues(alpha: 0.25)),
            ),
            child: Icon(icon, color: iconColor, size: 20),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: TextStyle(
                    color: c.t1,
                    fontSize: 14,
                    fontWeight: FontWeight.w700,
                    height: 1.3,
                  ),
                ),
                const SizedBox(height: 6),
                Text(
                  body,
                  style: TextStyle(
                    color: c.t2,
                    fontSize: 13,
                    height: 1.55,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildResponsibilityBanner(AppColors c) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            const Color(0xFFF59E0B).withValues(alpha: 0.12),
            const Color(0xFFEF4444).withValues(alpha: 0.08),
          ],
        ),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: const Color(0xFFF59E0B).withValues(alpha: 0.35)),
      ),
      child: Column(
        children: [
          const Text(
            '⚠️',
            style: TextStyle(fontSize: 30),
          ),
          const SizedBox(height: 10),
          const Text(
            'Trade Responsibly',
            style: TextStyle(
              color: Color(0xFFF59E0B),
              fontSize: 18,
              fontWeight: FontWeight.w900,
              letterSpacing: -0.3,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            'The market will always be here tomorrow. Protect your capital first, profits second. No trade is worth your financial security.',
            textAlign: TextAlign.center,
            style: TextStyle(
              color: c.t2,
              fontSize: 13,
              height: 1.6,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildAcceptRow(AppColors c) {
    return GestureDetector(
      onTap: () => setState(() => _accepted = !_accepted),
      behavior: HitTestBehavior.opaque,
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          AnimatedContainer(
            duration: const Duration(milliseconds: 180),
            width: 22,
            height: 22,
            margin: const EdgeInsets.only(top: 1),
            decoration: BoxDecoration(
              color: _accepted ? const Color(0xFFF59E0B) : Colors.transparent,
              borderRadius: BorderRadius.circular(6),
              border: Border.all(
                color: _accepted ? const Color(0xFFF59E0B) : c.t3,
                width: 1.5,
              ),
            ),
            child: _accepted
                ? const Icon(Icons.check_rounded, color: Colors.white, size: 14)
                : null,
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              'I have read and understood the risks involved in cryptocurrency trading and agree to trade responsibly.',
              style: TextStyle(color: c.t2, fontSize: 13, height: 1.5),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildBottomBar(AppColors c) {
    final enabled = _accepted;
    return Container(
      padding: EdgeInsets.fromLTRB(
        20,
        12,
        20,
        12 + MediaQuery.of(context).padding.bottom,
      ),
      decoration: BoxDecoration(
        color: c.surface,
        border: Border(top: BorderSide(color: c.border, width: 0.5)),
      ),
      child: SizedBox(
        width: double.infinity,
        height: 52,
        child: ElevatedButton(
          onPressed: enabled
              ? () => Navigator.of(context).pushReplacementNamed('/main')
              : null,
          style: ElevatedButton.styleFrom(
            backgroundColor: const Color(0xFFF59E0B),
            disabledBackgroundColor: c.card,
            foregroundColor: Colors.white,
            disabledForegroundColor: c.t3,
            elevation: 0,
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
          ),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(
                Icons.shield_outlined,
                size: 18,
                color: enabled ? Colors.white : c.t3,
              ),
              const SizedBox(width: 8),
              Text(
                'I Understand — Trade Responsibly',
                style: TextStyle(
                  fontSize: 15,
                  fontWeight: FontWeight.w700,
                  color: enabled ? Colors.white : c.t3,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
