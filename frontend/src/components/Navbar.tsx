"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Wifi,
  PlusCircle,
  Search,
  Home,
  Menu,
  X,
  ShieldAlert,
  Activity,
  Landmark,
  LogOut,
  User,
} from "lucide-react";
import { checkBackendHealth } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

export function Navbar() {
  const pathname = usePathname();
  const { user, isAuthenticated, logout } = useAuth();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [apiConnected, setApiConnected] = useState<boolean | null>(null);

  useEffect(() => {
    checkBackendHealth().then((res) => {
      setApiConnected(res !== null && res.status === "healthy");
    });
  }, []);

  // Determine portal home link based on role
  const portalHome = !user
    ? "/login"
    : user.portal === "student"
    ? "/student"
    : user.portal === "vc"
    ? "/vc"
    : "/admin";

  // Determine portal badge
  const portalBadge = !user
    ? "University Portal"
    : user.portal === "student"
    ? "Student Portal"
    : user.portal === "vc"
    ? "Vice-Chancellor Executive"
    : "Campus Administration";

  // Navigation links based strictly on user portal/role
  const navLinks = React.useMemo(() => {
    if (!user) {
      return [];
    }

    if (user.portal === "student") {
      return [
        { href: "/student", label: "Dashboard", icon: Home },
        { href: "/submit", label: "Submit Complaint", icon: PlusCircle },
        { href: "/track", label: "Track Status", icon: Search },
      ];
    }

    if (user.portal === "admin") {
      return [
        { href: "/admin", label: "Admin Dashboard", icon: ShieldAlert },
        { href: "/swarm", label: "Swarm Monitoring", icon: Activity },
      ];
    }

    if (user.portal === "vc") {
      return [
        { href: "/vc", label: "Executive Dashboard", icon: Landmark },
      ];
    }

    return [];
  }, [user]);

  const handleLogout = async () => {
    setMobileMenuOpen(false);
    await logout();
  };

  return (
    <header className="bg-[#0f2744] text-white border-b border-[#1e3a5f] sticky top-0 z-50 shadow-sm">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Brand Logo & University Title */}
          <Link href={portalHome} className="flex items-center gap-3 group">
            <div className="w-10 h-10 rounded-lg bg-[#1e3a5f] border border-blue-400/30 flex items-center justify-center text-blue-300 group-hover:text-white group-hover:bg-blue-600 transition-colors">
              <Wifi className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-bold text-lg tracking-tight text-white">CampusPulse AI</span>
                <span className="hidden sm:inline-block px-2 py-0.5 text-[10px] font-semibold bg-blue-500/20 text-blue-300 rounded border border-blue-400/20">
                  {portalBadge}
                </span>
              </div>
              <p className="text-xs text-slate-300 font-medium hidden md:block">
                Autonomous Infrastructure Resolution
              </p>
            </div>
          </Link>

          {/* Desktop Navigation */}
          {isAuthenticated && navLinks.length > 0 && (
            <nav className="hidden md:flex items-center gap-1">
              {navLinks.map((link) => {
                const Icon = link.icon;
                const isActive = pathname === link.href;
                return (
                  <Link
                    key={link.href}
                    href={link.href}
                    className={`flex items-center gap-2 px-3.5 py-2 rounded-md text-sm font-medium transition-colors ${
                      isActive
                        ? "bg-[#1e3a5f] text-white font-semibold border border-blue-400/30"
                        : "text-slate-200 hover:text-white hover:bg-[#163252]"
                    }`}
                  >
                    <Icon className="w-4 h-4 text-blue-300" />
                    <span>{link.label}</span>
                  </Link>
                );
              })}
            </nav>
          )}

          {/* Desktop Right Controls (User Info, Status, Logout) */}
          <div className="hidden sm:flex items-center gap-3">
            {/* Backend Health Badge */}
            <div className="flex items-center gap-2 px-2.5 py-1 rounded-full bg-[#163252] border border-slate-700/60 text-xs">
              <span
                className={`w-2 h-2 rounded-full ${
                  apiConnected === true
                    ? "bg-emerald-400 animate-pulse"
                    : apiConnected === false
                    ? "bg-rose-400"
                    : "bg-amber-400"
                }`}
              />
              <span className="text-slate-300 font-mono text-[11px]">
                {apiConnected === true ? "API Online" : apiConnected === false ? "API Offline" : "Connecting..."}
              </span>
            </div>

            {/* Authenticated User Badge & Logout */}
            {isAuthenticated && user ? (
              <div className="flex items-center gap-2 pl-2 border-l border-slate-700">
                <div className="flex flex-col text-right">
                  <span className="text-xs font-semibold text-white leading-tight">
                    {user.name || user.role}
                  </span>
                  <span className="text-[10px] text-blue-300 uppercase tracking-wide">
                    {user.role}
                  </span>
                </div>
                <button
                  onClick={handleLogout}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium text-slate-300 hover:text-white hover:bg-rose-900/40 border border-slate-700 hover:border-rose-700/50 transition-colors"
                  title="Sign out of session"
                >
                  <LogOut className="w-3.5 h-3.5 text-rose-400" />
                  <span>Logout</span>
                </button>
              </div>
            ) : pathname !== "/login" ? (
              <Link
                href="/login"
                className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-md text-xs font-semibold bg-blue-600 hover:bg-blue-500 text-white transition-colors shadow-sm"
              >
                <User className="w-3.5 h-3.5" />
                <span>Portal Login</span>
              </Link>
            ) : null}
          </div>

          {/* Mobile menu button */}
          <div className="flex md:hidden">
            <button
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              className="p-2 rounded-md text-slate-300 hover:text-white hover:bg-[#1e3a5f] focus:outline-none"
              aria-label="Toggle menu"
            >
              {mobileMenuOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
            </button>
          </div>
        </div>
      </div>

      {/* Mobile menu dropdown */}
      {mobileMenuOpen && (
        <div className="md:hidden bg-[#0d213a] border-b border-[#1e3a5f] px-4 pt-2 pb-4 space-y-1">
          {isAuthenticated && user && (
            <div className="px-3 py-2 border-b border-slate-800 mb-2">
              <div className="text-sm font-semibold text-white">{user.name}</div>
              <div className="text-xs text-blue-400 font-mono">{user.role}</div>
            </div>
          )}

          {navLinks.map((link) => {
            const Icon = link.icon;
            const isActive = pathname === link.href;
            return (
              <Link
                key={link.href}
                href={link.href}
                onClick={() => setMobileMenuOpen(false)}
                className={`flex items-center gap-3 px-3 py-2.5 rounded-md text-sm font-medium ${
                  isActive
                    ? "bg-[#1e3a5f] text-white font-semibold"
                    : "text-slate-200 hover:text-white hover:bg-[#163252]"
                }`}
              >
                <Icon className="w-4 h-4 text-blue-300" />
                <span>{link.label}</span>
              </Link>
            );
          })}

          {isAuthenticated ? (
            <button
              onClick={handleLogout}
              className="w-full flex items-center gap-3 px-3 py-2.5 rounded-md text-sm font-medium text-rose-300 hover:bg-rose-950/40"
            >
              <LogOut className="w-4 h-4 text-rose-400" />
              <span>Logout</span>
            </button>
          ) : (
            <Link
              href="/login"
              onClick={() => setMobileMenuOpen(false)}
              className="flex items-center gap-3 px-3 py-2.5 rounded-md text-sm font-medium text-blue-300 hover:bg-[#163252]"
            >
              <User className="w-4 h-4" />
              <span>Login to Portal</span>
            </Link>
          )}

          <div className="pt-2 border-t border-slate-700/60 flex items-center justify-between text-xs text-slate-400 px-3">
            <span>FastAPI Backend</span>
            <span className="font-mono text-emerald-400">
              {apiConnected ? "Connected" : "Offline"}
            </span>
          </div>
        </div>
      )}
    </header>
  );
}
