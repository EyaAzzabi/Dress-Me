import { useEffect, useRef } from "react";
import { Animated, StyleSheet, Text, View } from "react-native";

import { PurchaseFactor, Verdict } from "@/api/purchase";
import { useTheme } from "@/theme/ThemeContext";
import { radius, spacing } from "@/theme/tokens";
import { platformShadow } from "@/utils/platformStyles";

const VERDICT_LABEL: Record<Verdict, string> = {
  recommended: "Bon achat",
  think_twice: "À réfléchir",
  not_recommended: "Pas convaincant",
};

const VERDICT_ICON: Record<Verdict, string> = {
  recommended: "✓",
  think_twice: "!",
  not_recommended: "✕",
};

const FACTOR_ICON: Record<string, string> = {
  versatility: "✦",
  uniqueness: "◆",
  style_fit: "❀",
  price: "₸",
};

interface Props {
  verdict: Verdict;
  score: number;
  explanation: string;
  factors: PurchaseFactor[];
}

export function ScoreVerdictCard({ verdict, score, explanation, factors }: Props) {
  const { colors } = useTheme();
  const tone = {
    recommended: colors.success,
    think_twice: colors.warning,
    not_recommended: colors.error,
  }[verdict];
  const toneBg = {
    recommended: colors.successBg,
    think_twice: colors.warningBg,
    not_recommended: colors.errorBg,
  }[verdict];

  const fill = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    fill.setValue(0);
    Animated.timing(fill, { toValue: score, duration: 900, useNativeDriver: false }).start();
  }, [score, fill]);

  return (
    <View style={[styles.card, { backgroundColor: colors.surfaceElevated, borderColor: colors.border },
      platformShadow(tone, { y: 6, opacity: 0.18, radius: 18 })]}>
      <View style={styles.header}>
        <View style={[styles.ring, { borderColor: tone, backgroundColor: toneBg }]}>
          <Text style={[styles.scoreValue, { color: tone }]}>{score}</Text>
          <Text style={[styles.scoreMax, { color: colors.textMuted }]}>/100</Text>
        </View>
        <View style={styles.headerText}>
          <View style={[styles.badge, { backgroundColor: tone }]}>
            <Text style={styles.badgeText}>{VERDICT_ICON[verdict]}  {VERDICT_LABEL[verdict]}</Text>
          </View>
          <Text style={[styles.explanation, { color: colors.text }]}>{explanation}</Text>
        </View>
      </View>

      <View style={[styles.track, { backgroundColor: colors.surface }]}>
        <Animated.View
          style={[styles.trackFill, {
            backgroundColor: tone,
            width: fill.interpolate({ inputRange: [0, 100], outputRange: ["0%", "100%"] }),
          }]}
        />
      </View>

      {factors.length > 0 && (
        <View style={styles.factors}>
          <Text style={[styles.factorsTitle, { color: colors.textMuted }]}>POURQUOI CE SCORE</Text>
          {factors.map((factor) => (
            <View key={factor.key} style={styles.factor}>
              <View style={styles.factorHead}>
                <Text style={[styles.factorLabel, { color: colors.text }]}>
                  <Text style={{ color: colors.accent }}>{FACTOR_ICON[factor.key] ?? "•"}  </Text>
                  {factor.label}
                </Text>
                <Text style={[styles.factorScore, { color: colors.primary }]}>
                  {Math.round(factor.score * 100)}
                  <Text style={[styles.factorWeight, { color: colors.textSubtle }]}>
                    {"  "}poids {Math.round(factor.weight * 100)} %
                  </Text>
                </Text>
              </View>
              <View style={[styles.factorTrack, { backgroundColor: colors.surface }]}>
                <View style={[styles.factorFill, {
                  backgroundColor: colors.primary,
                  width: `${Math.max(3, Math.round(factor.score * 100))}%`,
                }]} />
              </View>
              <Text style={[styles.factorDetail, { color: colors.textMuted }]}>{factor.detail}</Text>
            </View>
          ))}
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  card: { borderRadius: radius.lg, borderWidth: 1, padding: spacing.xl, gap: spacing.lg },
  header: { flexDirection: "row", alignItems: "center", gap: spacing.lg },
  ring: {
    width: 96, height: 96, borderRadius: 48, borderWidth: 6,
    alignItems: "center", justifyContent: "center",
  },
  scoreValue: { fontSize: 32, fontWeight: "800", lineHeight: 36 },
  scoreMax: { fontSize: 12, fontWeight: "600" },
  headerText: { flex: 1, gap: spacing.sm },
  badge: { alignSelf: "flex-start", paddingHorizontal: 12, paddingVertical: 5, borderRadius: radius.pill },
  badgeText: { color: "#FFFFFF", fontSize: 13, fontWeight: "800", letterSpacing: 0.3 },
  explanation: { fontSize: 14, lineHeight: 20 },
  track: { height: 8, borderRadius: radius.pill, overflow: "hidden" },
  trackFill: { height: "100%", borderRadius: radius.pill },
  factors: { gap: spacing.md },
  factorsTitle: { fontSize: 11, fontWeight: "800", letterSpacing: 1.2 },
  factor: { gap: 5 },
  factorHead: { flexDirection: "row", justifyContent: "space-between", alignItems: "baseline" },
  factorLabel: { fontSize: 14, fontWeight: "700" },
  factorScore: { fontSize: 15, fontWeight: "800" },
  factorWeight: { fontSize: 11, fontWeight: "500" },
  factorTrack: { height: 6, borderRadius: radius.pill, overflow: "hidden" },
  factorFill: { height: "100%", borderRadius: radius.pill },
  factorDetail: { fontSize: 12, lineHeight: 16 },
});
