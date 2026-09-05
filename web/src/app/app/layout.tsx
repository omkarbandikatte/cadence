import { RunProvider } from "@/lib/RunContext";
import { Nav } from "@/components/Nav";
import { DemoPanel } from "@/components/DemoPanel";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <RunProvider>
      <div className="app-shell-bg" aria-hidden />
      <Nav />
      <main className="max-w-6xl mx-auto px-4 py-6 relative z-10">{children}</main>
      <DemoPanel />
    </RunProvider>
  );
}
