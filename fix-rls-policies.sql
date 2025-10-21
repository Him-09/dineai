-- Fix RLS Policies for Authentication Tables
-- Run this in your Supabase SQL Editor to fix the authentication issues

-- First, let's completely disable RLS on auth tables for testing
-- We'll re-enable with proper policies after

-- Disable RLS temporarily to allow authentication to work
ALTER TABLE client_accounts DISABLE ROW LEVEL SECURITY;
ALTER TABLE auth_sessions DISABLE ROW LEVEL SECURITY;
ALTER TABLE auth_attempts DISABLE ROW LEVEL SECURITY;

-- Drop all existing policies first
DROP POLICY IF EXISTS "Clients can view their own account" ON client_accounts;
DROP POLICY IF EXISTS "Users can view their own sessions" ON auth_sessions;
DROP POLICY IF EXISTS "Allow public read for authentication" ON client_accounts;
DROP POLICY IF EXISTS "Allow public insert for new sessions" ON auth_sessions;
DROP POLICY IF EXISTS "Users can read their own sessions" ON auth_sessions;
DROP POLICY IF EXISTS "Users can update their own sessions" ON auth_sessions;
DROP POLICY IF EXISTS "Allow public insert for auth attempts" ON auth_attempts;
DROP POLICY IF EXISTS "Clients can update their own account" ON client_accounts;
DROP POLICY IF EXISTS "Only admins can access admin_users" ON admin_users;

-- Re-enable RLS with simple, working policies
ALTER TABLE client_accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE auth_sessions ENABLE ROW LEVEL SECURITY;

-- Keep auth_attempts without RLS (it's just for logging)
-- ALTER TABLE auth_attempts ENABLE ROW LEVEL SECURITY;

-- Create simple, permissive policies for authentication

-- 1. Allow anyone to read client_accounts (needed for login)
CREATE POLICY "Public read access" ON client_accounts
    FOR SELECT USING (true);

-- 2. Allow anyone to insert into auth_sessions (needed for login)
CREATE POLICY "Public insert access" ON auth_sessions
    FOR INSERT WITH CHECK (true);

-- 3. Allow anyone to read auth_sessions (we'll filter in the app)
CREATE POLICY "Public read access" ON auth_sessions
    FOR SELECT USING (true);

-- 4. Allow anyone to update auth_sessions (we'll filter in the app)
CREATE POLICY "Public update access" ON auth_sessions
    FOR UPDATE USING (true);

-- 5. Keep admin_users completely locked down
ALTER TABLE admin_users ENABLE ROW LEVEL SECURITY;
CREATE POLICY "No access to admin_users" ON admin_users
    FOR ALL USING (false);

-- Grant necessary permissions to anon and authenticated roles
GRANT USAGE ON SCHEMA public TO anon, authenticated;
GRANT SELECT ON client_accounts TO anon, authenticated;
GRANT INSERT, SELECT, UPDATE ON auth_sessions TO anon, authenticated;
GRANT INSERT ON auth_attempts TO anon, authenticated;

-- Grant sequence usage (needed for auto-incrementing IDs)
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO anon, authenticated;

-- Refresh the schema cache
NOTIFY pgrst, 'reload schema';