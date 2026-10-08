/**
 * PremiumCard — carte élégante avec accent coloré, ombre rose, coins arrondis.
 * Variantes :
 *  • "default"  — fond blanc, bordure rose légère
 *  • "tinted"   — fond rosé, accent barre rose
 *  • "gold"     — accent doré (or tunisien)
 *  • "flat"     — sans ombre, design minimaliste
 */
import { useTheme } from "@/theme/ThemeContext";
import { radius } from "@/theme/tokens";
import { ReactNode } from "react";
import { StyleSheet, View, ViewStyle } from "react-native";


import { platformShadow } from "@/utils/platformStyles";
interface PremiumCardProps {
  children: ReactNode;
  variant?: "default" | "tinted" | "gold" | "flat";
  style?: ViewStyle;
  contentStyle?: ViewStyle;
  accent?: boolean;
}

export function PremiumCard({
  children,
  variant = "default",
  style,
  contentStyle,
  accent = true,
}: PremiumCardProps) {
  const { colors } = useTheme();

  const bg = {
    default: colors.surfaceElevated,
    tinted:  colors.surface,
    gold:    colors.surfaceElevated,
    flat:    colors.surface,
  }[variant];

  const borderColor = {
    default: colors.border,
    tinted:  colors.border,
    gold:    colors.tunisianGold + "55",
    flat:    colors.border,
  }[variant];

  const accentColor = {
    default: colors.primary,
    tinted:  colors.primaryLight,
    gold:    colors.tunisianGold,
    flat:    colors.primary,
  }[variant];

  const shadowProps = variant === "flat" ? {} : {
    ...platformShadow(
      variant === "gold" ? colors.tunisianGold : colors.primary,
      { y: 4, opacity: 0.12, radius: 12 },
    ),
  };

  return (
    <View style={[
      styles.card,
      { backgroundColor: bg, borderColor },
      shadowProps,
      style,
    ]}>
      {accent && (
        <View style={[styles.accentBar, { backgroundColor: accentColor }]} />
      )}
      <View style={[styles.content, contentStyle]}>
        {children}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderRadius: radius.lg,
    borderWidth: 1,
    overflow: "hidden",
  },
  accentBar: {
    height: 3.5,
    width: "100%",
  },
  content: {
    padding: 18,
  },
});
