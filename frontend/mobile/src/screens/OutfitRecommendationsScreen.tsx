import { useState } from "react";
import { ScrollView, StyleSheet, Text, View } from "react-native";

import { Outfit, recommendOutfits } from "@/api/recommendations";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { ScreenTitle } from "@/components/Typography";
import { useTheme } from "@/theme/ThemeContext";
import { spacing } from "@/theme/tokens";

export default function OutfitRecommendationsScreen() {
  const { colors } = useTheme();
  const [outfits, setOutfits] = useState<Outfit[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleGenerate() {
    setLoading(true);
    setError(null);
    try {
      const data = await recommendOutfits({});
      setOutfits(data.outfits);
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? "Something went wrong — try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <ScrollView
      style={{ backgroundColor: colors.bg }}
      contentContainerStyle={styles.container}
    >
      <ScreenTitle>Outfits</ScreenTitle>
      <Button title="Suggest an outfit" onPress={handleGenerate} loading={loading} />
      {error && <Text style={[styles.error, { color: colors.error }]}>{error}</Text>}
      {!loading && outfits.length === 0 && (
        <Text style={[styles.empty, { color: colors.textMuted }]}>
          No outfits yet — add a few wardrobe items first, then try again.
        </Text>
      )}
      {outfits.map((outfit) => (
        <Card key={outfit.id} style={styles.card}>
          <View style={styles.cardHeader}>
            {outfit.occasion && (
              <Text style={[styles.occasion, { color: colors.textMuted }]}>{outfit.occasion}</Text>
            )}
            {outfit.relevance_score != null && (
              <Text style={[styles.score, { color: colors.primary }]}>
                {Math.round(outfit.relevance_score * 100)}% match
              </Text>
            )}
          </View>
          <Text style={[styles.pieces, { color: colors.textSubtle }]}>
            {outfit.item_ids.length} pieces
          </Text>
          {outfit.explanation && (
            <Text style={[styles.explanation, { color: colors.text }]}>{outfit.explanation}</Text>
          )}
        </Card>
      ))}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { padding: spacing.xl, gap: spacing.md },
  card: { padding: spacing.lg, gap: spacing.xs },
  cardHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  occasion: { fontSize: 13, fontWeight: "600", textTransform: "capitalize" },
  score: { fontSize: 13, fontWeight: "700" },
  pieces: { fontSize: 12 },
  explanation: { fontSize: 14, marginTop: spacing.xs },
  empty: { textAlign: "center", marginTop: spacing.xxl },
  error: { fontSize: 13 },
});
