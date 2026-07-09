import { apiRequest } from "@/api/client";

export type AuthUser = {
  id: number;
  username: string;
  role: string;
  isActive: boolean;
};

export type LoginPayload = {
  username: string;
  password: string;
};

export type LoginResponse = {
  access_token: string;
  token_type: string;
  user: AuthUser;
};

export async function loginUser(payload: LoginPayload): Promise<LoginResponse> {
  return apiRequest<LoginResponse>("/auth/login", {
    method: "POST",
    body: {
      username: payload.username,
      password: payload.password,
    },
  });
}

export async function getCurrentUser(token: string): Promise<AuthUser> {
  return apiRequest<AuthUser>("/auth/me", {
    method: "GET",
    token,
  });
}
