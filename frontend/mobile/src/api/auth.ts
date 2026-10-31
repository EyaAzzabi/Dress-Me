import { apiClient } from "@/api/client";

export interface LoginPayload {
  email: string;
  password: string;
}

export interface RegisterPayload extends LoginPayload {
  full_name?: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export function login(payload: LoginPayload) {
  return apiClient.post<TokenResponse>("/auth/login", payload).then((r) => r.data);
}

export function register(payload: RegisterPayload) {
  return apiClient.post("/auth/register", payload).then((r) => r.data);
}

export interface Me {
  id: string;
  email: string;
  full_name: string | null;
  avatar_photo_url: string | null;
}

export function getMe() {
  return apiClient.get<Me>("/auth/me").then((r) => r.data);
}
