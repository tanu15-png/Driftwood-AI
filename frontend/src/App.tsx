import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { RequireAuth } from '@/components/auth/RequireAuth'
import { AuthProvider } from '@/lib/auth-provider'
import ChatPage from '@/pages/chat'
import SignInPage from '@/pages/sign-in'
import SignUpPage from '@/pages/sign-up'

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/signin" element={<SignInPage />} />
          <Route path="/signup" element={<SignUpPage />} />
          <Route element={<RequireAuth />}>
            <Route path="/" element={<ChatPage />} />
            <Route path="/t/:threadId" element={<ChatPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  )
}
