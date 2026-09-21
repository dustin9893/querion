import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Đăng nhập quản trị",
};

export default function LoginLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  // Login page has no sidebar/topbar — just render children directly
  return <>{children}</>;
}
