'use client'
import { useState, FormEvent } from 'react'
import { Input } from '@/components/ui'
import { Button } from '@/components/ui/Button'
import { NAVY } from '@/lib/constants'

interface LoginFormProps {
  onLogin: (email: string, password: string) => Promise<void>
  error?: string
  loading?: boolean
}

export function LoginForm({ onLogin, error, loading }: LoginFormProps) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPwd, setShowPwd] = useState(false)
  const [localError, setLocalError] = useState('')

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (!email || !password) { setLocalError('Please enter email and password'); return }
    setLocalError('')
    try {
      await onLogin(email, password)
    } catch (err: any) {
      setLocalError(err.message || 'Login failed')
    }
  }

  const displayError = error || localError

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      <div>
        <label className="block text-xs font-semibold text-[#060B4E] mb-1.5">Email</label>
        <Input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@acldigital.com"
          autoComplete="email"
        />
      </div>

      <div>
        <label className="block text-xs font-semibold text-[#060B4E] mb-1.5">Password</label>
        <div className="relative">
          <Input
            type={showPwd ? 'text' : 'password'}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Enter your password"
            autoComplete="current-password"
            className="pr-14"
          />
          <button
            type="button"
            onClick={() => setShowPwd((s) => !s)}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-slate-400 hover:text-slate-600"
          >
            {showPwd ? 'Hide' : 'Show'}
          </button>
        </div>
      </div>

      {displayError && (
        <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700">
          {displayError}
        </div>
      )}

      <Button type="submit" disabled={loading} className="w-full py-2.5 mt-1">
        {loading ? 'Signing in...' : 'Sign In'}
      </Button>
    </form>
  )
}
