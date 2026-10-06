// Design tokens ported 1:1 from the approved HTML prototype (dressme_preview.html)
// so the app matches it exactly, not just "in spirit".

export interface ColorTokens {
  bg: string;
  surface: string;
  surfaceElevated: string;
  border: string;
  borderStrong: string;
  text: string;
  textMuted: string;
  textSubtle: string;
  primary: string;
  primaryContrast: string;
  accent: string;
  pillBg: string;
  pillActiveBg: string;
  pillText: string;
  pillActiveText: string;
  tabBg: string;
  tabBorder: string;
  tabActive: string;
  tabInactive: string;
  inputBg: string;
  inputBorder: string;
  success: string;
  successBg: string;
  warning: string;
  warningBg: string;
  error: string;
  errorBg: string;
}

export const lightColors: ColorTokens = {
  bg: "#FFFFFF",
  surface: "#FAFAFA",
  surfaceElevated: "#FFFFFF",
  border: "#E5E5EA",
  borderStrong: "#D1D1D6",
  text: "#0A0A0A",
  textMuted: "rgba(0,0,0,0.5)",
  textSubtle: "rgba(0,0,0,0.35)",
  primary: "#000000",
  primaryContrast: "#FFFFFF",
  accent: "#D4A373",
  pillBg: "#F2F2F7",
  pillActiveBg: "#000000",
  pillText: "#636366",
  pillActiveText: "#FFFFFF",
  tabBg: "#FFFFFF",
  tabBorder: "#E5E5EA",
  tabActive: "#000000",
  tabInactive: "#8E8E93",
  inputBg: "#F2F2F7",
  inputBorder: "#E5E5EA",
  success: "#2E7D32",
  successBg: "#E8F5E9",
  warning: "#E65100",
  warningBg: "#FFF3E0",
  error: "#C62828",
  errorBg: "#FFEBEE",
};

export const darkColors: ColorTokens = {
  bg: "#0A0A0A",
  surface: "#1C1C1E",
  surfaceElevated: "#2C2C2E",
  border: "rgba(255,255,255,0.1)",
  borderStrong: "rgba(255,255,255,0.2)",
  text: "#F5F5F7",
  textMuted: "rgba(255,255,255,0.5)",
  textSubtle: "rgba(255,255,255,0.3)",
  primary: "#FFFFFF",
  primaryContrast: "#000000",
  accent: "#D4A373",
  pillBg: "#2C2C2E",
  pillActiveBg: "#FFFFFF",
  pillText: "#AEAEB2",
  pillActiveText: "#000000",
  tabBg: "#141416",
  tabBorder: "rgba(255,255,255,0.08)",
  tabActive: "#FFFFFF",
  tabInactive: "#636366",
  inputBg: "#1C1C1E",
  inputBorder: "rgba(255,255,255,0.12)",
  success: "#81C784",
  successBg: "#0D2818",
  warning: "#FFB74D",
  warningBg: "#2E1B00",
  error: "#EF9A9A",
  errorBg: "#2E0A0A",
};

export const radius = { sm: 10, md: 16, lg: 24, pill: 9999 };
export const spacing = { xs: 4, sm: 8, md: 12, lg: 16, xl: 20, xxl: 24 };
