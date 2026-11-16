import type { Metadata } from "next";
import type { ReactNode } from "react";

import { LocaleProvider } from "@/lib/i18n/provider";
import { getI18n } from "@/lib/i18n/server";

import "./globals.css";

export const metadata: Metadata = {
  title: "Collaborative OSCAL",
  description: "Open-source GRC platform foundation",
};

export default async function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  const { locale } = await getI18n();
  return (
    <html lang={locale}>
      <body><LocaleProvider locale={locale}>{children}</LocaleProvider></body>
    </html>
  );
}
