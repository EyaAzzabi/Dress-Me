import * as ImagePicker from "expo-image-picker";
import { useState } from "react";
import { Image, ScrollView, StyleSheet, Text, View } from "react-native";

import { checkPurchase, PurchaseCheckResult } from "@/api/recommendations";
import { uploadPhoto } from "@/api/wardrobe";
import { Button } from "@/components/Button";
import { ScreenTitle, SectionLabel } from "@/components/Typography";
import { VerdictCard } from "@/components/VerdictCard";
import { useTheme } from "@/theme/ThemeContext";
import { radius, spacing } from "@/theme/tokens";

export default function PurchaseCheckScreen() {
  const { colors } = useTheme();
  const [imageUri, setImageUri] = useState<string | null>(null);
  const [result, setResult] = useState<PurchaseCheckResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function pickImage() {
    const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!permission.granted) return;

    const picked = await ImagePicker.launchImageLibraryAsync({ quality: 0.8 });
    if (picked.canceled) return;

    const uri = picked.assets[0].uri;
    setImageUri(uri);
    setResult(null);
    setError(null);
    setLoading(true);
    try {
      const imageUrl = await uploadPhoto(uri);
      const data = await checkPurchase(imageUrl);
      setResult(data);
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? "Something went wrong — try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <ScrollView style={{ backgroundColor: colors.bg }} contentContainerStyle={styles.container}>
      <ScreenTitle>Should I buy this?</ScreenTitle>
      <Button title="Pick a photo" onPress={pickImage} loading={loading} />
      {imageUri && <Image source={{ uri: imageUri }} style={[styles.preview, { borderRadius: radius.lg }]} />}
      {error && <Text style={[styles.error, { color: colors.error }]}>{error}</Text>}

      {result && (
        <>
          <VerdictCard
            verdict={result.verdict}
            explanation={result.explanation}
            compatibilityScore={result.compatibility_score}
          />
          {result.catalog_alternatives.length > 0 && (
            <>
              <SectionLabel style={styles.sectionLabel}>Similar items available</SectionLabel>
              <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.altRow}>
                {result.catalog_alternatives.map((alt, i) => (
                  <View key={i} style={[styles.altCard, { backgroundColor: colors.surface }]}>
                    {alt.image_url && (
                      <Image source={{ uri: alt.image_url }} style={styles.altImage} />
                    )}
                    <Text style={[styles.altName, { color: colors.text }]} numberOfLines={2}>
                      {alt.name}
                    </Text>
                    <Text style={[styles.altMeta, { color: colors.textMuted }]}>
                      {alt.price != null ? `${alt.price}` : ""}
                      {alt.brand ? ` · ${alt.brand}` : ""}
                    </Text>
                  </View>
                ))}
              </ScrollView>
            </>
          )}
        </>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { padding: spacing.xl, gap: spacing.md },
  preview: { width: "100%", height: 240, backgroundColor: "#eee" },
  error: { fontSize: 13 },
  sectionLabel: { marginTop: spacing.sm },
  altRow: { gap: spacing.md },
  altCard: { width: 140, borderRadius: radius.md, padding: spacing.sm },
  altImage: { width: "100%", height: 100, borderRadius: radius.sm, marginBottom: spacing.xs },
  altName: { fontSize: 13, fontWeight: "600" },
  altMeta: { fontSize: 12, marginTop: 2 },
});
