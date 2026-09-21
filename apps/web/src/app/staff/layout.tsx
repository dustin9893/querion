"use client";

import { StaffSettingsProvider } from "@/components/providers/StaffSettingsProvider";

export default function StaffLayout({ children }: { children: React.ReactNode }) {
  return <StaffSettingsProvider>{children}</StaffSettingsProvider>;
}
