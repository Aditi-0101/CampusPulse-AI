"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { Loader2 } from "lucide-react";

export default function RootPage() {
  const router = useRouter();
  const { user, isAuthenticated, isLoading } = useAuth();

  useEffect(() => {
    if (isLoading) return;

    if (!isAuthenticated || !user) {
      router.replace("/login");
      return;
    }

    if (user.portal === "student") {
      router.replace("/student");
    } else if (user.portal === "vc") {
      router.replace("/vc");
    } else {
      router.replace("/admin");
    }
  }, [isLoading, isAuthenticated, user, router]);

  return (
    <div className="min-h-[60vh] flex flex-col items-center justify-center space-y-4">
      <div className="w-12 h-12 rounded-2xl bg-[#0f2744] text-blue-400 flex items-center justify-center shadow-md">
        <Loader2 className="w-6 h-6 animate-spin" />
      </div>
      <p className="text-sm font-medium text-slate-500">
        Redirecting to authorized university portal...
      </p>
    </div>
  );
}
