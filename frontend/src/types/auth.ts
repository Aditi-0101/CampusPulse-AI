export type UserRole =
  | "STUDENT"
  | "NOC_SUPERVISOR"
  | "CAMPUS_ADMIN"
  | "NETWORK_ENGINEER"
  | "FACILITIES_MANAGER"
  | "VICE_CHANCELLOR"
  | "READ_ONLY";

export type PortalType = "student" | "admin" | "vc";

export interface UserSession {
  user_id: string;
  name: string;
  role: UserRole | string;
  email?: string | null;
  portal: PortalType;
  token_type?: "student" | "staff";
}

export interface LoginResponse {
  status: string;
  user: UserSession;
  redirect_url: string;
}
