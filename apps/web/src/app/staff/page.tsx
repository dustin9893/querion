"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { restoreStaffToken } from "@/lib/api/staff";

// /staff → the chat when a staff token is stored (the chat page re-checks it and handles expiry
// and forced password changes), otherwise the staff login.
export default function StaffHomePage() {
  const router = useRouter();

  useEffect(() => {
    router.replace(restoreStaffToken() ? "/staff/chat" : "/staff/login");
  }, [router]);

  return (
    <div className="flex items-center justify-center" style={{ height: "100vh" }}>
      <div className="animate-spin rounded-full h-6 w-6 border-2 border-current"
        style={{ borderTopColor: "transparent", color: "var(--accent)" }} />
    </div>
  );
}
