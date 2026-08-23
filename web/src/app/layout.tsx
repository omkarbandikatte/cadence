import type { Metadata } from "next";
import "./globals.css";
import { RunProvider } from "@/lib/RunContext";
import { Nav } from "@/components/Nav";

export const metadata: Metadata = {
  title: "Cadence — recurring debit recovery",
  description: "Recovers failed recurring debits by predicting when the customer's account will be funded.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased">
        <RunProvider>
          <Nav />
          <main className="max-w-6xl mx-auto px-4 py-6">{children}</main>
        </RunProvider>
      </body>
    </html>
  );
}
