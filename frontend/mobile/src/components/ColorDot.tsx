import { StyleSheet, View } from "react-native";

import { useTheme } from "@/theme/ThemeContext";

interface ColorDotProps {
  color: string;
  size?: number;
  selected?: boolean;
}

export function ColorDot({ color, size = 28, selected }: ColorDotProps) {
  const { colors } = useTheme();
  return (
    <View
      style={[
        styles.dot,
        {
          width: size,
          height: size,
          borderRadius: size / 2,
          backgroundColor: color,
          borderColor: selected ? colors.primary : colors.border,
          borderWidth: selected ? 2.5 : 1,
        },
      ]}
    />
  );
}

const styles = StyleSheet.create({
  dot: {},
});
