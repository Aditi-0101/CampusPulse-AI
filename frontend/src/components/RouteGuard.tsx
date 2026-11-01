"use client";

import React, { useEffect } from "react";
import { useRouter, usePathname } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { PortalType, UserRole } from "@/types/auth";
import { Loader2 } from "lucide-react";

interface RouteGuardProps {
  children: React.ReactNode;
  allowedPortals?: PortalType[];
  requiredRole?: UserRole;
}

export function RouteGuard({
  children,
  allowedPortals,
  requiredRole,
}: RouteGuardProps) {
  const { user, isLoading, isAuthenticated } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (isLoading) return;

    if (!isAuthenticated || !user) {
      // Redirect unauthenticated user to login with return path
      router.replace(`/login?redirect=${encodeURIComponent(pathname)}`);
      return;
    }

    // Role check if required
    if (requiredRole && user.role !== requiredRole) {
      router.replace("/unauthorized");
      return;
    }

    // Portal check if specified
    if (allowedPortals && allowedPortals.length > 0 && !allowedPortals.includes(user.portal)) {
      router.replace("/unauthorized");
      return;
    }
  }, [isLoading, isAuthenticated, user, allowedPortals, requiredRole, pathname, router]);

  // Loading state prevents flicker of protected content
  if (isLoading) {
    return (
      <div className="min-h-[50vh] flex flex-col items-center justify-center space-y-4">
        <div className="w-12 h-12 rounded-2xl bg-blue-50 border border-blue-200 flex items-center justify-center">
          <Loader2 className="w-6 h-6 text-blue-600 animate-spin" />
        </div>
        <p className="text-sm font-medium text-slate-500">
          Verifying security authorization...
        </p>
      </div>
    );
  }

  // If not authenticated or not authorized, don't render children while redirecting
  if (!isAuthenticated || !user) {
    return null;
  }

  if (requiredRole && user.role !== requiredRole) {
    return null;
  }

  if (allowedPortals && allowedPortals.length > 0 && !allowedPortals.includes(user.portal)) {
    return null;
  }

  return <>{children}</>;
}
