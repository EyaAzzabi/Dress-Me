import { ReactNode } from "react";
import { StyleSheet, Text } from "react-native";

import { useTheme } from "@/theme/ThemeContext";

export function ScreenTitle({ children, style }: { children: ReactNode; style?: object }) {
  const { colors } = useTheme();
  return <Text style={[styles.title, { color: colors.text }, style]}>{children}</Text>;
}

export function ScreenSubtitle({ children, style }: { children: ReactNode; style?: object }) {
  const { colors } = useTheme();
  return <Text style={[styles.subtitle, { color: colors.textMuted }, style]}>{children}</Text>;
}

export function SectionLabel({ children, style }: { children: ReactNode; style?: object }) {
  const { colors } = useTheme();
  return <Text style={[styles.label, { color: colors.textSubtle }, style]}>{children}</Text>;
}

const styles = StyleSheet.create({
  title: { fontSize: 26, fontWeight: "700" },
  subtitle: { fontSize: 15, marginTop: 4 },
  label: {
    fontSize: 12,
    fontWeight: "600",
    textTransform: "uppercase",
    letterSpacing: 0.6,
  },
});
