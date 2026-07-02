import 'package:flutter/material.dart';
import '../../theme/app_colors.dart';
import 'auth_widgets.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen>
    with SingleTickerProviderStateMixin {
  final _formKey = GlobalKey<FormState>();
  final _emailCtrl = TextEditingController();
  final _passCtrl = TextEditingController();

  bool _obscure = true;
  bool _rememberMe = false;
  bool _loading = false;

  late AnimationController _animCtrl;
  late Animation<double> _fadeAnim;
  late Animation<Offset> _slideAnim;

  @override
  void initState() {
    super.initState();
    _animCtrl = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 700),
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
    _emailCtrl.dispose();
    _passCtrl.dispose();
    super.dispose();
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

  Future<void> _submit() async {
    FocusScope.of(context).unfocus();
    if (!_formKey.currentState!.validate()) return;
    setState(() => _loading = true);
    await Future.delayed(const Duration(milliseconds: 1400));
    if (!mounted) return;
    setState(() => _loading = false);
    Navigator.of(context).pushReplacementNamed('/main');
  }

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final size = MediaQuery.of(context).size;

    return Scaffold(
      backgroundColor: c.bg,
      body: Stack(
        children: [
          // Decorative background blobs
          Positioned(
            top: -100,
            right: -80,
            child: AuthGlowBlob(color: c.accent, size: 280),
          ),
          Positioned(
            bottom: size.height * 0.15,
            left: -60,
            child: AuthGlowBlob(color: c.long, size: 200, opacity: 0.07),
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
                      const SizedBox(height: 32),
                      _buildLogo(c),
                      const SizedBox(height: 36),
                      _buildHeading(c),
                      const SizedBox(height: 32),
                      _buildForm(c),
                      const SizedBox(height: 24),
                      _buildLoginButton(c),
                      const SizedBox(height: 28),
                      _buildDivider(c),
                      const SizedBox(height: 20),
                      _buildSocialRow(c),
                      const SizedBox(height: 36),
                      _buildRegisterLink(c),
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

  Widget _buildLogo(AppColors c) {
    return Row(
      children: [
        Container(
          width: 44,
          height: 44,
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(13),
            boxShadow: [
              BoxShadow(
                color: c.accent.withValues(alpha: 0.35),
                blurRadius: 16,
                offset: const Offset(0, 6),
              ),
            ],
          ),
          child: ClipRRect(
            borderRadius: BorderRadius.circular(13),
            child: Image.asset('assets/images/logo.png', fit: BoxFit.cover),
          ),
        ),
        const SizedBox(width: 10),
        Text(
          'Zenviq',
          style: TextStyle(
            color: c.t1,
            fontSize: 20,
            fontWeight: FontWeight.w900,
            letterSpacing: -0.5,
          ),
        ),
      ],
    );
  }

  Widget _buildHeading(AppColors c) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Welcome back',
          style: TextStyle(
            color: c.t1,
            fontSize: 30,
            fontWeight: FontWeight.w900,
            letterSpacing: -0.8,
          ),
        ),
        const SizedBox(height: 6),
        Text(
          'Sign in to access your trading signals',
          style: TextStyle(color: c.t2, fontSize: 15),
        ),
      ],
    );
  }

  Widget _buildForm(AppColors c) {
    return Form(
      key: _formKey,
      child: Column(
        children: [
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
            obscureText: _obscure,
            textInputAction: TextInputAction.done,
            onFieldSubmitted: (_) => _submit(),
            style: TextStyle(color: c.t1, fontSize: 15),
            decoration: InputDecoration(
              hintText: '••••••••',
              hintStyle: TextStyle(color: c.t3),
              prefixIcon: Icon(Icons.lock_outline_rounded, color: c.t3, size: 20),
              suffixIcon: IconButton(
                icon: Icon(
                  _obscure ? Icons.visibility_off_outlined : Icons.visibility_outlined,
                  color: c.t3,
                  size: 20,
                ),
                onPressed: () => setState(() => _obscure = !_obscure),
              ),
            ),
          ),
          const SizedBox(height: 14),

          // Remember me + Forgot password
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              GestureDetector(
                onTap: () => setState(() => _rememberMe = !_rememberMe),
                behavior: HitTestBehavior.opaque,
                child: Row(
                  children: [
                    AnimatedContainer(
                      duration: const Duration(milliseconds: 160),
                      width: 20,
                      height: 20,
                      decoration: BoxDecoration(
                        color: _rememberMe ? c.accent : Colors.transparent,
                        borderRadius: BorderRadius.circular(5),
                        border: Border.all(
                          color: _rememberMe ? c.accent : c.t3,
                          width: 1.5,
                        ),
                      ),
                      child: _rememberMe
                          ? const Icon(Icons.check_rounded, color: Colors.white, size: 13)
                          : null,
                    ),
                    const SizedBox(width: 8),
                    Text('Remember me', style: TextStyle(color: c.t2, fontSize: 13)),
                  ],
                ),
              ),
              TextButton(
                onPressed: () {},
                style: TextButton.styleFrom(
                  padding: EdgeInsets.zero,
                  minimumSize: Size.zero,
                  tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                ),
                child: Text(
                  'Forgot password?',
                  style: TextStyle(color: c.accent, fontSize: 13, fontWeight: FontWeight.w600),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildLoginButton(AppColors c) {
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
                'Sign In',
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
          child: Text('or continue with', style: TextStyle(color: c.t3, fontSize: 12)),
        ),
        Expanded(child: Divider(color: c.border)),
      ],
    );
  }

  Widget _buildSocialRow(AppColors c) {
    return Row(
      children: [
        Expanded(
          child: AuthSocialButton(
            label: 'Google',
            icon: Icons.g_mobiledata_rounded,
            onTap: () {},
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: AuthSocialButton(
            label: 'Apple',
            icon: Icons.apple_rounded,
            onTap: () {},
          ),
        ),
      ],
    );
  }

  Widget _buildRegisterLink(AppColors c) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        Text("Don't have an account? ", style: TextStyle(color: c.t2, fontSize: 14)),
        GestureDetector(
          onTap: () => Navigator.of(context).pushNamed('/register'),
          child: Text(
            'Sign Up',
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

