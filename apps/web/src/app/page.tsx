"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/components/providers/AuthProvider";

export default function HomePage() {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (loading) return;
    if (user) {
      router.replace("/datasets");
    } else {
      router.replace("/login");
    }
  }, [user, loading, router]);

  return (
    <div className="flex items-center justify-center" style={{ height: "100vh" }}>
      <div className="animate-spin rounded-full h-6 w-6 border-2 border-current"
        style={{ borderTopColor: "transparent", color: "var(--accent)" }} />
    </div>
  );
}
