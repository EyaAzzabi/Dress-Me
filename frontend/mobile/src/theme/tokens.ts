// ─────────────────────────────────────────────────────────────
//  DressMe Design Tokens — Thème Tunisien Rose Premium
//  Palette inspirée des médinas tunisiennes :
//  rose fard (#F8A4C8) · blanc chéchaouen (#FFF8FA)
//  navy profond (#1A237E) · or arabesque (#C9984A)
// ─────────────────────────────────────────────────────────────

export interface ColorTokens {
  bg: string;
  bgAlt: string;
  surface: string;
  surfaceElevated: string;
  border: string;
  borderStrong: string;
  text: string;
  textMuted: string;
  textSubtle: string;
  primary: string;
  primaryLight: string;
  primaryDark: string;
  primaryContrast: string;
  accent: string;           // or tunisien
  accentSoft: string;
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
  inputFocusBorder: string;
  success: string;
  successBg: string;
  warning: string;
  warningBg: string;
  error: string;
  errorBg: string;
  gradientStart: string;
  gradientMid: string;
  gradientEnd: string;
  // Tunisian specific
  tunisianGold: string;
  tunisianNavy: string;
}

export const lightColors: ColorTokens = {
  // Fonds
  bg:              "#FFF8FA",
  bgAlt:           "#FFF0F5",
  surface:         "#FFE8F3",
  surfaceElevated: "#FFFFFF",

  // Bordures
  border:          "#F5C2D8",
  borderStrong:    "#EC93BB",

  // Textes
  text:            "#1A0A14",
  textMuted:       "rgba(80,10,40,0.55)",
  textSubtle:      "rgba(80,10,40,0.35)",

  // Rose primaire (plus chaud, plus élégant)
  primary:         "#E8176A",
  primaryLight:    "#FF6BA8",
  primaryDark:     "#B50050",
  primaryContrast: "#FFFFFF",

  // Or tunisien comme accent
  accent:          "#C9984A",
  accentSoft:      "#F5DEB8",

  // Pills
  pillBg:          "#FFD6EC",
  pillActiveBg:    "#E8176A",
  pillText:        "#A01050",
  pillActiveText:  "#FFFFFF",

  // Tab bar
  tabBg:           "#FFFFFF",
  tabBorder:       "#F5C2D8",
  tabActive:       "#E8176A",
  tabInactive:     "#C0839E",

  // Inputs
  inputBg:         "#FFF0F7",
  inputBorder:     "#F5C2D8",
  inputFocusBorder:"#E8176A",

  // États
  success:         "#2E7D32",
  successBg:       "#F0FBF0",
  warning:         "#E65100",
  warningBg:       "#FFF8F0",
  error:           "#C62828",
  errorBg:         "#FFF0F0",

  // Dégradés
  gradientStart:   "#FFADD5",
  gradientMid:     "#FF78B8",
  gradientEnd:     "#E8176A",

  // Spécifique Tunisie
  tunisianGold:    "#C9984A",
  tunisianNavy:    "#1A237E",
};

export const darkColors: ColorTokens = {
  bg:              "#150010",
  bgAlt:           "#1E001A",
  surface:         "#2A0020",
  surfaceElevated: "#380028",

  border:          "rgba(232,23,106,0.20)",
  borderStrong:    "rgba(232,23,106,0.40)",

  text:            "#FFE8F4",
  textMuted:       "rgba(255,180,220,0.58)",
  textSubtle:      "rgba(255,180,220,0.35)",

  primary:         "#FF4DA6",
  primaryLight:    "#FF80C4",
  primaryDark:     "#CC0077",
  primaryContrast: "#FFFFFF",

  accent:          "#E0AA5A",
  accentSoft:      "#4A3010",

  pillBg:          "#380028",
  pillActiveBg:    "#FF4DA6",
  pillText:        "#FF9FD0",
  pillActiveText:  "#FFFFFF",

  tabBg:           "#150010",
  tabBorder:       "rgba(232,23,106,0.15)",
  tabActive:       "#FF4DA6",
  tabInactive:     "#8A4068",

  inputBg:         "#2A0020",
  inputBorder:     "rgba(232,23,106,0.25)",
  inputFocusBorder:"#FF4DA6",

  success:         "#81C784",
  successBg:       "#0A2010",
  warning:         "#FFB74D",
  warningBg:       "#2A1500",
  error:           "#EF9A9A",
  errorBg:         "#2A0808",

  gradientStart:   "#6B0040",
  gradientMid:     "#A00060",
  gradientEnd:     "#FF4DA6",

  tunisianGold:    "#E0AA5A",
  tunisianNavy:    "#3949AB",
};

export const radius = {
  xs:   6,
  sm:   12,
  md:   18,
  lg:   26,
  xl:   34,
  pill: 9999,
};

export const spacing = {
  xs:   4,
  sm:   8,
  md:   14,
  lg:   18,
  xl:   22,
  xxl:  28,
  xxxl: 36,
};

// Ombres réutilisables
export const shadow = {
  sm: {
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.08,
    shadowRadius: 6,
    elevation: 2,
  },
  md: {
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.12,
    shadowRadius: 12,
    elevation: 4,
  },
  lg: {
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.18,
    shadowRadius: 20,
    elevation: 8,
  },
};
