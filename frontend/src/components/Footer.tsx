"use client";

import React from "react";
import Link from "next/link";
import { Shield, Cpu, BookOpen } from "lucide-react";

export function Footer() {
  return (
    <footer className="bg-[#0a192f] text-slate-400 border-t border-slate-800 text-sm mt-auto">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-8 mb-8">
          {/* Column 1: System info */}
          <div className="md:col-span-2 space-y-3">
            <div className="flex items-center gap-2 text-white font-bold text-base">
              <span className="w-2.5 h-2.5 rounded-full bg-blue-400 inline-block"></span>
              <span>CampusPulse AI</span>
              <span className="text-xs px-2 py-0.5 rounded bg-blue-900/60 text-blue-300 border border-blue-700/40 font-mono">
                Stage E.2
              </span>
            </div>
            <p className="text-xs text-slate-300 max-w-md leading-relaxed">
              Autonomous multi-agent campus grievance orchestration system. Built for HackCBS 9.0 (Track B: Campus Grievance Swarm) with Meko swarm memory and human-in-the-loop operational oversight.
            </p>
            <div className="flex items-center gap-2 text-xs text-emerald-400 pt-1">
              <Shield className="w-3.5 h-3.5" />
              <span>Zero-PII Architecture: No room numbers or personal identities collected.</span>
            </div>
          </div>

          {/* Column 2: Student Quick Links */}
          <div className="space-y-2">
            <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-300">
              Student Portal
            </h4>
            <ul className="space-y-1.5 text-xs">
              <li>
                <Link href="/" className="hover:text-blue-300 transition-colors">
                  Dashboard
                </Link>
              </li>
              <li>
                <Link href="/submit" className="hover:text-blue-300 transition-colors">
                  Submit Complaint (Hostel Wi-Fi)
                </Link>
              </li>
              <li>
                <Link href="/track" className="hover:text-blue-300 transition-colors">
                  Track Ticket Status
                </Link>
              </li>
            </ul>
          </div>

          {/* Column 3: Architecture & Privacy */}
          <div className="space-y-2">
            <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-300">
              Platform Standards
            </h4>
            <ul className="space-y-1.5 text-xs text-slate-400">
              <li className="flex items-center gap-1.5">
                <Cpu className="w-3 h-3 text-blue-400" />
                <span>FastAPI Swarm Backend</span>
              </li>
              <li className="flex items-center gap-1.5">
                <Shield className="w-3 h-3 text-blue-400" />
                <span>X-Staff-Token Security</span>
              </li>
              <li className="flex items-center gap-1.5">
                <BookOpen className="w-3 h-3 text-blue-400" />
                <span>Meko Long-Term Memory</span>
              </li>
            </ul>
          </div>
        </div>

        {/* Bottom bar */}
        <div className="border-t border-slate-800/80 pt-6 flex flex-col sm:flex-row items-center justify-between text-xs text-slate-300 gap-4">
          <p>
            © 2026 CampusPulse AI. Official University Campus Technology Demonstration.
          </p>
          <div className="flex items-center gap-4 text-slate-300">
            <span>FastAPI: <code className="text-blue-300 font-mono">/api/v1/grievances</code></span>
            <span>•</span>
            <span>Track B: Grievance Swarm</span>
          </div>
        </div>
      </div>
    </footer>
  );
}
