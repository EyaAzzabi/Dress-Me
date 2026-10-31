/**
 * A thin decorative banner that appears at the top of screens during special
 * periods (Halloween, Christmas, Valentine's, etc.). Hidden during the default
 * pink season to keep the UI clean.
 */
import { useTheme } from "@/theme/ThemeContext";
import { StyleSheet, Text, View } from "react-native";

export function SeasonalBanner() {
  const { season, colors } = useTheme();

  // Only show during a named season, not the default state
  if (season.id === "default") return null;

  return (
    <View style={[styles.banner, { backgroundColor: colors.primary }]}>
      <Text style={[styles.text, { color: colors.primaryContrast }]}>
        {season.emoji}  {season.greeting}  {season.emoji}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  banner: {
    width: "100%",
    paddingVertical: 7,
    alignItems: "center",
  },
  text: {
    fontSize: 13,
    fontWeight: "600",
    letterSpacing: 0.3,
  },
});
