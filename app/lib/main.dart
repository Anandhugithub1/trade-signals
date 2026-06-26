import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'theme/app_theme.dart';
import 'theme/app_colors.dart';
import 'screens/splash_screen.dart';
import 'screens/auth/login_screen.dart';
import 'screens/auth/register_screen.dart';
import 'screens/disclaimer_screen.dart';
import 'screens/home_screen.dart';
import 'screens/signals_screen.dart';
import 'screens/profile_screen.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  SystemChrome.setSystemUIOverlayStyle(const SystemUiOverlayStyle(
    statusBarColor: Colors.transparent,
    statusBarIconBrightness: Brightness.light,
  ));
  runApp(const TradePilotApp());
}

class TradePilotApp extends StatelessWidget {
  const TradePilotApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'TradePilot',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.light,
      darkTheme: AppTheme.dark,
      themeMode: ThemeMode.system,
      initialRoute: '/',
      routes: {
        '/': (_) => const SplashScreen(),
        '/disclaimer': (_) => const DisclaimerScreen(isOnboarding: true),
        '/disclaimer/info': (_) => const DisclaimerScreen(isOnboarding: false),
        '/login': (_) => const LoginScreen(),
        '/register': (_) => const RegisterScreen(),
        '/main': (_) => const MainShell(),
      },
    );
  }
}

class MainShell extends StatefulWidget {
  const MainShell({super.key});

  @override
  State<MainShell> createState() => _MainShellState();
}

class _MainShellState extends State<MainShell> {
  int _index = 0;

  static const _screens = [HomeScreen(), SignalsScreen(), ProfileScreen()];

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return Scaffold(
      backgroundColor: c.bg,
      body: IndexedStack(index: _index, children: _screens),
      bottomNavigationBar: Container(
        decoration: BoxDecoration(
          color: c.surface,
          border: Border(top: BorderSide(color: c.border, width: 0.5)),
        ),
        child: NavigationBar(
          selectedIndex: _index,
          onDestinationSelected: (i) {
            HapticFeedback.selectionClick();
            setState(() => _index = i);
          },
          backgroundColor: Colors.transparent,
          shadowColor: Colors.transparent,
          surfaceTintColor: Colors.transparent,
          indicatorColor: c.accent.withValues(alpha: 0.15),
          elevation: 0,
          height: 66,
          labelBehavior: NavigationDestinationLabelBehavior.alwaysShow,
          destinations: [
            NavigationDestination(
              icon: Icon(Icons.home_outlined, color: c.t3),
              selectedIcon: Icon(Icons.home_rounded, color: c.accent),
              label: 'Home',
            ),
            NavigationDestination(
              icon: Icon(Icons.bolt_outlined, color: c.t3),
              selectedIcon: Icon(Icons.bolt_rounded, color: c.accent),
              label: 'Signals',
            ),
            NavigationDestination(
              icon: Icon(Icons.person_outline_rounded, color: c.t3),
              selectedIcon: Icon(Icons.person_rounded, color: c.accent),
              label: 'Profile',
            ),
          ],
        ),
      ),
    );
  }
}
