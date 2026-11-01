"use client";

import React, { useState, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  Wifi,
  KeyRound,
  Eye,
  EyeOff,
  ArrowRight,
  ShieldCheck,
  AlertCircle,
  Loader2,
} from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { ApiError } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const redirectParam = searchParams.get("redirect");

  const { user, isAuthenticated, isLoading: authLoading, login } = useAuth();

  const [credential, setCredential] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // If already authenticated, redirect to authorized portal
  useEffect(() => {
    if (!authLoading && isAuthenticated && user) {
      if (redirectParam && redirectParam.startsWith("/")) {
        router.replace(redirectParam);
      } else {
        const dest =
          user.portal === "student"
            ? "/student"
            : user.portal === "vc"
            ? "/vc"
            : "/admin";
        router.replace(dest);
      }
    }
  }, [authLoading, isAuthenticated, user, redirectParam, router]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const cleanCred = credential.trim();
    if (!cleanCred) {
      setErrorMessage("Please enter your university credential or access token.");
      return;
    }

    setIsSubmitting(true);
    setErrorMessage(null);

    try {
      const resp = await login(cleanCred);
      // Determine destination
      if (redirectParam && redirectParam.startsWith("/")) {
        // Simple check that destination matches portal
        const isStudentRoute = ["/student", "/submit", "/track"].some(r => redirectParam.startsWith(r));
        const isAdminRoute = ["/admin", "/swarm"].some(r => redirectParam.startsWith(r));
        const isVCRoute = redirectParam.startsWith("/vc");

        if (resp.user.portal === "student" && isStudentRoute) {
          router.replace(redirectParam);
          return;
        }
        if (resp.user.portal === "admin" && isAdminRoute) {
          router.replace(redirectParam);
          return;
        }
        if (resp.user.portal === "vc" && isVCRoute) {
          router.replace(redirectParam);
          return;
        }
      }

      router.replace(resp.redirect_url);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setErrorMessage(
          err.status === 401
            ? "Invalid university credential. Please verify your credentials and try again."
            : err.message
        );
      } else {
        setErrorMessage("Network error. Unable to reach campus authentication service.");
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-[75vh] flex items-center justify-center px-4 py-8">
      <div className="max-w-md w-full space-y-8 bg-white p-8 sm:p-10 rounded-2xl border border-slate-200/80 shadow-lg shadow-slate-200/50">
        {/* Branding & Header */}
        <div className="text-center space-y-3">
          <div className="w-14 h-14 rounded-2xl bg-[#0f2744] text-blue-400 mx-auto flex items-center justify-center shadow-md shadow-blue-900/10">
            <Wifi className="w-7 h-7" />
          </div>
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-slate-900">
              CampusPulse AI
            </h1>
            <p className="text-xs font-semibold text-blue-600 uppercase tracking-widest mt-0.5">
              Secure Role-Based Portal
            </p>
          </div>
          <p className="text-sm text-slate-500 max-w-xs mx-auto">
            Sign in with your university-issued credential to enter your authorized portal.
          </p>
        </div>

        {/* Error Alert */}
        {errorMessage && (
          <div className="p-3.5 rounded-xl bg-rose-50 border border-rose-200/80 text-rose-800 text-xs flex items-start gap-2.5 animate-fadeIn">
            <AlertCircle className="w-4 h-4 text-rose-500 shrink-0 mt-0.5" />
            <div className="flex-1 font-medium leading-relaxed">{errorMessage}</div>
          </div>
        )}

        {/* Login Form */}
        <form onSubmit={handleSubmit} className="space-y-5">
          <div className="space-y-1.5">
            <label
              htmlFor="credential"
              className="block text-xs font-semibold uppercase tracking-wider text-slate-700"
            >
              University Credential / Access Token
            </label>
            <div className="relative">
              <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-400">
                <KeyRound className="w-4 h-4" />
              </div>
              <input
                id="credential"
                name="credential"
                type={showPassword ? "text" : "password"}
                autoComplete="current-password"
                required
                value={credential}
                onChange={(e) => setCredential(e.target.value)}
                placeholder="Enter student or staff credential..."
                disabled={isSubmitting}
                className="w-full pl-10 pr-10 py-2.5 rounded-xl border border-slate-300 text-slate-900 placeholder:text-slate-400 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all disabled:opacity-50"
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                tabIndex={-1}
                className="absolute inset-y-0 right-0 pr-3.5 flex items-center text-slate-400 hover:text-slate-600"
                aria-label={showPassword ? "Hide credential" : "Show credential"}
              >
                {showPassword ? (
                  <EyeOff className="w-4 h-4" />
                ) : (
                  <Eye className="w-4 h-4" />
                )}
              </button>
            </div>
            <p className="text-[11px] text-slate-400">
              Identity, role, and authorized portal are derived securely on the backend.
            </p>
          </div>

          <button
            type="submit"
            disabled={isSubmitting || !credential.trim()}
            className="w-full py-3 px-4 rounded-xl text-sm font-semibold text-white bg-[#0f2744] hover:bg-[#163252] focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-600 transition-all shadow-md shadow-slate-900/10 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 group"
          >
            {isSubmitting ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin text-blue-300" />
                <span>Authenticating...</span>
              </>
            ) : (
              <>
                <span>Sign In to Portal</span>
                <ArrowRight className="w-4 h-4 text-blue-300 group-hover:translate-x-0.5 transition-transform" />
              </>
            )}
          </button>
        </form>

        {/* Security / Privacy Footnote */}
        <div className="pt-4 border-t border-slate-100 flex items-center justify-center gap-2 text-xs text-slate-500">
          <ShieldCheck className="w-4 h-4 text-emerald-600 shrink-0" />
          <span>Encrypted HttpOnly session • Strict RBAC enforced</span>
        </div>
      </div>
    </div>
  );
}
