class SupabaseConfig {
  // Must match the project the anonKey below was issued for (its JWT "ref"
  // claim). A placeholder here fails DNS on-device, which surfaces as
  // "No connection — check your internet" and looks like a network fault.
  static const url = 'https://ndukwedjdqonulhwajmu.supabase.co';

  // Anon key — safe to embed in mobile (Row Level Security enforces access).
  // Never use the service_role key here.
  static const anonKey =
      'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9'
      '.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im5kdWt3ZWRqZHFvbnVsaHdham11Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODI0Nzk1ODQsImV4cCI6MjA5ODA1NTU4NH0'
      '.4rZobUQKdPpfpPYNNvyc_OeCEZ3ZB1_FL_UCKzgXN7g';
}
