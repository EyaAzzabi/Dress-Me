import * as ImagePicker from "expo-image-picker";
import { useState } from "react";
import {
    ActivityIndicator,
    Image,
    Pressable,
    ScrollView,
    StyleSheet,
    Text,
    View,
} from "react-native";


import { platformShadow } from "@/utils/platformStyles";
import { checkPurchase, PurchaseCheckResult } from "@/api/recommendations";
import { uploadPhoto } from "@/api/wardrobe";
import { TunisianPhotoHero } from "@/components/TunisianPhotoHero";
import { VerdictCard } from "@/components/VerdictCard";
import { useTheme } from "@/theme/ThemeContext";
import { radius, spacing } from "@/theme/tokens";

export default function PurchaseCheckScreen() {
  const { colors } = useTheme();
  const [imageUri, setImageUri] = useState<string | null>(null);
  const [result, setResult]     = useState<PurchaseCheckResult | null>(null);
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState<string | null>(null);

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
    <ScrollView
      style={{ backgroundColor: colors.bg }}
      contentContainerStyle={styles.root}
      showsVerticalScrollIndicator={false}
    >
      <TunisianPhotoHero
        icon="✧"
        title="J’achète ou pas ?"
        subtitle="Fais le bon choix pour ton dressing"
        image="wardrobe"
      />

      <View style={styles.content}>
        {/* Upload zone */}
        <Pressable
          onPress={loading ? undefined : pickImage}
          style={[styles.uploadZone, {
            backgroundColor: colors.surface,
            borderColor: imageUri ? colors.primary : colors.border,
            ...platformShadow(colors.primary),
          }]}
        >
          {loading ? (
            <View style={styles.uploadInner}>
              <ActivityIndicator color={colors.primary} size="large" />
              <Text style={[styles.uploadHint, { color: colors.textMuted }]}>Analysing…</Text>
            </View>
          ) : imageUri ? (
            <>
              <Image source={{ uri: imageUri }} style={styles.uploadImage} />
              <View style={[styles.retakeBadge, { backgroundColor: colors.primary }]}>
                <Text style={styles.retakeText}>Change photo ✎</Text>
              </View>
            </>
          ) : (
            <View style={styles.uploadInner}>
              <Text style={styles.uploadIcon}>📸</Text>
              <Text style={[styles.uploadTitle, { color: colors.text }]}>Upload an item photo</Text>
              <Text style={[styles.uploadHint, { color: colors.textMuted }]}>
                Take or pick a photo of the clothing item you're considering buying.
              </Text>
            </View>
          )}
        </Pressable>

        {!imageUri && (
          <Pressable
            onPress={pickImage}
            style={[styles.pickBtn, { backgroundColor: colors.primary, ...platformShadow(colors.primary)}]}
          >
            <Text style={styles.pickBtnIcon}>📂</Text>
            <Text style={styles.pickBtnText}>Choose from gallery</Text>
          </Pressable>
        )}

        {error && (
          <View style={[styles.errorBox, { backgroundColor: colors.errorBg, borderColor: colors.error }]}>
            <Text style={[styles.errorText, { color: colors.error }]}>⚠ {error}</Text>
          </View>
        )}

        {/* ── Verdict ── */}
        {result && (
          <>
            <VerdictCard
              verdict={result.verdict}
              explanation={result.explanation}
              compatibilityScore={result.compatibility_score}
            />

            {result.catalog_alternatives.length > 0 && (
              <>
                <View style={styles.altHeader}>
                  <Text style={[styles.altTitle, { color: colors.text }]}>Similar items available</Text>
                  <Text style={[styles.altCount, { color: colors.textMuted }]}>
                    {result.catalog_alternatives.length} found
                  </Text>
                </View>

                <ScrollView
                  horizontal
                  showsHorizontalScrollIndicator={false}
                  contentContainerStyle={styles.altRow}
                >
                  {result.catalog_alternatives.map((alt, i) => (
                    <View key={i} style={[styles.altCard, {
                      backgroundColor: colors.surfaceElevated,
                      borderColor: colors.border,
                      ...platformShadow(colors.primary),
                    }]}>
                      {alt.image_url && (
                        <Image source={{ uri: alt.image_url }} style={styles.altImage} />
                      )}
                      <View style={styles.altBody}>
                        <Text style={[styles.altName, { color: colors.text }]} numberOfLines={2}>
                          {alt.name}
                        </Text>
                        {(alt.price != null || alt.brand) && (
                          <Text style={[styles.altMeta, { color: colors.primary }]}>
                            {alt.price != null ? `${alt.price} TND` : ""}
                            {alt.brand ? `  ·  ${alt.brand}` : ""}
                          </Text>
                        )}
                      </View>
                    </View>
                  ))}
                </ScrollView>
              </>
            )}
          </>
        )}
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  root: { paddingBottom: 40 },

  hero: {
    paddingTop: 50,
    paddingBottom: 44,
    overflow: "hidden",
    position: "relative",
  },
  blob1: { position: "absolute", width: 200, height: 200, borderRadius: 100, top: -60, right: -40, opacity: 0.35 },
  heroContent: { alignItems: "center", gap: 4, zIndex: 2 },
  heroEmoji:   { fontSize: 40 },
  heroTitle:   { fontSize: 26, fontWeight: "800", color: "#FFFFFF", letterSpacing: -0.3 },
  heroSub:     { fontSize: 13, color: "rgba(255,255,255,0.8)", textAlign: "center", paddingHorizontal: 20 },
  heroCurve: {
    position: "absolute",
    bottom: -2, left: -20, right: -20,
    height: 36,
    borderTopLeftRadius: 36,
    borderTopRightRadius: 36,
  },

  content: { padding: spacing.xl, gap: spacing.lg },

  uploadZone: {
    height: 260,
    borderRadius: radius.lg,
    borderWidth: 2,
    overflow: "hidden",
    position: "relative",
    ...platformShadow("#17235B", { x: 0, y: 4, opacity: 0.10, radius: 12 }),
  },
  uploadInner: { flex: 1, alignItems: "center", justifyContent: "center", padding: spacing.xl, gap: spacing.sm },
  uploadIcon:  { fontSize: 48 },
  uploadTitle: { fontSize: 17, fontWeight: "700", textAlign: "center" },
  uploadHint:  { fontSize: 13, textAlign: "center", lineHeight: 18 },
  uploadImage: { width: "100%", height: "100%" },
  retakeBadge: {
    position: "absolute",
    bottom: 12, right: 12,
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: radius.pill,
  },
  retakeText: { color: "#FFFFFF", fontSize: 12, fontWeight: "700" },

  pickBtn: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: spacing.sm,
    paddingVertical: 16,
    borderRadius: radius.pill,
    ...platformShadow("#17235B", { x: 0, y: 6, opacity: 0.25, radius: 12 }),
  },
  pickBtnIcon: { fontSize: 20 },
  pickBtnText: { color: "#FFFFFF", fontSize: 16, fontWeight: "700" },

  errorBox:  { padding: spacing.md, borderRadius: radius.md, borderWidth: 1 },
  errorText: { fontSize: 13, fontWeight: "500" },

  altHeader:  { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  altTitle:   { fontSize: 16, fontWeight: "700" },
  altCount:   { fontSize: 13 },
  altRow:     { gap: spacing.md },
  altCard: {
    width: 148,
    borderRadius: radius.lg,
    borderWidth: 1,
    overflow: "hidden",
    ...platformShadow("#17235B", { x: 0, y: 2, opacity: 0.07, radius: 6 }),
  },
  altImage: { width: "100%", height: 110 },
  altBody:  { padding: spacing.sm, gap: 3 },
  altName:  { fontSize: 13, fontWeight: "600", lineHeight: 17 },
  altMeta:  { fontSize: 12, fontWeight: "600" },
});
