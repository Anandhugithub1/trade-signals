import 'package:flutter/material.dart';
import '../../theme/app_colors.dart';
import 'auth_widgets.dart';

class RegisterScreen extends StatefulWidget {
  const RegisterScreen({super.key});

  @override
  State<RegisterScreen> createState() => _RegisterScreenState();
}

class _RegisterScreenState extends State<RegisterScreen>
    with SingleTickerProviderStateMixin {
  final _formKey = GlobalKey<FormState>();
  final _nameCtrl = TextEditingController();
  final _emailCtrl = TextEditingController();
  final _passCtrl = TextEditingController();
  final _confirmCtrl = TextEditingController();

  bool _obscurePass = true;
  bool _obscureConfirm = true;
  bool _acceptTerms = false;
  bool _loading = false;
  _PasswordStrength _strength = _PasswordStrength.empty;

  late AnimationController _animCtrl;
  late Animation<double> _fadeAnim;
  late Animation<Offset> _slideAnim;

  @override
  void initState() {
    super.initState();
    _animCtrl = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 600),
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
    _nameCtrl.dispose();
    _emailCtrl.dispose();
    _passCtrl.dispose();
    _confirmCtrl.dispose();
    super.dispose();
  }

  void _onPasswordChanged(String v) {
    setState(() {
      if (v.isEmpty) {
        _strength = _PasswordStrength.empty;
      } else if (v.length < 6) {
        _strength = _PasswordStrength.weak;
      } else if (v.length < 10 ||
          !RegExp(r'[A-Z]').hasMatch(v) ||
          !RegExp(r'[0-9]').hasMatch(v)) {
        _strength = _PasswordStrength.fair;
      } else if (RegExp(r'[!@#\$%^&*(),.?":{}|<>]').hasMatch(v)) {
        _strength = _PasswordStrength.strong;
      } else {
        _strength = _PasswordStrength.good;
      }
    });
  }

  String? _validateName(String? v) {
    if (v == null || v.trim().isEmpty) return 'Full name is required';
    if (v.trim().length < 2) return 'Name must be at least 2 characters';
    return null;
  }

  String? _validateEmail(String? v) {
    if (v == null || v.trim().isEmpty) return 'Email is required';
    final ok = RegExp(r'^[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}$').hasMatch(v.trim());
    return ok ? null : 'Enter a valid email address';
  }

  String? _validatePassword(String? v) {
    if (v == null || v.isEmpty) return 'Password is required';
    if (v.length < 6) return 'Password must be at least 6 characters';
    return null;
  }

  String? _validateConfirm(String? v) {
    if (v == null || v.isEmpty) return 'Please confirm your password';
    if (v != _passCtrl.text) return 'Passwords do not match';
    return null;
  }

  Future<void> _submit() async {
    FocusScope.of(context).unfocus();
    if (!_formKey.currentState!.validate()) return;
    if (!_acceptTerms) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: const Text('Please accept the terms and conditions'),
          behavior: SnackBarBehavior.floating,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
          margin: const EdgeInsets.all(16),
        ),
      );
      return;
    }
    setState(() => _loading = true);
    await Future.delayed(const Duration(milliseconds: 1600));
    if (!mounted) return;
    setState(() => _loading = false);
    Navigator.of(context).pushReplacementNamed('/main');
  }

  @override
  Widget build(BuildContext context) {
    final c = context.colors;

    return Scaffold(
      backgroundColor: c.bg,
      body: Stack(
        children: [
          Positioned(
            top: -60,
            left: -80,
            child: AuthGlowBlob(color: c.long, size: 260, opacity: 0.09),
          ),
          Positioned(
            bottom: -60,
            right: -60,
            child: AuthGlowBlob(color: c.accent, size: 220),
          ),
          SafeArea(
            child: FadeTransition(
              opacity: _fadeAnim,
              child: SlideTransition(
                position: _slideAnim,
                child: SingleChildScrollView(
                  padding: const EdgeInsets.symmetric(horizontal: 24),
                  physics: const BouncingScrollPhysics(),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const SizedBox(height: 16),
                      _buildTopBar(c),
                      const SizedBox(height: 28),
                      _buildHeading(c),
                      const SizedBox(height: 28),
                      _buildForm(c),
                      const SizedBox(height: 20),
                      _buildTermsRow(c),
                      const SizedBox(height: 24),
                      _buildRegisterButton(c),
                      const SizedBox(height: 28),
                      _buildDivider(c),
                      const SizedBox(height: 20),
                      _buildSocialRow(c),
                      const SizedBox(height: 32),
                      _buildLoginLink(c),
                      const SizedBox(height: 24),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildTopBar(AppColors c) {
    return Row(
      children: [
        GestureDetector(
          onTap: () => Navigator.of(context).pop(),
          child: Container(
            width: 40,
            height: 40,
            decoration: BoxDecoration(
              color: c.card,
              borderRadius: BorderRadius.circular(11),
              border: Border.all(color: c.border),
            ),
            child: Icon(Icons.arrow_back_ios_new_rounded, color: c.t1, size: 16),
          ),
        ),
        const SizedBox(width: 14),
        Text(
          'Back',
          style: TextStyle(color: c.t2, fontSize: 15, fontWeight: FontWeight.w500),
        ),
      ],
    );
  }

  Widget _buildHeading(AppColors c) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Create account',
          style: TextStyle(
            color: c.t1,
            fontSize: 30,
            fontWeight: FontWeight.w900,
            letterSpacing: -0.8,
          ),
        ),
        const SizedBox(height: 6),
        Text(
          'Join thousands of traders using TradePilot',
          style: TextStyle(color: c.t2, fontSize: 15),
        ),
      ],
    );
  }

  Widget _buildForm(AppColors c) {
    return Form(
      key: _formKey,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Full name
          const AuthFieldLabel(label: 'Full name'),
          const SizedBox(height: 6),
          TextFormField(
            controller: _nameCtrl,
            validator: _validateName,
            keyboardType: TextInputType.name,
            textInputAction: TextInputAction.next,
            textCapitalization: TextCapitalization.words,
            style: TextStyle(color: c.t1, fontSize: 15),
            decoration: InputDecoration(
              hintText: 'Alex Johnson',
              hintStyle: TextStyle(color: c.t3),
              prefixIcon: Icon(Icons.person_outline_rounded, color: c.t3, size: 20),
            ),
          ),
          const SizedBox(height: 18),

          // Email
          const AuthFieldLabel(label: 'Email address'),
          const SizedBox(height: 6),
          TextFormField(
            controller: _emailCtrl,
            validator: _validateEmail,
            keyboardType: TextInputType.emailAddress,
            textInputAction: TextInputAction.next,
            style: TextStyle(color: c.t1, fontSize: 15),
            decoration: InputDecoration(
              hintText: 'you@example.com',
              hintStyle: TextStyle(color: c.t3),
              prefixIcon: Icon(Icons.mail_outline_rounded, color: c.t3, size: 20),
            ),
          ),
          const SizedBox(height: 18),

          // Password
          const AuthFieldLabel(label: 'Password'),
          const SizedBox(height: 6),
          TextFormField(
            controller: _passCtrl,
            validator: _validatePassword,
            obscureText: _obscurePass,
            textInputAction: TextInputAction.next,
            onChanged: _onPasswordChanged,
            style: TextStyle(color: c.t1, fontSize: 15),
            decoration: InputDecoration(
              hintText: '••••••••',
              hintStyle: TextStyle(color: c.t3),
              prefixIcon: Icon(Icons.lock_outline_rounded, color: c.t3, size: 20),
              suffixIcon: IconButton(
                icon: Icon(
                  _obscurePass ? Icons.visibility_off_outlined : Icons.visibility_outlined,
                  color: c.t3,
                  size: 20,
                ),
                onPressed: () => setState(() => _obscurePass = !_obscurePass),
              ),
            ),
          ),
          if (_strength != _PasswordStrength.empty) ...[
            const SizedBox(height: 8),
            _PasswordStrengthBar(strength: _strength, c: c),
          ],
          const SizedBox(height: 18),

          // Confirm password
          const AuthFieldLabel(label: 'Confirm password'),
          const SizedBox(height: 6),
          TextFormField(
            controller: _confirmCtrl,
            validator: _validateConfirm,
            obscureText: _obscureConfirm,
            textInputAction: TextInputAction.done,
            onFieldSubmitted: (_) => _submit(),
            style: TextStyle(color: c.t1, fontSize: 15),
            decoration: InputDecoration(
              hintText: '••••••••',
              hintStyle: TextStyle(color: c.t3),
              prefixIcon: Icon(Icons.lock_outline_rounded, color: c.t3, size: 20),
              suffixIcon: IconButton(
                icon: Icon(
                  _obscureConfirm ? Icons.visibility_off_outlined : Icons.visibility_outlined,
                  color: c.t3,
                  size: 20,
                ),
                onPressed: () => setState(() => _obscureConfirm = !_obscureConfirm),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildTermsRow(AppColors c) {
    return GestureDetector(
      onTap: () => setState(() => _acceptTerms = !_acceptTerms),
      behavior: HitTestBehavior.opaque,
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          AnimatedContainer(
            duration: const Duration(milliseconds: 160),
            width: 20,
            height: 20,
            margin: const EdgeInsets.only(top: 1),
            decoration: BoxDecoration(
              color: _acceptTerms ? c.accent : Colors.transparent,
              borderRadius: BorderRadius.circular(5),
              border: Border.all(
                color: _acceptTerms ? c.accent : c.t3,
                width: 1.5,
              ),
            ),
            child: _acceptTerms
                ? const Icon(Icons.check_rounded, color: Colors.white, size: 13)
                : null,
          ),
          const SizedBox(width: 10),
          Expanded(
            child: RichText(
              text: TextSpan(
                style: TextStyle(color: c.t2, fontSize: 13, height: 1.5),
                children: [
                  const TextSpan(text: 'I agree to the '),
                  TextSpan(
                    text: 'Terms of Service',
                    style: TextStyle(color: c.accent, fontWeight: FontWeight.w600),
                  ),
                  const TextSpan(text: ' and '),
                  TextSpan(
                    text: 'Privacy Policy',
                    style: TextStyle(color: c.accent, fontWeight: FontWeight.w600),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildRegisterButton(AppColors c) {
    return SizedBox(
      width: double.infinity,
      height: 52,
      child: ElevatedButton(
        onPressed: _loading ? null : _submit,
        style: ElevatedButton.styleFrom(
          backgroundColor: c.accent,
          disabledBackgroundColor: c.accent.withValues(alpha: 0.6),
          foregroundColor: Colors.white,
          elevation: 0,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
        ),
        child: _loading
            ? const SizedBox(
                width: 22,
                height: 22,
                child: CircularProgressIndicator(
                  color: Colors.white,
                  strokeWidth: 2.5,
                ),
              )
            : const Text(
                'Create Account',
                style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
              ),
      ),
    );
  }

  Widget _buildDivider(AppColors c) {
    return Row(
      children: [
        Expanded(child: Divider(color: c.border)),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 14),
          child: Text('or sign up with', style: TextStyle(color: c.t3, fontSize: 12)),
        ),
        Expanded(child: Divider(color: c.border)),
      ],
    );
  }

  Widget _buildSocialRow(AppColors c) {
    return Row(
      children: [
        Expanded(
          child: AuthSocialButton(label: 'Google', icon: Icons.g_mobiledata_rounded, onTap: () {}),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: AuthSocialButton(label: 'Apple', icon: Icons.apple_rounded, onTap: () {}),
        ),
      ],
    );
  }

  Widget _buildLoginLink(AppColors c) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        Text('Already have an account? ', style: TextStyle(color: c.t2, fontSize: 14)),
        GestureDetector(
          onTap: () => Navigator.of(context).pop(),
          child: Text(
            'Sign In',
            style: TextStyle(
              color: c.accent,
              fontSize: 14,
              fontWeight: FontWeight.w700,
            ),
          ),
        ),
      ],
    );
  }
}

// ─────────────────────────────────────────────────────
// Password strength bar
// ─────────────────────────────────────────────────────

enum _PasswordStrength { empty, weak, fair, good, strong }

class _PasswordStrengthBar extends StatelessWidget {
  final _PasswordStrength strength;
  final AppColors c;

  const _PasswordStrengthBar({required this.strength, required this.c});

  @override
  Widget build(BuildContext context) {
    final (filled, color, label) = switch (strength) {
      _PasswordStrength.weak   => (1, c.short, 'Weak'),
      _PasswordStrength.fair   => (2, c.gold, 'Fair'),
      _PasswordStrength.good   => (3, const Color(0xFF22C55E), 'Good'),
      _PasswordStrength.strong => (4, const Color(0xFF16A34A), 'Strong'),
      _PasswordStrength.empty  => (0, c.border, ''),
    };

    return Row(
      children: [
        Expanded(
          child: Row(
            children: List.generate(4, (i) {
              return Expanded(
                child: Container(
                  height: 3,
                  margin: EdgeInsets.only(right: i < 3 ? 4 : 0),
                  decoration: BoxDecoration(
                    color: i < filled ? color : c.border,
                    borderRadius: BorderRadius.circular(2),
                  ),
                ),
              );
            }),
          ),
        ),
        const SizedBox(width: 10),
        Text(
          label,
          style: TextStyle(
            color: color,
            fontSize: 12,
            fontWeight: FontWeight.w600,
          ),
        ),
      ],
    );
  }
}
