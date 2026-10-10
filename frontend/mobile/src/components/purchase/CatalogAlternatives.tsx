import { Image, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { CatalogAlternative, formatTnd } from "@/api/purchase";
import { useTheme } from "@/theme/ThemeContext";
import { radius, spacing } from "@/theme/tokens";
import { platformShadow } from "@/utils/platformStyles";

// Matches the backend's DUPLICATE_SIMILARITY: above it, it's the same product photographed.
const SAME_ITEM_SIMILARITY = 0.95;

interface Props {
  alternatives: CatalogAlternative[];
  onOpen: (alternative: CatalogAlternative) => void;
  savedKeys: Set<string>;
  onToggleSave: (alternative: CatalogAlternative) => void;
}

export function CatalogAlternatives({ alternatives, onOpen, savedKeys, onToggleSave }: Props) {
  const { colors } = useTheme();
  if (alternatives.length === 0) return null;

  return (
    <View style={styles.root}>
      <Text style={[styles.title, { color: colors.tunisianNavy }]}>Alternatives en Tunisie</Text>
      <Text style={[styles.subtitle, { color: colors.tunisianNavy, opacity: 0.65 }]}>
        Trouvées par ressemblance visuelle (FashionCLIP) — touche pour commander
      </Text>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.row}>
        {alternatives.map((alt, i) => {
          const saved = alt.item_key != null && savedKeys.has(alt.item_key);
          return (
            <Pressable
              key={alt.item_key ?? i}
              onPress={() => onOpen(alt)}
              style={[styles.card, { backgroundColor: colors.surfaceElevated, borderColor: colors.border },
                platformShadow(colors.primary, { y: 2, opacity: 0.07, radius: 6 })]}
            >
              <View>
                {alt.image_url && <Image source={{ uri: alt.image_url }} style={styles.image} />}
                {alt.similarity != null && (
                  <View style={[styles.simBadge, {
                    backgroundColor: alt.similarity >= SAME_ITEM_SIMILARITY ? colors.accent : colors.tunisianNavy,
                  }]}>
                    <Text style={styles.badgeText}>
                      {alt.similarity >= SAME_ITEM_SIMILARITY ? "Même article" : `${Math.round(alt.similarity * 100)} % similaire`}
                    </Text>
                  </View>
                )}
                {alt.cheaper && (
                  <View style={[styles.cheaperBadge, { backgroundColor: colors.success }]}>
                    <Text style={styles.badgeText}>Moins cher</Text>
                  </View>
                )}
                {alt.item_key && (
                  <Pressable
                    onPress={() => onToggleSave(alt)}
                    hitSlop={8}
                    style={[styles.heart, { backgroundColor: colors.surfaceElevated }]}
                  >
                    <Text style={{ color: colors.primary, fontSize: 16 }}>{saved ? "♥" : "♡"}</Text>
                  </Pressable>
                )}
              </View>
              <View style={styles.body}>
                <Text style={[styles.name, { color: colors.text }]} numberOfLines={2}>{alt.name}</Text>
                <Text style={[styles.price, { color: colors.primary }]}>{formatTnd(alt.price) ?? "Prix n.c."}</Text>
                {alt.brand && <Text style={[styles.brand, { color: colors.textMuted }]}>{alt.brand}</Text>}
                <View style={[styles.cta, { backgroundColor: alt.buyable ? colors.primary : colors.pillBg }]}>
                  <Text style={[styles.ctaText, { color: alt.buyable ? "#FFFFFF" : colors.pillText }]}>
                    {alt.buyable ? "Acheter 🛍" : "Voir le site ↗"}
                  </Text>
                </View>
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
  row: { gap: spacing.md, paddingVertical: 4 },
  card: { width: 156, borderRadius: radius.lg, borderWidth: 1, overflow: "hidden" },
  image: { width: "100%", height: 168, backgroundColor: "#FFFFFF" },
  simBadge: { position: "absolute", left: 8, bottom: 8, paddingHorizontal: 8, paddingVertical: 3, borderRadius: radius.pill },
  cheaperBadge: { position: "absolute", left: 8, top: 8, paddingHorizontal: 8, paddingVertical: 3, borderRadius: radius.pill },
  heart: {
    position: "absolute", right: 8, top: 8,
    width: 30, height: 30, borderRadius: 15,
    alignItems: "center", justifyContent: "center",
  },
  badgeText: { color: "#FFFFFF", fontSize: 10, fontWeight: "800" },
  body: { padding: spacing.sm, gap: 2 },
  name: { fontSize: 13, fontWeight: "600", lineHeight: 17, minHeight: 34 },
  price: { fontSize: 15, fontWeight: "800" },
  brand: { fontSize: 11 },
  cta: { marginTop: 6, alignItems: "center", paddingVertical: 6, borderRadius: radius.pill },
  ctaText: { fontSize: 12, fontWeight: "800" },
});
