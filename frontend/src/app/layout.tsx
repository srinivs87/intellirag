import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'ACL IntelliRAG',
  description: 'On-premise AI knowledge assistant',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  )
}
