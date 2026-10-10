import { StyleSheet, Text, View } from "react-native";

import { PriceInsight, PriceLabel } from "@/api/purchase";
import { useTheme } from "@/theme/ThemeContext";
import { radius, spacing } from "@/theme/tokens";

const LABEL_TEXT: Record<PriceLabel, string> = {
  bon_prix: "Bon prix",
  prix_marche: "Prix du marché",
  cher: "Plus cher que le marché",
};

function position(value: number, min: number, max: number) {
  if (max <= min) return 50;
  return Math.min(100, Math.max(0, ((value - min) / (max - min)) * 100));
}

export function PriceInsightCard({ insight }: { insight: PriceInsight }) {
  const { colors } = useTheme();
  const { market_min: min, market_max: max, market_median: median, price, label } = insight;
  const labelColor = label === "bon_prix" ? colors.success : label === "cher" ? colors.error : colors.accent;

  return (
    <View style={[styles.card, { backgroundColor: colors.surfaceElevated, borderColor: colors.border }]}>
      <View style={styles.header}>
        <Text style={[styles.title, { color: colors.text }]}>Prix sur le marché tunisien</Text>
        {label && (
          <View style={[styles.pill, { backgroundColor: labelColor }]}>
            <Text style={styles.pillText}>{LABEL_TEXT[label]}</Text>
          </View>
        )}
      </View>
      <Text style={[styles.subtitle, { color: colors.textMuted }]}>
        D'après les {insight.sample_size} articles les plus ressemblants de 9 marques tunisiennes
      </Text>

      <View style={styles.rangeWrap}>
        <View style={[styles.range, { backgroundColor: colors.accentSoft }]} />
        <View style={[styles.medianTick, { left: `${position(median, min, max)}%`, backgroundColor: colors.accent }]} />
        {price != null && (
          <View style={[styles.priceDot, { left: `${position(price, min, max)}%`, backgroundColor: colors.primary,
            borderColor: colors.surfaceElevated }]} />
        )}
      </View>

      <View style={styles.legend}>
        <Text style={[styles.legendText, { color: colors.textMuted }]}>{min.toFixed(0)} TND</Text>
        <Text style={[styles.legendText, { color: colors.accent, fontWeight: "800" }]}>
          médiane {median.toFixed(0)} TND
        </Text>
        <Text style={[styles.legendText, { color: colors.textMuted }]}>{max.toFixed(0)} TND</Text>
      </View>

      {price != null && insight.percentile != null && (
        <Text style={[styles.verdict, { color: colors.text }]}>
          Ton prix (<Text style={{ color: colors.primary, fontWeight: "800" }}>{price.toFixed(0)} TND</Text>) est plus
          élevé que {Math.round(insight.percentile * 100)} % des articles similaires.
        </Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  card: { borderRadius: radius.lg, borderWidth: 1, padding: spacing.lg, gap: spacing.sm },
  header: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: spacing.sm },
  title: { fontSize: 16, fontWeight: "800", flexShrink: 1 },
  subtitle: { fontSize: 12 },
  pill: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: radius.pill },
  pillText: { color: "#FFFFFF", fontSize: 11, fontWeight: "800" },
  rangeWrap: { height: 22, justifyContent: "center", marginTop: spacing.sm },
  range: { height: 8, borderRadius: radius.pill },
  medianTick: { position: "absolute", width: 3, height: 18, borderRadius: 2, marginLeft: -1.5 },
  priceDot: { position: "absolute", width: 20, height: 20, borderRadius: 10, borderWidth: 3, marginLeft: -10 },
  legend: { flexDirection: "row", justifyContent: "space-between" },
  legendText: { fontSize: 11 },
  verdict: { fontSize: 13, lineHeight: 18, marginTop: spacing.xs },
});
