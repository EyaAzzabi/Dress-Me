import AsyncStorage from "@react-native-async-storage/async-storage";
import { createContext, ReactNode, useContext, useEffect, useMemo, useState } from "react";
import { useColorScheme } from "react-native";

import { ColorTokens, darkColors, lightColors } from "@/theme/tokens";

const THEME_OVERRIDE_KEY = "dressme_theme_override";

interface ThemeContextValue {
  colors: ColorTokens;
  isDark: boolean;
  toggleTheme: () => void;
}

const ThemeContext = createContext<ThemeContextValue | undefined>(undefined);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const systemScheme = useColorScheme();
  const [override, setOverride] = useState<"light" | "dark" | null>(null);

  useEffect(() => {
    AsyncStorage.getItem(THEME_OVERRIDE_KEY).then((value) => {
      if (value === "light" || value === "dark") setOverride(value);
    });
  }, []);

  const isDark = override ? override === "dark" : systemScheme === "dark";

  function toggleTheme() {
    const next = isDark ? "light" : "dark";
    setOverride(next);
    AsyncStorage.setItem(THEME_OVERRIDE_KEY, next).catch(() => {
      // Best-effort persistence — a failed write just means the toggle won't
      // survive an app restart, not worth surfacing to the user.
    });
  }

  const value = useMemo(
    () => ({ colors: isDark ? darkColors : lightColors, isDark, toggleTheme }),
    [isDark]
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used within a ThemeProvider");
  return ctx;
}
