import { Image, Linking, Pressable, StyleSheet, Text, View } from "react-native";

import { BrandRecommendation, CatalogAlternative, formatTnd } from "@/api/purchase";
import { useTheme } from "@/theme/ThemeContext";
import { radius, spacing } from "@/theme/tokens";
import { platformShadow } from "@/utils/platformStyles";

interface Props {
  brands: BrandRecommendation[];
  onOpen: (product: CatalogAlternative) => void;
}

/** Tunisian brands ranked by visual affinity with the piece and the user's style. */
export function TunisianBrands({ brands, onOpen }: Props) {
  const { colors } = useTheme();
  if (brands.length === 0) return null;
  const best = brands[0].affinity;

  return (
    <View style={styles.root}>
      <Text style={[styles.title, { color: colors.tunisianNavy }]}>🇹🇳 Marques tunisiennes pour toi</Text>
      <Text style={[styles.subtitle, { color: colors.tunisianNavy, opacity: 0.65 }]}>
        Classées par affinité visuelle avec cet article et ton style (FashionCLIP)
      </Text>
      {brands.map((brand, rank) => {
        const match = Math.round((brand.affinity / best) * 100);
        return (
          <View
            key={brand.name}
            style={[styles.card, { backgroundColor: colors.surfaceElevated, borderColor: colors.border },
              platformShadow(colors.primary, { y: 2, opacity: 0.06, radius: 6 })]}
          >
            <View style={styles.top}>
              <View style={[styles.rank, { backgroundColor: rank === 0 ? colors.accent : colors.tunisianNavy }]}>
                <Text style={styles.rankText}>{rank + 1}</Text>
              </View>
              <View style={styles.info}>
                <Text style={[styles.name, { color: colors.text }]}>{brand.name}</Text>
                <Text style={[styles.meta, { color: colors.textMuted }]}>
                  {brand.product_count} articles similaires
                  {brand.price_min != null && brand.price_max != null &&
                    ` · ${formatTnd(brand.price_min)} – ${formatTnd(brand.price_max)}`}
                </Text>
                <View style={[styles.track, { backgroundColor: colors.pillBg }]}>
                  <View style={[styles.fill, { width: `${match}%`, backgroundColor: colors.primary }]} />
                </View>
              </View>
              {brand.website && (
                <Pressable
                  onPress={() => Linking.openURL(brand.website!)}
                  style={[styles.visit, { borderColor: colors.primary }]}
                >
                  <Text style={[styles.visitText, { color: colors.primary }]}>Site ↗</Text>
                </Pressable>
              )}
            </View>
            <View style={styles.showcase}>
              {brand.showcase.map((product) => (
                <Pressable key={product.item_key ?? product.name} onPress={() => onOpen(product)} style={styles.product}>
                  {product.image_url && <Image source={{ uri: product.image_url }} style={styles.productImage} />}
                  <Text style={[styles.productName, { color: colors.text }]} numberOfLines={1}>{product.name}</Text>
                  <Text style={[styles.productPrice, { color: colors.primary }]}>
                    {formatTnd(product.price) ?? "Prix n.c."}
                  </Text>
                </Pressable>
              ))}
            </View>
          </View>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { gap: spacing.sm },
  title: { fontSize: 17, fontWeight: "800" },
  subtitle: { fontSize: 12, marginTop: -4 },
  card: { borderRadius: radius.lg, borderWidth: 1, padding: spacing.md, gap: spacing.md },
  top: { flexDirection: "row", alignItems: "center", gap: spacing.md },
  rank: { width: 30, height: 30, borderRadius: 15, alignItems: "center", justifyContent: "center" },
  rankText: { color: "#FFFFFF", fontWeight: "900", fontSize: 14 },
  info: { flex: 1, gap: 3 },
  name: { fontSize: 15, fontWeight: "800" },
  meta: { fontSize: 11 },
  track: { height: 6, borderRadius: 3, overflow: "hidden", marginTop: 2 },
  fill: { height: "100%", borderRadius: 3 },
  visit: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: radius.pill, borderWidth: 1.5 },
  visitText: { fontSize: 12, fontWeight: "800" },
  showcase: { flexDirection: "row", gap: spacing.md },
  product: { flex: 1, gap: 2 },
  productImage: { width: "100%", height: 110, borderRadius: radius.md, backgroundColor: "#FFFFFF" },
  productName: { fontSize: 12, fontWeight: "600" },
  productPrice: { fontSize: 13, fontWeight: "800" },
});
