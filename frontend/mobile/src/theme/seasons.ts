/**
 * Seasonal / festive theme engine.
 * Base colour is always pink (DressMe brand). Each period adds its own
 * accent palette ON TOP of the pink base, so the brand identity is preserved.
 */

export type SeasonId =
  | "default"
  | "valentine"
  | "spring"
  | "summer"
  | "halloween"
  | "christmas"
  | "newYear"
  | "ramadan"
  | "eid";

export interface SeasonalOverride {
  id: SeasonId;
  label: string;
  /** Emoji shown next to the DressMe logo */
  emoji: string;
  /** Greeting shown on the home / login screen */
  greeting: string;
  primary: string;
  primaryContrast: string;
  accent: string;
  bg: string;
  surface: string;
  pillActiveBg: string;
  pillActiveText: string;
  tabActive: string;
  /** Optional gradient stops for decorative backgrounds */
  gradientStart: string;
  gradientEnd: string;
}

/** Returns the active season for a given Date. */
export function getActiveSeason(now: Date = new Date()): SeasonalOverride {
  const month = now.getMonth() + 1; // 1-based
  const day = now.getDate();

  // --- Christmas (Dec 20 – Jan 5) ---
  if ((month === 12 && day >= 20) || (month === 1 && day <= 5)) {
    return {
      id: "christmas",
      label: "Christmas",
      emoji: "🎄",
      greeting: "Happy Holidays! 🎄",
      primary: "#C0155A",          // deep crimson-pink
      primaryContrast: "#FFFFFF",
      accent: "#8B0000",           // dark red
      bg: "#FFF0F5",
      surface: "#FFE4EE",
      pillActiveBg: "#C0155A",
      pillActiveText: "#FFFFFF",
      tabActive: "#C0155A",
      gradientStart: "#FFB6C1",
      gradientEnd: "#C0155A",
    };
  }

  // --- New Year (Jan 1 – Jan 10) ---
  if (month === 1 && day <= 10) {
    return {
      id: "newYear",
      label: "New Year",
      emoji: "✨",
      greeting: "Happy New Year! ✨",
      primary: "#E91E8C",
      primaryContrast: "#FFFFFF",
      accent: "#FF6EC7",
      bg: "#FFF5FB",
      surface: "#FFE8F5",
      pillActiveBg: "#E91E8C",
      pillActiveText: "#FFFFFF",
      tabActive: "#E91E8C",
      gradientStart: "#FF9FDB",
      gradientEnd: "#E91E8C",
    };
  }

  // --- Valentine's Day (Feb 10 – Feb 16) ---
  if (month === 2 && day >= 10 && day <= 16) {
    return {
      id: "valentine",
      label: "Valentine's Day",
      emoji: "💖",
      greeting: "Happy Valentine's! 💖",
      primary: "#E91E8C",
      primaryContrast: "#FFFFFF",
      accent: "#FF4081",
      bg: "#FFF0F5",
      surface: "#FFD6E8",
      pillActiveBg: "#E91E8C",
      pillActiveText: "#FFFFFF",
      tabActive: "#E91E8C",
      gradientStart: "#FFB3D4",
      gradientEnd: "#E91E8C",
    };
  }

  // --- Ramadan (approximate — changes yearly; using mid-March as a proxy for 2025/2026) ---
  // 2026: Feb 17 – Mar 19 | 2027: Feb 6 – Mar 8
  if (
    (month === 2 && day >= 17) ||
    (month === 3 && day <= 19)
  ) {
    return {
      id: "ramadan",
      label: "Ramadan",
      emoji: "🌙",
      greeting: "Ramadan Kareem 🌙",
      primary: "#B5006E",
      primaryContrast: "#FFFFFF",
      accent: "#FFD700",           // gold crescent accent
      bg: "#FFF5FB",
      surface: "#FFE4F2",
      pillActiveBg: "#B5006E",
      pillActiveText: "#FFFFFF",
      tabActive: "#B5006E",
      gradientStart: "#FFB6D9",
      gradientEnd: "#B5006E",
    };
  }

  // --- Eid (Apr 1 – Apr 5 approximate) ---
  if (month === 4 && day <= 5) {
    return {
      id: "eid",
      label: "Eid Mubarak",
      emoji: "🌟",
      greeting: "Eid Mubarak! 🌟",
      primary: "#AD1476",
      primaryContrast: "#FFFFFF",
      accent: "#FFD700",
      bg: "#FFF5FB",
      surface: "#FFE0F0",
      pillActiveBg: "#AD1476",
      pillActiveText: "#FFFFFF",
      tabActive: "#AD1476",
      gradientStart: "#FFADD6",
      gradientEnd: "#AD1476",
    };
  }

  // --- Spring (Mar 20 – Jun 20) ---
  if ((month === 3 && day >= 20) || month === 4 || month === 5 || (month === 6 && day <= 20)) {
    return {
      id: "spring",
      label: "Spring",
      emoji: "🌸",
      greeting: "Spring is here! 🌸",
      primary: "#E91E8C",
      primaryContrast: "#FFFFFF",
      accent: "#FF80B5",
      bg: "#FFF5FA",
      surface: "#FFE8F3",
      pillActiveBg: "#E91E8C",
      pillActiveText: "#FFFFFF",
      tabActive: "#E91E8C",
      gradientStart: "#FFB6D9",
      gradientEnd: "#FF7BBE",
    };
  }

  // --- Summer (Jun 21 – Sep 21) ---
  if ((month === 6 && day >= 21) || month === 7 || month === 8 || (month === 9 && day <= 21)) {
    return {
      id: "summer",
      label: "Summer",
      emoji: "☀️",
      greeting: "Sunny vibes! ☀️",
      primary: "#D81B60",
      primaryContrast: "#FFFFFF",
      accent: "#FF6FB0",
      bg: "#FFF8FA",
      surface: "#FFEAF3",
      pillActiveBg: "#D81B60",
      pillActiveText: "#FFFFFF",
      tabActive: "#D81B60",
      gradientStart: "#FFB6CF",
      gradientEnd: "#FF5999",
    };
  }

  // --- Halloween (Oct 15 – Nov 2) ---
  if ((month === 10 && day >= 15) || (month === 11 && day <= 2)) {
    return {
      id: "halloween",
      label: "Halloween",
      emoji: "🎃",
      greeting: "Spooky season! 🎃",
      primary: "#C2185B",          // deep pink (brand) replaces orange
      primaryContrast: "#FFFFFF",
      accent: "#FF6D00",           // pumpkin orange as accent only
      bg: "#FFF0F5",
      surface: "#FFE0EC",
      pillActiveBg: "#C2185B",
      pillActiveText: "#FFFFFF",
      tabActive: "#C2185B",
      gradientStart: "#FFB6C8",
      gradientEnd: "#C2185B",
    };
  }

  // --- Default (year-round pink) ---
  return {
    id: "default",
    label: "DressMe",
    emoji: "👗",
    greeting: "Hello! 👗",
    primary: "#E91E8C",
    primaryContrast: "#FFFFFF",
    accent: "#FF80B5",
    bg: "#FFF5FA",
    surface: "#FFE8F3",
    pillActiveBg: "#E91E8C",
    pillActiveText: "#FFFFFF",
    tabActive: "#E91E8C",
    gradientStart: "#FFB6D9",
    gradientEnd: "#E91E8C",
  };
}
