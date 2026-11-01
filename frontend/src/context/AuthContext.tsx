"use client";

import React, {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  ReactNode,
} from "react";
import { useRouter } from "next/navigation";
import { UserSession, LoginResponse } from "@/types/auth";
import { fetchCurrentUser, loginUser, logoutUser } from "@/lib/api";

interface AuthContextType {
  user: UserSession | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  login: (credential: string) => Promise<LoginResponse>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserSession | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const router = useRouter();

  useEffect(() => {
    let ignore = false;
    fetchCurrentUser()
      .then((session) => {
        if (!ignore) {
          setUser(session);
          setIsLoading(false);
        }
      })
      .catch(() => {
        if (!ignore) {
          setUser(null);
          setIsLoading(false);
        }
      });

    return () => {
      ignore = true;
    };
  }, []);

  const refreshUser = useCallback(async () => {
    try {
      const session = await fetchCurrentUser();
      setUser(session);
    } catch {
      setUser(null);
    }
  }, []);

  const login = async (credential: string): Promise<LoginResponse> => {
    setIsLoading(true);
    try {
      const resp = await loginUser(credential);
      setUser(resp.user);
      return resp;
    } finally {
      setIsLoading(false);
    }
  };

  const logout = async () => {
    setIsLoading(true);
    try {
      await logoutUser();
      setUser(null);
      router.push("/login");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        isLoading,
        isAuthenticated: !!user,
        login,
        logout,
        refreshUser,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextType {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
