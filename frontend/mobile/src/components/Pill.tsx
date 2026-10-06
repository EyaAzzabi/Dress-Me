import { Pressable, StyleSheet, Text } from "react-native";

import { useTheme } from "@/theme/ThemeContext";
import { radius } from "@/theme/tokens";

interface PillProps {
  label: string;
  active?: boolean;
  onPress?: () => void;
}

export function Pill({ label, active, onPress }: PillProps) {
  const { colors } = useTheme();
  return (
    <Pressable
      onPress={onPress}
      style={[
        styles.pill,
        { backgroundColor: active ? colors.pillActiveBg : colors.pillBg },
      ]}
    >
      <Text style={[styles.text, { color: active ? colors.pillActiveText : colors.pillText }]}>
        {label}
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  pill: {
    paddingVertical: 8,
    paddingHorizontal: 18,
    borderRadius: radius.pill,
  },
  text: { fontSize: 13, fontWeight: "500" },
});
