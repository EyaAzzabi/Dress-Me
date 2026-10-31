import { StyleSheet, Text, View } from "react-native";

import { CostPerWear, formatTnd } from "@/api/purchase";
import { useTheme } from "@/theme/ThemeContext";
import { radius, spacing } from "@/theme/tokens";

const LABELS: Record<CostPerWear["label"], string> = {
  excellent: "Excellent rapport usage / prix",
  correct: "Rapport usage / prix correct",
  eleve: "Cher à l'usage",
};

export function CostPerWearCard({ cpw }: { cpw: CostPerWear }) {
  const { colors } = useTheme();
  const tone = cpw.label === "excellent" ? colors.success : cpw.label === "correct" ? colors.warning : colors.error;
  const toneBg = cpw.label === "excellent" ? colors.successBg : cpw.label === "correct" ? colors.warningBg : colors.errorBg;

  return (
    <View style={[styles.root, { backgroundColor: toneBg, borderColor: tone }]}>
      <View style={styles.left}>
        <Text style={[styles.kicker, { color: tone }]}>COÛT PAR PORT</Text>
        <Text style={[styles.value, { color: colors.text }]}>
          {formatTnd(cpw.cost_per_wear)}
          <Text style={[styles.unit, { color: colors.textMuted }]}> / port</Text>
        </Text>
        <Text style={[styles.label, { color: tone }]}>{LABELS[cpw.label]}</Text>
      </View>
      <View style={[styles.wears, { borderColor: tone }]}>
        <Text style={[styles.wearsValue, { color: colors.text }]}>≈ {cpw.wears_per_year}</Text>
        <Text style={[styles.wearsLabel, { color: colors.textMuted }]}>ports / an</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    flexDirection: "row",
    alignItems: "center",
    padding: spacing.lg,
    borderRadius: radius.lg,
    borderWidth: 1,
    gap: spacing.md,
  },
  left: { flex: 1, gap: 2 },
  kicker: { fontSize: 11, fontWeight: "900", letterSpacing: 1 },
  value: { fontSize: 26, fontWeight: "900" },
  unit: { fontSize: 14, fontWeight: "600" },
  label: { fontSize: 12, fontWeight: "700" },
  wears: { alignItems: "center", paddingHorizontal: spacing.md, paddingVertical: spacing.sm, borderRadius: radius.md, borderWidth: 1 },
  wearsValue: { fontSize: 20, fontWeight: "900" },
  wearsLabel: { fontSize: 11 },
});
