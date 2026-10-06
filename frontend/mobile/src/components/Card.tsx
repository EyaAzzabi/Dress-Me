import { ReactNode } from "react";
import { StyleSheet, View } from "react-native";

import { useTheme } from "@/theme/ThemeContext";
import { radius } from "@/theme/tokens";

export function Card({ children, style }: { children: ReactNode; style?: object }) {
  const { colors } = useTheme();
  return <View style={[styles.card, { backgroundColor: colors.surface }, style]}>{children}</View>;
}

const styles = StyleSheet.create({
  card: { borderRadius: radius.lg, overflow: "hidden" },
});
