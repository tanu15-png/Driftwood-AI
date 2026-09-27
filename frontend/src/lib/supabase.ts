import { createClient } from '@supabase/supabase-js'

import { env } from '@/lib/env'

/**
 * Browser Supabase client for auth. Anon key only — the service-role key
 * never reaches the frontend; all privileged work happens in the backend.
 */
export const supabase = createClient(env.supabaseUrl, env.supabaseAnonKey)
