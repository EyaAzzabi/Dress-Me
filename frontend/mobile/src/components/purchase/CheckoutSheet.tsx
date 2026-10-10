import { useEffect, useState } from "react";
import {
  ActivityIndicator,
  Image,
  Linking,
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";

import { CatalogAlternative, formatTnd, getLiveProduct, LiveProduct } from "@/api/purchase";
import { useTheme } from "@/theme/ThemeContext";
import { radius, spacing } from "@/theme/tokens";

export type ShopProduct = Pick<
  CatalogAlternative,
  "item_key" | "name" | "brand" | "image_url" | "price" | "product_url" | "store_url" | "buyable"
>;

interface Props {
  product: ShopProduct | null;
  onClose: () => void;
  saved?: boolean;
  onToggleSave?: (product: ShopProduct) => void;
}

/** Live product from the brand's store: sizes in stock, sale price, then payment on
 * the brand's own checkout (opened with the chosen size already in the cart). */
export function CheckoutSheet({ product, onClose, saved, onToggleSave }: Props) {
  const { colors } = useTheme();
  const [live, setLive] = useState<LiveProduct | null>(null);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);
  const [variantId, setVariantId] = useState<number | null>(null);

  useEffect(() => {
    setLive(null);
    setFailed(false);
    setVariantId(null);
    if (!product?.buyable || !product.item_key) return;
    let cancelled = false;
    setLoading(true);
    getLiveProduct(product.item_key)
      .then((data) => {
        if (cancelled) return;
        setLive(data);
        const inStock = data.variants.filter((v) => v.available);
        if (inStock.length === 1 || data.variants.length === 1) setVariantId((inStock[0] ?? data.variants[0]).id);
      })
      .catch(() => !cancelled && setFailed(true))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [product?.item_key, product?.buyable]);

  if (!product) return null;

  const variant = live?.variants.find((v) => v.id === variantId) ?? null;
  const price = variant?.price ?? live?.price ?? (typeof product.price === "number" ? product.price : null);
  const discount = live?.compare_at_price && live.price
    ? Math.round((1 - live.price / live.compare_at_price) * 100)
    : null;
  const sized = (live?.variants.length ?? 0) > 1;

  function pay() {
    if (variant?.available) Linking.openURL(variant.checkout_url);
  }

  return (
    <Modal visible transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={styles.backdrop} onPress={onClose} />
      <View style={[styles.sheet, { backgroundColor: colors.surfaceElevated }]}>
        <View style={[styles.handle, { backgroundColor: colors.border }]} />
        <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
          <View style={styles.header}>
            <Image
              source={{ uri: live?.image_url ?? product.image_url ?? undefined }}
              style={styles.image}
              resizeMode="contain"
            />
            <View style={styles.headerText}>
              {product.brand && (
                <Text style={[styles.brand, { color: colors.accent }]}>🇹🇳 {product.brand}</Text>
              )}
              <Text style={[styles.name, { color: colors.text }]} numberOfLines={3}>
                {live?.title ?? product.name}
              </Text>
              <View style={styles.priceRow}>
                <Text style={[styles.price, { color: colors.primary }]}>{formatTnd(price) ?? "Prix n.c."}</Text>
                {live?.compare_at_price && (
                  <Text style={[styles.oldPrice, { color: colors.textMuted }]}>{formatTnd(live.compare_at_price)}</Text>
                )}
                {discount != null && discount > 0 && (
                  <View style={[styles.saleBadge, { backgroundColor: colors.error }]}>
                    <Text style={styles.saleText}>-{discount} %</Text>
                  </View>
                )}
              </View>
              {live && (
                <Text style={{ color: live.available ? colors.success : colors.error, fontSize: 12, fontWeight: "700" }}>
                  {live.available ? "● En stock — prix en direct du site" : "● Rupture de stock"}
                </Text>
              )}
            </View>
          </View>

          {loading && (
            <View style={styles.loading}>
              <ActivityIndicator color={colors.primary} />
              <Text style={{ color: colors.textMuted, fontSize: 13 }}>Vérification du stock en direct…</Text>
            </View>
          )}

          {failed && (
            <Text style={[styles.note, { color: colors.textMuted }]}>
              Le site de la marque ne répond pas — tu peux voir le produit directement chez eux.
            </Text>
          )}

          {live && sized && (
            <View style={styles.section}>
              <Text style={[styles.sectionTitle, { color: colors.text }]}>Choisis ta taille</Text>
              <View style={styles.variants}>
                {live.variants.map((v) => {
                  const active = v.id === variantId;
                  return (
                    <Pressable
                      key={v.id}
                      disabled={!v.available}
                      onPress={() => setVariantId(v.id)}
                      style={[styles.variant, {
                        borderColor: active ? colors.primary : colors.border,
                        backgroundColor: active ? colors.primary : "transparent",
                        opacity: v.available ? 1 : 0.4,
                      }]}
                    >
                      <Text style={[styles.variantText, {
                        color: active ? "#FFFFFF" : colors.text,
                        textDecorationLine: v.available ? "none" : "line-through",
                      }]}>
                        {v.title}
                      </Text>
                    </Pressable>
                  );
                })}
              </View>
            </View>
          )}

          {live && (
            <Pressable
              onPress={pay}
              disabled={!variant?.available}
              style={[styles.payBtn, { backgroundColor: variant?.available ? colors.primary : colors.border }]}
            >
              <Text style={styles.payText}>
                {!live.available
                  ? "Indisponible pour le moment"
                  : !variant
                    ? "Choisis une taille"
                    : `🔒 Payer ${formatTnd(variant.price ?? price) ?? ""} sur ${live.brand}`}
              </Text>
            </Pressable>
          )}
          {live && (
            <Text style={[styles.note, { color: colors.textMuted }]}>
              Paiement sécurisé sur le site officiel de la marque — l'article est déjà dans ton panier.
            </Text>
          )}

          {!product.buyable && product.product_url && (
            <>
              <Pressable
                onPress={() => Linking.openURL(product.product_url!)}
                style={[styles.payBtn, { backgroundColor: colors.primary }]}
              >
                <Text style={styles.payText}>Voir et acheter sur {product.brand ?? "le site"} ↗</Text>
              </Pressable>
              <Text style={[styles.note, { color: colors.textMuted }]}>
                Ouvre la page de ce produit sur le site officiel de la marque.
              </Text>
            </>
          )}
          {!product.product_url && product.store_url && (
            <Text style={[styles.note, { color: colors.textMuted }]}>
              Cet article n'est plus en ligne chez {product.brand ?? "la marque"} — tu peux voir des modèles proches sur
              leur site.
            </Text>
          )}

          <View style={styles.links}>
            {(product.buyable || !product.product_url) && (product.product_url || product.store_url) && (
              <Pressable
                onPress={() => Linking.openURL((product.product_url ?? product.store_url)!)}
                style={[styles.linkBtn, { borderColor: colors.primary }]}
              >
                <Text style={[styles.linkText, { color: colors.primary }]}>
                  {product.product_url ? "Voir la fiche produit ↗" : `Visiter ${product.brand ?? "le site"} ↗`}
                </Text>
              </Pressable>
            )}
            {onToggleSave && product.item_key && (
              <Pressable
                onPress={() => onToggleSave(product)}
                style={[styles.linkBtn, { borderColor: colors.border }]}
              >
                <Text style={[styles.linkText, { color: colors.text }]}>
                  {saved ? "♥ Dans ta wishlist" : "♡ Ajouter à ma wishlist"}
                </Text>
              </Pressable>
            )}
          </View>
        </ScrollView>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: { ...StyleSheet.absoluteFillObject, backgroundColor: "rgba(26,10,20,0.45)" },
  sheet: {
    position: "absolute", left: 0, right: 0, bottom: 0,
    maxHeight: "88%",
    borderTopLeftRadius: 24, borderTopRightRadius: 24,
  },
  handle: { alignSelf: "center", width: 44, height: 5, borderRadius: 3, marginTop: 10 },
  content: { padding: spacing.xl, gap: spacing.lg },
  header: { flexDirection: "row", gap: spacing.lg },
  image: { width: 116, height: 140, borderRadius: radius.md, backgroundColor: "#FFFFFF" },
  headerText: { flex: 1, gap: 4 },
  brand: { fontSize: 12, fontWeight: "800", textTransform: "uppercase", letterSpacing: 0.5 },
  name: { fontSize: 16, fontWeight: "700", lineHeight: 21 },
  priceRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, flexWrap: "wrap" },
  price: { fontSize: 22, fontWeight: "900" },
  oldPrice: { fontSize: 14, textDecorationLine: "line-through" },
  saleBadge: { paddingHorizontal: 8, paddingVertical: 2, borderRadius: radius.pill },
  saleText: { color: "#FFFFFF", fontSize: 11, fontWeight: "900" },
  loading: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  section: { gap: spacing.sm },
  sectionTitle: { fontSize: 14, fontWeight: "800" },
  variants: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  variant: { paddingHorizontal: 14, paddingVertical: 8, borderRadius: radius.pill, borderWidth: 1.5 },
  variantText: { fontSize: 13, fontWeight: "700" },
  payBtn: { alignItems: "center", paddingVertical: 16, borderRadius: radius.pill },
  payText: { color: "#FFFFFF", fontSize: 16, fontWeight: "800" },
  note: { fontSize: 12, textAlign: "center", lineHeight: 17 },
  links: { gap: spacing.sm },
  linkBtn: { alignItems: "center", paddingVertical: 12, borderRadius: radius.pill, borderWidth: 1.5 },
  linkText: { fontSize: 14, fontWeight: "700" },
});
