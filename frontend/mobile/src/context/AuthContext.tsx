import AsyncStorage from "@react-native-async-storage/async-storage";
import { createContext, ReactNode, useContext, useEffect, useState } from "react";

import { login as loginRequest, LoginPayload, register as registerRequest, RegisterPayload } from "@/api/auth";
import { TOKEN_STORAGE_KEY } from "@/api/client";

interface AuthContextValue {
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (payload: LoginPayload) => Promise<void>;
  register: (payload: RegisterPayload) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    AsyncStorage.getItem(TOKEN_STORAGE_KEY).then((token) => {
      setIsAuthenticated(Boolean(token));
      setIsLoading(false);
    });
  }, []);

  async function login(payload: LoginPayload) {
    const { access_token } = await loginRequest(payload);
    await AsyncStorage.setItem(TOKEN_STORAGE_KEY, access_token);
    setIsAuthenticated(true);
  }

  async function register(payload: RegisterPayload) {
    await registerRequest(payload);
    await login({ email: payload.email, password: payload.password });
  }

  async function logout() {
    await AsyncStorage.removeItem(TOKEN_STORAGE_KEY);
    setIsAuthenticated(false);
  }

  return (
    <AuthContext.Provider value={{ isAuthenticated, isLoading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
