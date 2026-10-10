import { Ionicons } from "@expo/vector-icons";
import * as ImagePicker from "expo-image-picker";
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
    ActivityIndicator,
    Pressable,
    ScrollView,
    StyleSheet,
    Text,
    View,
} from "react-native";

import {
  addToWishlist,
  checkPurchase,
  clearPurchaseHistory,
  deleteHistoryEntry,
  extractGarments,
  GarmentExtractionResult,
  getPurchaseHistory,
  getWishlist,
  PurchaseCheckResult,
  PurchaseHistoryItem,
  removeFromWishlist,
  WishlistEntry,
} from "@/api/purchase";
import { uploadPhoto } from "@/api/wardrobe";
import { TextField } from "@/components/TextField";
import { TunisianPhotoHero } from "@/components/TunisianPhotoHero";
import { CatalogAlternatives } from "@/components/purchase/CatalogAlternatives";
import { CheckoutSheet, ShopProduct } from "@/components/purchase/CheckoutSheet";
import { CostPerWearCard } from "@/components/purchase/CostPerWearCard";
import { DetectedGarments } from "@/components/purchase/DetectedGarments";
import { PriceInsightCard } from "@/components/purchase/PriceInsightCard";
import { ScoreVerdictCard } from "@/components/purchase/ScoreVerdictCard";
import { ShoppingSpace } from "@/components/purchase/ShoppingSpace";
import { TunisianBrands } from "@/components/purchase/TunisianBrands";
import { UploadCard } from "@/components/purchase/UploadCard";
import { useTheme } from "@/theme/ThemeContext";
import { radius, spacing } from "@/theme/tokens";
import { platformShadow } from "@/utils/platformStyles";

function parsePrice(text: string): number | undefined {
  const value = parseFloat(text.replace(",", ".").replace(/[^\d.]/g, ""));
  return Number.isFinite(value) && value > 0 ? value : undefined;
}

type Phase = "idle" | "detecting" | "analysing";

const PRICE_QUESTION: Record<string, string> = {
  haut: "ce haut", bas: "ce bas", robe: "cette robe", veste: "cette veste",
  chaussures: "ces chaussures", sac: "ce sac", accessoire: "cet accessoire",
};

function wishlistProduct(item: WishlistEntry): ShopProduct {
  return { ...item, price: item.live_price ?? item.saved_price };
}

function errorMessage(err: any) {
  return err?.response?.data?.detail ?? "Un problème est survenu — réessaie.";
}

export default function PurchaseCheckScreen() {
  const { colors } = useTheme();
  const [imageUri, setImageUri]     = useState<string | null>(null);
  const [extraction, setExtraction] = useState<GarmentExtractionResult | null>(null);
  const [selected, setSelected]     = useState<number | null>(null);
  const [priceText, setPriceText]   = useState("");
  const [result, setResult]         = useState<PurchaseCheckResult | null>(null);
  const [phase, setPhase]           = useState<Phase>("idle");
  const [error, setError]           = useState<string | null>(null);
  const [wishlist, setWishlist]     = useState<WishlistEntry[]>([]);
  const [shopProduct, setShopProduct] = useState<ShopProduct | null>(null);
  const [history, setHistory]       = useState<PurchaseHistoryItem[]>([]);
  const [historyId, setHistoryId]   = useState<string | null>(null);
  const scrollRef = useRef<ScrollView>(null);

  const savedKeys = useMemo(() => new Set(wishlist.map((w) => w.item_key)), [wishlist]);

  // Wishlist and history are side panels: if they can't load, the purchase check still works.
  const refreshWishlist = useCallback(() => {
    getWishlist().then(setWishlist).catch(() => {});
  }, []);
  const refreshHistory = useCallback(() => {
    getPurchaseHistory().then(setHistory).catch(() => {});
  }, []);

  useEffect(refreshWishlist, [refreshWishlist]);
  useEffect(refreshHistory, [refreshHistory]);

  function openHistory(item: PurchaseHistoryItem) {
    setImageUri(item.image_url);
    setExtraction({
      person_detected: false,
      garments: [{ category: item.category, color: item.color, image_url: item.image_url, share: 1 }],
    });
    setSelected(0);
    setPriceText(item.price != null ? String(item.price).replace(".", ",") : "");
    setResult(item.result);
    setError(null);
    setHistoryId(item.id);
    scrollRef.current?.scrollTo({ y: 0, animated: true });
  }

  function removeHistory(item: PurchaseHistoryItem) {
    setHistory((items) => items.filter((h) => h.id !== item.id));
    if (item.id === historyId) setHistoryId(null);
    deleteHistoryEntry(item.id).catch(refreshHistory);
  }

  function clearHistory() {
    setHistory([]);
    setHistoryId(null);
    clearPurchaseHistory().catch(refreshHistory);
  }

  async function toggleSave(product: ShopProduct) {
    if (!product.item_key) return;
    const key = product.item_key;
    if (savedKeys.has(key)) {
      setWishlist((items) => items.filter((w) => w.item_key !== key));
      await removeFromWishlist(key).catch(refreshWishlist);
    } else {
      const entry = await addToWishlist(key).catch(() => null);
      if (entry) setWishlist((items) => [entry, ...items.filter((w) => w.item_key !== key)]);
    }
  }

  const loading = phase !== "idle";
  const garment = extraction && selected != null ? extraction.garments[selected] : null;
  const notClothing =
    garment?.category === "hors_perimetre" || result?.item.category === "hors_perimetre";

  async function pickImage() {
    const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!permission.granted) return;
    const picked = await ImagePicker.launchImageLibraryAsync({ quality: 0.8 });
    if (picked.canceled) return;
    setImageUri(picked.assets[0].uri);
    await detect(picked.assets[0].uri);
  }

  async function detect(uri: string) {
    setExtraction(null);
    setSelected(null);
    setResult(null);
    setError(null);
    setHistoryId(null);
    setPhase("detecting");
    try {
      const found = await extractGarments(await uploadPhoto(uri));
      setExtraction(found);
      setSelected(found.garments.length > 0 ? 0 : null);
    } catch (err: any) {
      setError(errorMessage(err));
    } finally {
      setPhase("idle");
    }
  }

  function selectGarment(index: number) {
    if (index === selected) return;
    setSelected(index);
    setResult(null);
    setError(null);
  }

  async function analyse() {
    if (!garment) return;
    setResult(null);
    setError(null);
    setPhase("analysing");
    setHistoryId(null);
    try {
      setResult(await checkPurchase(garment.image_url, parsePrice(priceText), garment.category));
      refreshHistory();
    } catch (err: any) {
      setError(errorMessage(err));
    } finally {
      setPhase("idle");
    }
  }

  function onMainPress() {
    if (loading) return;
    if (!imageUri) return pickImage();
    if (!extraction) return detect(imageUri);
    return analyse();
  }

  const mainLabel = !imageUri
    ? "Choisir une photo"
    : phase === "detecting"
      ? "Détection des vêtements…"
      : phase === "analysing"
        ? "Analyse en cours…"
        : !extraction
          ? "Relancer la détection"
          : result
            ? "Relancer l'analyse"
            : "Analyser cet achat";
  const mainIcon = !imageUri ? "images-outline" : !extraction ? "refresh" : "sparkles";

  const garmentCount = extraction?.garments.length ?? 0;
  const [uploadStatus, uploadHint] =
    phase === "detecting" ? ["Détection des vêtements…", "Segmentation · découpage · FashionCLIP"]
    : phase === "analysing" ? ["Analyse IA en cours…", "Compatibilité · style · marché tunisien"]
    : historyId ? ["Depuis ton historique", "Change le prix et relance si tu veux"]
    : notClothing ? ["Aucun vêtement reconnu", "Essaie une photo de l'article seul"]
    : !extraction ? ["Détection interrompue", "Relance la détection ci-dessous"]
    : result ? ["Analyse terminée", "Ton verdict est juste en dessous"]
    : garmentCount > 1 ? [`${garmentCount} vêtements détectés`, "Choisis la pièce qui t'intéresse"]
    : ["Vêtement détecté", "Ajoute le prix pour une analyse complète"];

  const itemChips = result
    ? [result.item.category, result.item.color, result.item.pattern, result.item.style].filter(Boolean)
    : [];

  return (
    <ScrollView
      ref={scrollRef}
      style={{ backgroundColor: colors.bg }}
      contentContainerStyle={styles.root}
      showsVerticalScrollIndicator={false}
      keyboardShouldPersistTaps="handled"
    >
      <TunisianPhotoHero
        icon="✧"
        title="J’achète ou pas ?"
        subtitle="Fais le bon choix pour ton dressing"
        image="wardrobe"
      />

      <View style={styles.content}>
        <UploadCard
          imageUri={imageUri}
          busy={loading}
          status={uploadStatus}
          hint={uploadHint}
          onPick={pickImage}
        />

        {extraction && extraction.garments.length > 0 && !notClothing && (
          <DetectedGarments
            garments={extraction.garments}
            personDetected={extraction.person_detected}
            selected={selected}
            onSelect={selectGarment}
            disabled={loading}
            note={historyId ? "Depuis ton historique — change le prix et relance si tu veux" : undefined}
          />
        )}

        {garment && !notClothing && (
          <View style={styles.priceRow}>
            <View style={styles.priceLabelRow}>
              <Ionicons name="pricetag-outline" size={16} color={colors.primary} />
              <Text style={[styles.priceLabel, { color: colors.tunisianNavy }]}>
                Combien coûte {PRICE_QUESTION[garment.category] ?? "cet article"} ?
              </Text>
              <View style={[styles.optional, { backgroundColor: colors.pillBg }]}>
                <Text style={[styles.optionalText, { color: colors.pillText }]}>optionnel</Text>
              </View>
            </View>
            <View style={styles.priceHelp}>
              <Ionicons name="information-circle-outline" size={14} color={colors.tunisianNavy} style={{ opacity: 0.65 }} />
              <Text style={[styles.priceHelpText, { color: colors.tunisianNavy }]}>
                Entre le prix vu en boutique ou en ligne : on le compare aux articles similaires
                du marché tunisien pour te dire si c'est une bonne affaire, le prix normal ou trop cher.
              </Text>
            </View>
            <TextField
              value={priceText}
              onChangeText={setPriceText}
              placeholder="ex. 89,90 TND"
              keyboardType="decimal-pad"
              editable={!loading}
            />
          </View>
        )}

        {!notClothing && imageUri && (
          <Pressable
            onPress={onMainPress}
            style={[styles.mainBtn, {
              backgroundColor: colors.primary,
              opacity: loading ? 0.6 : 1,
              ...platformShadow(colors.primary),
            }]}
          >
            {loading
              ? <ActivityIndicator color="#FFFFFF" />
              : <Ionicons name={mainIcon} size={18} color="#FFFFFF" />}
            <Text style={styles.mainBtnText}>{mainLabel}</Text>
          </Pressable>
        )}

        {error && (
          <View style={[styles.errorBox, { backgroundColor: colors.errorBg, borderColor: colors.error }]}>
            <Ionicons name="alert-circle-outline" size={18} color={colors.error} />
            <Text style={[styles.errorText, { color: colors.error }]}>{error}</Text>
          </View>
        )}

        {notClothing && (
          <View style={[styles.notClothing, { backgroundColor: colors.warningBg, borderColor: colors.warning }]}>
            <Ionicons name="search-outline" size={34} color={colors.warning} />
            <Text style={[styles.notClothingTitle, { color: colors.warning }]}>Ce n'est pas un vêtement</Text>
            <Text style={[styles.notClothingText, { color: colors.text }]}>
              L'IA ne reconnaît ni haut, bas, robe, veste, chaussures, sac ou accessoire sur cette photo.
              Prends l'article seul, bien cadré, sur un fond simple.
            </Text>
          </View>
        )}

        {result && garment && !notClothing && (
          <>
            <SectionTitle icon="ribbon-outline" title="Ton verdict" subtitle="Calculé sur ta garde-robe réelle" />

            {itemChips.length > 0 && (
              <View style={styles.chips}>
                <Ionicons name="eye-outline" size={14} color={colors.textMuted} />
                <Text style={[styles.chipsLabel, { color: colors.textMuted }]}>L'IA voit :</Text>
                {itemChips.map((chip) => (
                  <View key={chip} style={[styles.chip, { backgroundColor: colors.pillBg }]}>
                    <Text style={[styles.chipText, { color: colors.pillText }]}>{chip}</Text>
                  </View>
                ))}
              </View>
            )}

            <ScoreVerdictCard
              verdict={result.verdict}
              score={result.score}
              explanation={result.explanation}
              factors={result.factors}
            />

            {(result.cost_per_wear || result.price_insight) && (
              <SectionTitle icon="cash-outline" title="Le bon prix" subtitle="Comparé au marché tunisien" />
            )}

            {result.cost_per_wear && <CostPerWearCard cpw={result.cost_per_wear} />}

            {result.price_insight && <PriceInsightCard insight={result.price_insight} />}

            {(result.catalog_alternatives.length > 0 || result.tunisian_brands.length > 0) && (
              <SectionTitle
                icon="storefront-outline"
                title="Où l'acheter en Tunisie"
                subtitle="Paiement sécurisé sur le site officiel des marques"
              />
            )}

            <CatalogAlternatives
              alternatives={result.catalog_alternatives}
              onOpen={setShopProduct}
              savedKeys={savedKeys}
              onToggleSave={toggleSave}
            />

            <TunisianBrands brands={result.tunisian_brands} onOpen={setShopProduct} />
          </>
        )}

        <View style={[styles.divider, { backgroundColor: colors.border }]} />

        <ShoppingSpace
          history={history}
          activeHistoryId={historyId}
          onOpenHistory={openHistory}
          onRemoveHistory={removeHistory}
          onClearHistory={clearHistory}
          wishlist={wishlist}
          onOpenWish={(item) => setShopProduct(wishlistProduct(item))}
          onRemoveWish={(item) => toggleSave(wishlistProduct(item))}
        />
      </View>

      <CheckoutSheet
        product={shopProduct}
        onClose={() => setShopProduct(null)}
        saved={shopProduct?.item_key ? savedKeys.has(shopProduct.item_key) : false}
        onToggleSave={toggleSave}
      />
    </ScrollView>
  );
}

function SectionTitle({ icon, title, subtitle }: {
  icon: React.ComponentProps<typeof Ionicons>["name"];
  title: string;
  subtitle?: string;
}) {
  const { colors } = useTheme();
  return (
    <View style={styles.section}>
      <View style={[styles.sectionIcon, { backgroundColor: colors.pillBg }]}>
        <Ionicons name={icon} size={17} color={colors.primary} />
      </View>
      <View style={{ flex: 1 }}>
        <Text style={[styles.sectionTitle, { color: colors.tunisianNavy }]}>{title}</Text>
        {subtitle && <Text style={[styles.sectionSubtitle, { color: colors.tunisianNavy, opacity: 0.65 }]}>{subtitle}</Text>}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { paddingBottom: 40 },
  content: { padding: spacing.xl, gap: spacing.lg },

  section: { flexDirection: "row", alignItems: "center", gap: spacing.md, marginTop: spacing.sm },
  sectionIcon: { width: 34, height: 34, borderRadius: 17, alignItems: "center", justifyContent: "center" },
  sectionTitle: { fontSize: 18, fontWeight: "900" },
  sectionSubtitle: { fontSize: 12 },
  divider: { height: 1, marginVertical: spacing.sm },

  priceRow: { gap: spacing.sm },
  priceLabelRow: { flexDirection: "row", alignItems: "center", gap: 6 },
  priceLabel: { fontSize: 15, fontWeight: "800", flexShrink: 1 },
  optional: { paddingHorizontal: 8, paddingVertical: 2, borderRadius: radius.pill },
  optionalText: { fontSize: 10, fontWeight: "800" },
  priceHelp: { flexDirection: "row", alignItems: "flex-start", gap: 6 },
  priceHelpText: { flex: 1, fontSize: 12, lineHeight: 17, opacity: 0.75 },

  mainBtn: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: spacing.sm,
    paddingVertical: 15,
    borderRadius: radius.pill,
  },
  mainBtnText: { color: "#FFFFFF", fontSize: 16, fontWeight: "800" },

  errorBox:  { flexDirection: "row", alignItems: "center", gap: spacing.sm, padding: spacing.md, borderRadius: radius.md, borderWidth: 1 },
  errorText: { flex: 1, fontSize: 13, fontWeight: "500" },

  notClothing: {
    alignItems: "center",
    gap: spacing.sm,
    padding: spacing.xl,
    borderRadius: radius.lg,
    borderWidth: 1,
  },
  notClothingTitle: { fontSize: 17, fontWeight: "800" },
  notClothingText:  { fontSize: 13, lineHeight: 19, textAlign: "center" },

  chips: { flexDirection: "row", flexWrap: "wrap", alignItems: "center", gap: spacing.sm },
  chipsLabel: { fontSize: 12, fontWeight: "600" },
  chip: { paddingHorizontal: 12, paddingVertical: 5, borderRadius: radius.pill },
  chipText: { fontSize: 12, fontWeight: "700", textTransform: "capitalize" },
});
