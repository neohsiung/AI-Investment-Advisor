import type { Metadata } from "next";
import { Inter, Space_Grotesk } from "next/font/google";
import "./globals.css";
import Sidebar from "@/components/layout/Sidebar";
import TopBar from "@/components/layout/TopBar";
import { Providers } from "@/components/Providers";
import { SidebarProvider } from "@/context/SidebarContext";
import SidebarOverlay from "@/components/layout/SidebarOverlay";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
});

const spaceGrotesk = Space_Grotesk({
  variable: "--font-space-grotesk",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Quantum AI | Command Center",
  description: "Advanced AI Investment Advisory Platform",
  manifest: "/manifest.json",
  themeColor: "#0a0a0a",
  viewport: "width=device-width, initial-scale=1, maximum-scale=1, user-scalable=0",
  appleWebApp: {
    capable: true,
    title: "Quantum AI",
    statusBarStyle: "black-translucent",
  }
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${inter.variable} ${spaceGrotesk.variable} h-full antialiased`}
      suppressHydrationWarning
    >
      <head>
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=block"
        />
      </head>
      <body className="min-h-full flex font-body bg-background text-on-surface">
        <Providers>
          <SidebarProvider>
            <Sidebar />
            <SidebarOverlay />
            <div className="flex-1 flex flex-col min-h-screen ml-0 lg:ml-64 transition-all duration-300">
              <TopBar />
              <main className="flex-1 pt-16 p-4 sm:p-6 lg:p-8 overflow-y-auto">
                {children}
              </main>
            </div>
          </SidebarProvider>
        </Providers>
      </body>
    </html>
  );
}
