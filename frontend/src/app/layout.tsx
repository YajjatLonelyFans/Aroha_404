import type { Metadata } from "next";
import { Inter, Montserrat } from "next/font/google";

import { SiteHeader } from "@/components/site-header";
import { AssistantLauncher } from "@/features/assistant/assistant-launcher";
import "./globals.css";

const inter = Inter({ variable: "--font-inter", subsets: ["latin"], display: "swap" });
const montserrat = Montserrat({ variable: "--font-montserrat", subsets: ["latin"], weight: ["500", "600"], display: "swap" });

export const metadata: Metadata = {
  title: "Aroha: rooftop solar for your home",
  description: "From “is my roof suitable?” to a submitted rooftop-solar subsidy application.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en-IN" className={`${inter.variable} ${montserrat.variable} h-full antialiased`}>
      <body className="flex min-h-full flex-col font-sans">
        <SiteHeader />
        <main className="flex flex-1 flex-col">{children}</main>
        <AssistantLauncher />
      </body>
    </html>
  );
}
