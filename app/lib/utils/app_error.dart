/// Typed error hierarchy for the app.
/// All errors extend [AppError] so callers can catch the base
/// or specific subtypes depending on what they need to show.
class AppError implements Exception {
  final String message;
  final String? code;
  const AppError(this.message, {this.code});

  @override
  String toString() => message;
}

/// No internet / DNS failure / socket timeout.
class NetworkError extends AppError {
  const NetworkError()
      : super('No internet connection. Check your network and try again.');
}

/// Supabase / API returned a non-2xx response.
class ServerError extends AppError {
  const ServerError(super.message, {super.code});
}

/// JWT expired or user is not authenticated.
class AuthError extends AppError {
  const AuthError() : super('Session expired. Please restart the app.');
}

/// Response arrived but couldn't be parsed into the expected model.
class DataError extends AppError {
  const DataError(super.message);
}

/// Returns a short user-friendly label for any error.
String friendlyError(Object e) {
  if (e is NetworkError) return 'No connection — check your internet.';
  if (e is AuthError)    return 'Session expired — restart the app.';
  if (e is ServerError)  return 'Server error — please try again.';
  if (e is DataError)    return 'Unexpected data received.';
  if (e is AppError)     return e.message;
  final s = e.toString().toLowerCase();
  if (s.contains('socket') || s.contains('network') || s.contains('host lookup')) {
    return 'No connection — check your internet.';
  }
  return 'Something went wrong. Try again.';
}
