"use client";

import React from "react";
import Link from "next/link";
import { ShieldAlert, LogOut, Home } from "lucide-react";
import { useAuth } from "@/context/AuthContext";

export default function UnauthorizedPage() {
  const { user, logout } = useAuth();

  const portalHref = !user
    ? "/login"
    : user.portal === "student"
    ? "/student"
    : user.portal === "vc"
    ? "/vc"
    : "/admin";

  const portalLabel = !user
    ? "Return to Login"
    : user.portal === "student"
    ? "Go to Student Dashboard"
    : user.portal === "vc"
    ? "Go to VC Dashboard"
    : "Go to Admin Dashboard";

  return (
    <div className="min-h-[60vh] flex items-center justify-center px-4">
      <div className="max-w-md w-full text-center space-y-6 bg-white p-8 rounded-2xl border border-slate-200 shadow-sm">
        <div className="w-16 h-16 rounded-2xl bg-rose-50 border border-rose-200 text-rose-600 mx-auto flex items-center justify-center">
          <ShieldAlert className="w-8 h-8" />
        </div>

        <div className="space-y-2">
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">
            Access Restricted
          </h1>
          <p className="text-sm text-slate-600">
            You do not have security clearance or authorization to access this portal. Strict role-based access control (RBAC) is enforced.
          </p>
        </div>

        {user && (
          <div className="bg-slate-50 border border-slate-200 rounded-lg p-3 text-xs text-left space-y-1">
            <div className="text-slate-500 font-medium">Current Session:</div>
            <div className="text-slate-900 font-semibold">{user.name}</div>
            <div className="text-blue-600 font-mono">Role: {user.role}</div>
          </div>
        )}

        <div className="flex flex-col sm:flex-row gap-3 justify-center pt-2">
          <Link
            href={portalHref}
            className="inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg text-sm font-semibold bg-[#0f2744] text-white hover:bg-[#163252] transition-colors"
          >
            <Home className="w-4 h-4" />
            <span>{portalLabel}</span>
          </Link>
          {user && (
            <button
              onClick={() => logout()}
              className="inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg text-sm font-semibold border border-rose-200 text-rose-700 bg-rose-50 hover:bg-rose-100 transition-colors"
            >
              <LogOut className="w-4 h-4" />
              <span>Sign Out</span>
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
