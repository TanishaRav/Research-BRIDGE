import type { Metadata } from "next";
import "@fontsource-variable/space-grotesk";
import "@fontsource-variable/public-sans";
import "@fontsource-variable/jetbrains-mono";
import "./globals.css";
import { DemoProvider } from "@/lib/demo-context";

export const metadata: Metadata = {
  title: {
    default: "ResearchBridge",
    template: "%s · ResearchBridge",
  },
  description:
    "Independent synthetic-data prototype for transparent EUReCA research placement.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <a className="skip-link" href="#main-content">
          Skip to main content
        </a>
        <DemoProvider>{children}</DemoProvider>
      </body>
    </html>
  );
}
