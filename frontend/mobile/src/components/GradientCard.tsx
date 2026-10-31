/**
 * GradientCard — simulates a soft gradient card using layered Views.
 * Used throughout the app for premium-looking section cards.
 */
import { useTheme } from "@/theme/ThemeContext";
import { radius } from "@/theme/tokens";
import { ReactNode } from "react";
import { StyleSheet, View, ViewStyle } from "react-native";


import { platformShadow } from "@/utils/platformStyles";
interface GradientCardProps {
  children: ReactNode;
  style?: ViewStyle;
  /** Use "primary" for pink-tinted cards, "surface" for neutral */
  variant?: "primary" | "surface" | "glass";
}

export function GradientCard({ children, style, variant = "surface" }: GradientCardProps) {
  const { colors } = useTheme();

  const bgColor = {
    primary: colors.surface,
    surface: colors.surfaceElevated,
    glass:   "rgba(255,255,255,0.65)",
  }[variant];

  const borderColor = {
    primary: colors.border,
    surface: colors.border,
    glass:   "rgba(255,255,255,0.8)",
  }[variant];

  const accentBar = variant === "primary";

  return (
    <View style={[styles.outer, { backgroundColor: bgColor, borderColor, ...platformShadow(colors.primary)}, style]}>
      {accentBar && (
        <View style={[styles.accentBar, { backgroundColor: colors.primary }]} />
      )}
      <View style={styles.content}>{children}</View>
    </View>
  );
}

const styles = StyleSheet.create({
  outer: {
    borderRadius: radius.lg,
    borderWidth: 1,
    overflow: "hidden",
    ...platformShadow("#17235B", { x: 0, y: 4, opacity: 0.10, radius: 12 }),
  },
  accentBar: {
    height: 3,
    width: "100%",
  },
  content: {
    padding: 18,
  },
});
