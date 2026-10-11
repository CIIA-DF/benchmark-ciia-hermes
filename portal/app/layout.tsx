import type { Metadata } from "next";
import { Inter, Roboto_Mono } from "next/font/google";
import "./globals.css";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
});

const robotoMono = Roboto_Mono({
  variable: "--font-roboto-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Portal de Orquestração: Benchmark SEI | CIIA-DF",
  description: "Portal de Orquestração da Equipe de P&D",
  icons: {
    icon: "/ciia_logo.png",
    shortcut: "/ciia_logo.png",
    apple: "/ciia_logo.png",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="pt-BR"
      className={`${inter.variable} ${robotoMono.variable} h-full antialiased`}
    >
      <head>
        <link rel="icon" href="/ciia_logo.png" type="image/png" sizes="any" />
        <link rel="shortcut icon" href="/ciia_logo.png" type="image/png" />
        <link rel="apple-touch-icon" href="/ciia_logo.png" />
      </head>
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
