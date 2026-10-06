import { StyleSheet, Text, View } from "react-native";

import { useTheme } from "@/theme/ThemeContext";
import { radius, spacing } from "@/theme/tokens";

export type Verdict = "recommended" | "think_twice" | "not_recommended";

const VERDICT_LABEL: Record<Verdict, string> = {
  recommended: "Recommended purchase",
  think_twice: "Think twice",
  not_recommended: "Not recommended",
};

const VERDICT_ICON: Record<Verdict, string> = {
  recommended: "✓",
  think_twice: "!",
  not_recommended: "✕",
};

interface VerdictCardProps {
  verdict: Verdict;
  explanation: string;
  compatibilityScore?: number;
}

export function VerdictCard({ verdict, explanation, compatibilityScore }: VerdictCardProps) {
  const { colors } = useTheme();

  const tone = {
    recommended: { bg: colors.successBg, fg: colors.success },
    think_twice: { bg: colors.warningBg, fg: colors.warning },
    not_recommended: { bg: colors.errorBg, fg: colors.error },
  }[verdict];

  return (
    <View style={[styles.card, { backgroundColor: tone.bg }]}>
      <View style={[styles.iconCircle, { backgroundColor: tone.fg }]}>
        <Text style={styles.icon}>{VERDICT_ICON[verdict]}</Text>
      </View>
      <Text style={[styles.label, { color: tone.fg }]}>{VERDICT_LABEL[verdict]}</Text>
      <Text style={[styles.explanation, { color: colors.text }]}>{explanation}</Text>
      {compatibilityScore != null && (
        <Text style={[styles.score, { color: colors.textMuted }]}>
          Compatibility: {Math.round(compatibilityScore * 100)}%
        </Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderRadius: radius.lg,
    padding: spacing.xl,
    alignItems: "center",
    gap: spacing.sm,
  },
  iconCircle: {
    width: 48,
    height: 48,
    borderRadius: 24,
    alignItems: "center",
    justifyContent: "center",
  },
  icon: { color: "#fff", fontSize: 22, fontWeight: "700" },
  label: { fontSize: 18, fontWeight: "700" },
  explanation: { fontSize: 14, textAlign: "center" },
  score: { fontSize: 13, marginTop: spacing.xs },
});
