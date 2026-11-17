import { AppShell } from "@/components/app-shell";
import { ErrorBoundary } from "@/components/states";

export default function AppGroupLayout({ children }: { children: React.ReactNode }) {
  return (
    <AppShell>
      <ErrorBoundary>{children}</ErrorBoundary>
    </AppShell>
  );
}
