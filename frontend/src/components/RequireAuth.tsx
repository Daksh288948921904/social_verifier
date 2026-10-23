import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import { getToken, setToken } from '../api/auth'
import { api } from '../api/client'

// Local dev only: skip the login screen by auto-authenticating with the
// single hardcoded account instead of clicking through it every time the
// backend restarts and mints a fresh session token. import.meta.env.DEV is
// false in production builds, so this never reaches a deployed build.
const DEV_AUTO_LOGIN = import.meta.env.DEV

export function RequireAuth({ children }: { children: ReactNode }) {
  const [loggingIn, setLoggingIn] = useState(DEV_AUTO_LOGIN && !getToken())

  useEffect(() => {
    if (!DEV_AUTO_LOGIN || getToken()) return
    api.login('rig360media', 'worldisDNL').then(({ token }) => {
      setToken(token)
      setLoggingIn(false)
    })
  }, [])

  if (!getToken()) {
    if (DEV_AUTO_LOGIN) return loggingIn ? null : <>{children}</>
    return <Navigate to="/login" replace />
  }
  return <>{children}</>
}
