import { Image, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { ExtractedGarment } from "@/api/purchase";
import { useTheme } from "@/theme/ThemeContext";
import { radius, spacing } from "@/theme/tokens";
import { platformShadow } from "@/utils/platformStyles";

const CATEGORY_LABELS: Record<string, string> = {
  haut: "Haut",
  bas: "Bas",
  robe: "Robe",
  veste: "Veste",
  chaussures: "Chaussures",
  sac: "Sac",
  accessoire: "Accessoire",
};

interface Props {
  garments: ExtractedGarment[];
  personDetected: boolean;
  selected: number | null;
  onSelect: (index: number) => void;
  disabled?: boolean;
  note?: string; // replaces the default subtitle
}

export function DetectedGarments({ garments, personDetected, selected, onSelect, disabled, note }: Props) {
  const { colors } = useTheme();

  return (
    <View style={styles.root}>
      <Text style={[styles.title, { color: colors.tunisianNavy }]}>
        {garments.length > 1 ? `${garments.length} vêtements détectés` : "Vêtement détecté"}
      </Text>
      <Text style={[styles.subtitle, { color: colors.tunisianNavy, opacity: 0.65 }]}>
        {note ?? (personDetected
          ? garments.length > 1
            ? "Découpés par segmentation (SegFormer) — choisis celui que tu veux acheter"
            : "Découpé par segmentation (SegFormer)"
          : "Photo produit — analysée en entier")}
      </Text>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.row}>
        {garments.map((garment, i) => {
          const active = i === selected;
          return (
            <Pressable
              key={garment.image_url}
              onPress={disabled ? undefined : () => onSelect(i)}
              style={[styles.card, {
                backgroundColor: colors.surfaceElevated,
                borderColor: active ? colors.primary : colors.border,
                borderWidth: active ? 2.5 : 1,
                opacity: disabled && !active ? 0.5 : 1,
              }, platformShadow(colors.primary, { y: 2, opacity: active ? 0.18 : 0.06, radius: 6 })]}
            >
              <Image source={{ uri: garment.image_url }} style={styles.image} resizeMode="contain" />
              {active && (
                <View style={[styles.check, { backgroundColor: colors.primary }]}>
                  <Text style={styles.checkText}>✓</Text>
                </View>
              )}
              <View style={styles.body}>
                <Text style={[styles.category, { color: colors.text }]}>
                  {CATEGORY_LABELS[garment.category] ?? garment.category}
                </Text>
                {garment.color && (
                  <Text style={[styles.color, { color: colors.textMuted }]}>{garment.color}</Text>
                )}
              </View>
            </Pressable>
          );
        })}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { gap: spacing.xs },
  title: { fontSize: 17, fontWeight: "800" },
  subtitle: { fontSize: 12, marginBottom: spacing.sm },
  row: { gap: spacing.md, paddingVertical: 4, paddingHorizontal: 2 },
  card: { width: 120, borderRadius: radius.lg, overflow: "hidden" },
  image: { width: "100%", height: 130, backgroundColor: "#FFFFFF" },
  check: {
    position: "absolute", top: 8, right: 8,
    width: 24, height: 24, borderRadius: 12,
    alignItems: "center", justifyContent: "center",
  },
  checkText: { color: "#FFFFFF", fontSize: 13, fontWeight: "900" },
  body: { padding: spacing.sm, gap: 1 },
  category: { fontSize: 13, fontWeight: "800" },
  color: { fontSize: 11, textTransform: "capitalize" },
});
