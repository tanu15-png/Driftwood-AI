/**
 * Single source of truth for environment variables (read at boot).
 *
 * All required `VITE_*` vars must be present and well-formed, or the app
 * refuses to start. Components never read `import.meta.env` directly.
 */

const required = (name: string): string => {
  const value = import.meta.env[name]
  if (typeof value !== 'string' || value.trim() === '') {
    throw new Error(
      `Missing required environment variable: ${name}. ` +
        `Copy frontend/.env.example to frontend/.env and fill it in.`,
    )
  }
  return value.trim()
}

const requiredUrl = (name: string): string => {
  const value = required(name)
  try {
    new URL(value)
  } catch {
    throw new Error(
      `Environment variable ${name} must be a valid URL, got: "${value}"`,
    )
  }
  return value
}

const requiredHttpUrl = (name: string): string => {
  const value = requiredUrl(name)
  if (!/^https?:\/\//.test(value)) {
    throw new Error(
      `Environment variable ${name} must start with http:// or https://, got: "${value}"`,
    )
  }
  return value
}

export const env = {
  apiBaseUrl: requiredHttpUrl('VITE_API_BASE_URL'),
  supabaseUrl: requiredUrl('VITE_SUPABASE_URL'),
  supabaseAnonKey: required('VITE_SUPABASE_ANON_KEY'),
} as const
