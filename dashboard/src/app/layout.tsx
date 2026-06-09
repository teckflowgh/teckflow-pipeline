import type { Metadata } from "next";
import "./globals.css";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Video Pipeline Dashboard",
  description: "Automated daily video generation pipeline",
};

const navLinks = [
  { href: "/", label: "Dashboard" },
  { href: "/history", label: "Run History" },
  { href: "/settings", label: "Settings" },
];

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-gray-950 text-gray-100 font-sans">
        <nav className="bg-gray-900 border-b border-gray-800 px-6 py-3 flex items-center gap-8">
          <span className="font-bold text-brand-500 text-lg tracking-tight">
            🎬 VideoBot
          </span>
          {navLinks.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              className="text-sm text-gray-400 hover:text-white transition-colors"
            >
              {l.label}
            </Link>
          ))}
        </nav>
        <main className="max-w-5xl mx-auto px-4 py-8">{children}</main>
      </body>
    </html>
  );
}
