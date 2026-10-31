import { ActivityIndicator, Pressable, StyleSheet, Text } from "react-native";

import { useTheme } from "@/theme/ThemeContext";
import { radius } from "@/theme/tokens";

type Variant = "primary" | "secondary" | "small" | "ghost" | "logout";

interface ButtonProps {
  title: string;
  onPress: () => void;
  variant?: Variant;
  disabled?: boolean;
  loading?: boolean;
  style?: object;
}

export function Button({ title, onPress, variant = "primary", disabled, loading, style }: ButtonProps) {
  const { colors } = useTheme();
  const isDisabled = disabled || loading;

  const variantStyle = {
    primary: { backgroundColor: colors.primary, borderColor: "transparent" },
    secondary: { backgroundColor: "transparent", borderColor: colors.borderStrong, borderWidth: 1.5 },
    small: { backgroundColor: colors.primary, borderColor: "transparent", paddingVertical: 10, paddingHorizontal: 20 },
    ghost: { backgroundColor: "transparent", borderColor: "transparent" },
    logout: { backgroundColor: "transparent", borderColor: colors.error, borderWidth: 1.5 },
  }[variant];

  const textColor = {
    primary: colors.primaryContrast,
    secondary: colors.text,
    small: colors.primaryContrast,
    ghost: colors.textMuted,
    logout: colors.error,
  }[variant];

  const fontSize = variant === "small" || variant === "ghost" ? 13 : 16;

  return (
    <Pressable
      onPress={onPress}
      disabled={isDisabled}
      style={({ pressed }) => [
        styles.base,
        variantStyle,
        variant === "small" || variant === "ghost" ? styles.inline : styles.full,
        { opacity: isDisabled ? 0.5 : pressed ? 0.85 : 1 },
        style,
      ]}
    >
      {loading ? (
        <ActivityIndicator color={textColor} />
      ) : (
        <Text style={[styles.text, { color: textColor, fontSize }]}>{title}</Text>
      )}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  base: {
    borderRadius: radius.pill,
    alignItems: "center",
    justifyContent: "center",
  },
  full: { width: "100%", paddingVertical: 16 },
  inline: { paddingVertical: 10, paddingHorizontal: 20, alignSelf: "flex-start" },
  text: { fontWeight: "600" },
});
