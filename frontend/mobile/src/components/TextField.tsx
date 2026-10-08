import { StyleSheet, TextInput, TextInputProps } from "react-native";

import { useTheme } from "@/theme/ThemeContext";
import { radius } from "@/theme/tokens";

export function TextField(props: TextInputProps) {
  const { colors } = useTheme();
  return (
    <TextInput
      placeholderTextColor={colors.textSubtle}
      style={[
        styles.field,
        {
          backgroundColor: colors.inputBg,
          color: colors.text,
          borderColor: colors.inputBorder,
        },
      ]}
      {...props}
    />
  );
}

const styles = StyleSheet.create({
  field: {
    width: "100%",
    paddingVertical: 16,
    paddingHorizontal: 18,
    borderRadius: radius.md,
    fontSize: 16,
    borderWidth: 1.5,
  },
});
