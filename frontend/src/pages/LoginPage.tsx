import { useState } from 'react'
import type { FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { setToken } from '../api/auth'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'

export function LoginPage() {
  const navigate = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setPending(true)
    try {
      const { token } = await api.login(username, password)
      setToken(token)
      navigate('/', { replace: true })
    } catch (err) {
      setError((err as Error).message || 'Login failed')
    } finally {
      setPending(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <Card className="w-full max-w-sm p-6">
        <h1 className="mb-1 font-display text-2xl uppercase tracking-widest text-neutral-100">
          🎬 Live Cutter
        </h1>
        <p className="mb-6 font-mono text-xs text-neutral-500">Sign in to continue</p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1 block font-mono text-xs uppercase tracking-widest text-neutral-500">
              Username
            </label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoFocus
              className="w-full border-2 border-neutral-700 bg-black px-3 py-2 text-sm text-neutral-100 outline-none focus:border-brand-500"
            />
          </div>
          <div>
            <label className="mb-1 block font-mono text-xs uppercase tracking-widest text-neutral-500">
              Password
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full border-2 border-neutral-700 bg-black px-3 py-2 text-sm text-neutral-100 outline-none focus:border-brand-500"
            />
          </div>

          {error && (
            <p className="border-2 border-brand-800 bg-brand-950/40 px-3 py-2 font-mono text-xs text-brand-400">
              {error}
            </p>
          )}

          <Button type="submit" variant="primary" className="w-full" disabled={pending}>
            {pending ? 'Signing in…' : 'Sign In'}
          </Button>
        </form>
      </Card>
    </div>
  )
}
