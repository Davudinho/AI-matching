import type { Metadata } from "next"
import "./globals.css"
import { AuthProvider } from "@/components/AuthProvider"
import Navbar from "@/components/layout/Navbar"
import Footer from "@/components/layout/Footer"
import { Geist } from "next/font/google";
import { cn } from "@/lib/utils";

const geist = Geist({subsets:['latin'],variable:'--font-sans'});

export const metadata: Metadata = {
  title: {
    default: "Dyversifying — AI-Powered Diverse Hiring",
    template: "%s | Dyversifying",
  },
  description:
    "Find your next opportunity or hire diverse talent with AI-powered matching. Fair, transparent, and built for inclusion.",
  keywords: ["diversity hiring", "AI recruitment", "job matching", "inclusive hiring"],
  openGraph: {
    title: "Dyversifying — AI-Powered Diverse Hiring",
    description: "Fair, transparent AI hiring for everyone.",
    type: "website",
  },
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" suppressHydrationWarning className={cn("font-sans", geist.variable)}>
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
      </head>
      <body>
        <AuthProvider>
          <Navbar />
          <main>{children}</main>
          <Footer />
        </AuthProvider>
      </body>
    </html>
  )
}
