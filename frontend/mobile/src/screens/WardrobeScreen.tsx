import AsyncStorage from "@react-native-async-storage/async-storage";
import { useFocusEffect } from "@react-navigation/native";
import * as ImagePicker from "expo-image-picker";
import { useCallback, useMemo, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Image,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { isAxiosError } from "axios";

import { platformShadow } from "@/utils/platformStyles";
import {
  addWardrobeItem,
  listWardrobeItems,
  removeWardrobeItem,
  uploadPhoto,
} from "@/api/wardrobe";
import { TunisianHeader } from "@/components/TunisianHeader";
import { useTheme } from "@/theme/ThemeContext";
import { radius, spacing } from "@/theme/tokens";
import { ClothingItem } from "@/types/models";
import { notify } from "@/utils/notify";

const FAVORITES_STORAGE_KEY = "dressme_wardrobe_favorites";

const CAT_ICON: Record<string, string> = {
  top: "👕", tops: "👕",
  bottom: "👖", bottoms: "👖", pants: "👖", jeans: "👖",
  dress: "👗", dresses: "👗",
  shoes: "👟", chaussures: "👟",
  bag: "👜", bags: "👜", sac: "👜",
  accessory: "💍", accessories: "💍", accessoire: "💍",
  outerwear: "🧥", veste: "🧥", jacket: "🧥",
  uncategorized: "🪡",
};

function getErrorMessage(error: unknown): string {
  if (isAxiosError(error) && typeof error.response?.data?.detail === "string") {
    return error.response.data.detail;
  }
  return "Une erreur est survenue. Réessaie dans un instant.";
}

function getCategory(item: ClothingItem): string {
  return (item.category ?? "uncategorized").toLowerCase();
}

function groupByCategory(items: ClothingItem[]): [string, ClothingItem[]][] {
  const map = new Map<string, ClothingItem[]>();
  for (const item of items) {
    const category = getCategory(item);
    const group = map.get(category);
    if (group) group.push(item);
    else map.set(category, [item]);
  }
  return Array.from(map.entries()).sort(([a], [b]) => a.localeCompare(b));
}

function readFavorites(raw: string | null): string[] {
  if (!raw) return [];
  const parsed: unknown = JSON.parse(raw);
  if (!Array.isArray(parsed) || !parsed.every((id) => typeof id === "string")) {
    throw new Error("Invalid favorites data");
  }
  return parsed;
}

export default function WardrobeScreen() {
  const { colors } = useTheme();
  const [items, setItems] = useState<ClothingItem[]>([]);
  const [favorites, setFavorites] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [adding, setAdding] = useState(false);
  const [removingId, setRemovingId] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [favoritesOnly, setFavoritesOnly] = useState(false);

  const reload = useCallback(async () => {
    const nextItems = await listWardrobeItems();
    setItems(nextItems);
    return nextItems;
  }, []);

  useFocusEffect(useCallback(() => {
    let active = true;
    setLoading(true);
    Promise.all([
      listWardrobeItems(),
      AsyncStorage.getItem(FAVORITES_STORAGE_KEY).then(readFavorites),
    ])
      .then(([nextItems, storedFavorites]) => {
        if (!active) return;
        const validIds = new Set(nextItems.map((item) => item.id));
        const nextFavorites = storedFavorites.filter((id) => validIds.has(id));
        setItems(nextItems);
        setFavorites(nextFavorites);
        if (nextFavorites.length !== storedFavorites.length) {
          return AsyncStorage.setItem(FAVORITES_STORAGE_KEY, JSON.stringify(nextFavorites));
        }
      })
      .catch((error: unknown) => {
        if (active) notify("Impossible de charger le dressing", getErrorMessage(error));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []));

  async function handleAdd() {
    try {
      const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
      if (!permission.granted) {
        notify("Accès aux photos requis", "Autorise DressMe à accéder à ta galerie pour ajouter une pièce.");
        return;
      }
      const picture = await ImagePicker.launchImageLibraryAsync({ quality: 0.85 });
      if (picture.canceled) return;
      setAdding(true);
      await addWardrobeItem(await uploadPhoto(picture.assets[0].uri));
      await reload();
      notify("Pièce ajoutée", "Ta nouvelle pièce est dans ton dressing.");
    } catch (error: unknown) {
      notify("Impossible d'ajouter", getErrorMessage(error));
    } finally {
      setAdding(false);
    }
  }

  async function toggleFavorite(itemId: string) {
    const nextFavorites = favorites.includes(itemId)
      ? favorites.filter((id) => id !== itemId)
      : [...favorites, itemId];
    try {
      await AsyncStorage.setItem(FAVORITES_STORAGE_KEY, JSON.stringify(nextFavorites));
      setFavorites(nextFavorites);
    } catch (error: unknown) {
      notify("Favori non enregistré", getErrorMessage(error));
    }
  }

  async function deleteItem(item: ClothingItem) {
    setRemovingId(item.id);
    try {
      await removeWardrobeItem(item.id);
      const nextFavorites = favorites.filter((id) => id !== item.id);
      setItems((current) => current.filter((currentItem) => currentItem.id !== item.id));
      setFavorites(nextFavorites);
      try {
        await AsyncStorage.setItem(FAVORITES_STORAGE_KEY, JSON.stringify(nextFavorites));
      } catch (error: unknown) {
        notify("Pièce supprimée", `La pièce a été supprimée, mais le favori n'a pas pu être synchronisé. ${getErrorMessage(error)}`);
      }
    } catch (error: unknown) {
      notify("Impossible de supprimer", getErrorMessage(error));
    } finally {
      setRemovingId(null);
    }
  }

  function confirmDelete(item: ClothingItem) {
    const message = "Cette pièce sera retirée de ton dressing.";
    if (Platform.OS === "web") {
      if (window.confirm(`Supprimer cette pièce ?\n\n${message}`)) {
        void deleteItem(item);
      }
      return;
    }
    Alert.alert("Supprimer cette pièce ?", message, [
      { text: "Annuler", style: "cancel" },
      { text: "Supprimer", style: "destructive", onPress: () => void deleteItem(item) },
    ]);
  }

  const categories = useMemo(
    () => Array.from(new Set(items.map(getCategory))).sort((a, b) => a.localeCompare(b)),
    [items]
  );

  const filteredItems = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase();
    return items.filter((item) => {
      const category = getCategory(item);
      const searchable = [
        category,
        item.style ?? "",
        item.season ?? "",
        ...(item.colors ?? []),
      ].join(" ").toLocaleLowerCase();
      return (!selectedCategory || category === selectedCategory)
        && (!favoritesOnly || favorites.includes(item.id))
        && (!normalizedQuery || searchable.includes(normalizedQuery));
    });
  }, [favorites, favoritesOnly, items, query, selectedCategory]);

  const groups = useMemo(() => groupByCategory(filteredItems), [filteredItems]);

  if (loading) {
    return (
      <View style={[styles.centered, { backgroundColor: colors.bg }]}>
        <ActivityIndicator color={colors.primary} size="large" />
        <Text style={[styles.loadTxt, { color: colors.textMuted }]}>Chargement du dressing…</Text>
      </View>
    );
  }

  return (
    <View style={[styles.root, { backgroundColor: colors.bg }]}>
      <TunisianHeader
        title="Ma Garde-Robe"
        subtitle={`${items.length} pièce${items.length !== 1 ? "s" : ""} · ${favorites.length} favori${favorites.length !== 1 ? "s" : ""}`}
        actionLabel="＋ Ajouter"
        onAction={handleAdd}
        actionLoading={adding}
        bandHeight={130}
        logoWidth={180}
      />

      <ScrollView
        style={styles.scroll}
        contentContainerStyle={styles.content}
        showsVerticalScrollIndicator={false}
        keyboardShouldPersistTaps="handled"
      >
        {items.length > 0 && (
          <View style={styles.tools}>
            <View style={[
              styles.searchBox,
              { backgroundColor: colors.surfaceElevated, borderColor: colors.border },
            ]}>
              <Text style={styles.searchIcon}>⌕</Text>
              <TextInput
                value={query}
                onChangeText={setQuery}
                placeholder="Rechercher couleur, style, saison…"
                placeholderTextColor={colors.textSubtle}
                returnKeyType="search"
                accessibilityLabel="Rechercher dans le dressing"
                style={[styles.searchInput, { color: colors.text }]}
              />
              {query.length > 0 && (
                <Pressable onPress={() => setQuery("")} accessibilityLabel="Effacer la recherche">
                  <Text style={[styles.clearSearch, { color: colors.textMuted }]}>×</Text>
                </Pressable>
              )}
            </View>

            <ScrollView
              horizontal
              showsHorizontalScrollIndicator={false}
              contentContainerStyle={styles.filters}
            >
              <FilterChip
                label="Tout"
                selected={!favoritesOnly && !selectedCategory}
                onPress={() => {
                  setFavoritesOnly(false);
                  setSelectedCategory(null);
                }}
              />
              <FilterChip
                label={`♡ Favoris ${favorites.length > 0 ? `(${favorites.length})` : ""}`}
                selected={favoritesOnly}
                onPress={() => {
                  setFavoritesOnly((current) => !current);
                  setSelectedCategory(null);
                }}
              />
              {categories.map((category) => (
                <FilterChip
                  key={category}
                  label={`${CAT_ICON[category] ?? "👗"} ${categoryLabel(category)}`}
                  selected={selectedCategory === category}
                  onPress={() => {
                    setSelectedCategory((current) => current === category ? null : category);
                    setFavoritesOnly(false);
                  }}
                />
              ))}
            </ScrollView>
          </View>
        )}

        {items.length === 0 ? (
          <View style={[styles.empty, { borderColor: colors.border }]}>
            <Text style={styles.emptyEmoji}>👗</Text>
            <Text style={[styles.emptyTitle, { color: colors.text }]}>Garde-robe vide</Text>
            <Text style={[styles.emptySub, { color: colors.textMuted }]}>
              Ajoute tes premières pièces et DressMe t’aidera à composer des looks qui te ressemblent.
            </Text>
            <Pressable
              onPress={handleAdd}
              disabled={adding}
              style={[styles.emptyBtn, { backgroundColor: colors.primary, ...platformShadow(colors.primary) }]}
            >
              <Text style={styles.emptyBtnText}>
                {adding ? "Ajout en cours…" : "＋  Ajouter ma première pièce"}
              </Text>
            </Pressable>
          </View>
        ) : groups.length === 0 ? (
          <View style={[styles.noResults, { backgroundColor: colors.surfaceElevated, borderColor: colors.border }]}>
            <Text style={styles.noResultsIcon}>{favoritesOnly ? "♡" : "⌕"}</Text>
            <Text style={[styles.emptyTitle, { color: colors.text }]}>
              {favoritesOnly ? "Aucun favori pour le moment" : "Aucune pièce trouvée"}
            </Text>
            <Text style={[styles.emptySub, { color: colors.textMuted }]}>
              {favoritesOnly
                ? "Touche le cœur d’une pièce pour la retrouver facilement ici."
                : "Essaie une autre recherche ou réinitialise les filtres."}
            </Text>
            <Pressable
              onPress={() => {
                setQuery("");
                setSelectedCategory(null);
                setFavoritesOnly(false);
              }}
            >
              <Text style={[styles.resetText, { color: colors.primary }]}>Réinitialiser les filtres</Text>
            </Pressable>
          </View>
        ) : (
          <>
            <Text style={[styles.resultCount, { color: colors.textMuted }]}>
              {filteredItems.length} pièce{filteredItems.length !== 1 ? "s" : ""} affichée{filteredItems.length !== 1 ? "s" : ""}
            </Text>
            {groups.map(([category, categoryItems]) => (
              <View key={category} style={styles.section}>
                <View style={styles.catHeaderRow}>
                  <View style={[
                    styles.catTag,
                    { backgroundColor: colors.surface, borderColor: colors.border, ...platformShadow(colors.primary) },
                  ]}>
                    <Text style={styles.catEmoji}>{CAT_ICON[category] ?? "👗"}</Text>
                    <Text style={[styles.catName, { color: colors.text }]}>{categoryLabel(category)}</Text>
                    <View style={[styles.catBadge, { backgroundColor: colors.primary }]}>
                      <Text style={styles.catBadgeTxt}>{categoryItems.length}</Text>
                    </View>
                  </View>
                </View>

                <ScrollView
                  horizontal
                  showsHorizontalScrollIndicator={false}
                  contentContainerStyle={styles.itemRow}
                >
                  {categoryItems.map((item) => {
                    const isFavorite = favorites.includes(item.id);
                    const isRemoving = removingId === item.id;
                    return (
                      <View
                        key={item.id}
                        style={[
                          styles.itemCard,
                          {
                            backgroundColor: colors.surfaceElevated,
                            borderColor: colors.border,
                            ...platformShadow(colors.primary),
                          },
                        ]}
                      >
                        <Image source={{ uri: item.image_url }} style={styles.itemImg} />
                        {isRemoving && (
                          <View style={styles.removingOverlay}>
                            <ActivityIndicator color="#FFFFFF" />
                          </View>
                        )}
                        <Pressable
                          onPress={() => void toggleFavorite(item.id)}
                          disabled={isRemoving}
                          accessibilityRole="button"
                          accessibilityLabel={isFavorite ? "Retirer des favoris" : "Ajouter aux favoris"}
                          accessibilityState={{ selected: isFavorite }}
                          style={[styles.iconButton, styles.heartBadge]}
                        >
                          <Text style={[styles.heartText, { color: isFavorite ? colors.primary : colors.textMuted }]}>
                            {isFavorite ? "♥" : "♡"}
                          </Text>
                        </Pressable>
                        <Pressable
                          onPress={() => confirmDelete(item)}
                          disabled={isRemoving}
                          accessibilityRole="button"
                          accessibilityLabel="Supprimer cette pièce"
                          style={[styles.iconButton, styles.deleteBadge]}
                        >
                          <Text style={styles.deleteText}>🗑</Text>
                        </Pressable>
                        <View style={[styles.itemAccent, { backgroundColor: colors.tunisianGold }]} />
                        <View style={styles.itemMeta}>
                          <Text style={[styles.itemCategory, { color: colors.text }]} numberOfLines={1}>
                            {categoryLabel(category)}
                          </Text>
                          <Text style={[styles.itemDetails, { color: colors.textMuted }]} numberOfLines={1}>
                            {[item.colors?.join(", "), item.season, item.style].filter(Boolean).join(" · ") || "Ajoutée à ton dressing"}
                          </Text>
                        </View>
                      </View>
                    );
                  })}
                </ScrollView>
              </View>
            ))}
          </>
        )}
      </ScrollView>
    </View>
  );
}

function categoryLabel(category: string): string {
  if (category === "uncategorized") return "Non classé";
  return category.charAt(0).toLocaleUpperCase() + category.slice(1);
}

function FilterChip({
  label,
  selected,
  onPress,
}: {
  label: string;
  selected: boolean;
  onPress: () => void;
}) {
  const { colors } = useTheme();
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityState={{ selected }}
      style={[
        styles.filterChip,
        {
          backgroundColor: selected ? colors.pillActiveBg : colors.surfaceElevated,
          borderColor: selected ? colors.pillActiveBg : colors.border,
        },
      ]}
    >
      <Text style={[styles.filterText, { color: selected ? colors.pillActiveText : colors.textMuted }]}>
        {label}
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  centered: { flex: 1, alignItems: "center", justifyContent: "center", gap: 10 },
  loadTxt: { fontSize: 14 },
  scroll: { flex: 1 },
  content: { paddingTop: spacing.md, paddingBottom: 48 },
  tools: { gap: spacing.md, marginBottom: spacing.lg },
  searchBox: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    minHeight: 50,
    marginHorizontal: spacing.xl,
    paddingHorizontal: spacing.md,
    borderWidth: 1,
    borderRadius: radius.md,
  },
  searchIcon: { fontSize: 25, color: "#A17A8B" },
  searchInput: { flex: 1, minHeight: 48, fontSize: 13 },
  clearSearch: { fontSize: 22, paddingHorizontal: 4 },
  filters: { paddingHorizontal: spacing.xl, gap: spacing.sm },
  filterChip: {
    minHeight: 36,
    justifyContent: "center",
    paddingHorizontal: 14,
    borderWidth: 1,
    borderRadius: radius.pill,
  },
  filterText: { fontSize: 11, fontWeight: "700" },
  resultCount: { marginHorizontal: spacing.xl, marginBottom: spacing.md, fontSize: 12, fontWeight: "600" },
  empty: {
    margin: spacing.xl,
    padding: spacing.xxl,
    borderRadius: radius.xl,
    borderWidth: 1.5,
    borderStyle: "dashed",
    alignItems: "center",
    gap: spacing.md,
  },
  noResults: {
    marginHorizontal: spacing.xl,
    marginTop: spacing.lg,
    padding: spacing.xxl,
    borderRadius: radius.xl,
    borderWidth: 1,
    alignItems: "center",
    gap: spacing.md,
  },
  emptyEmoji: { fontSize: 52 },
  noResultsIcon: { fontSize: 40, color: "#C9984A" },
  emptyTitle: { fontSize: 19, fontWeight: "800", textAlign: "center" },
  emptySub: { fontSize: 13, textAlign: "center", lineHeight: 20 },
  emptyBtn: {
    paddingHorizontal: 24,
    paddingVertical: 14,
    borderRadius: radius.pill,
    marginTop: spacing.sm,
    ...platformShadow("#17235B", { x: 0, y: 4, opacity: 0.25, radius: 10 }),
  },
  emptyBtnText: { color: "#FFF", fontWeight: "700", fontSize: 14 },
  resetText: { fontSize: 13, fontWeight: "800" },
  section: { marginBottom: spacing.xl },
  catHeaderRow: { paddingHorizontal: spacing.xl, marginBottom: spacing.md },
  catTag: {
    flexDirection: "row",
    alignItems: "center",
    alignSelf: "flex-start",
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: radius.pill,
    borderWidth: 1,
    gap: 6,
    ...platformShadow("#17235B", { x: 0, y: 2, opacity: 0.08, radius: 6 }),
  },
  catEmoji: { fontSize: 17 },
  catName: { fontSize: 14, fontWeight: "700" },
  catBadge: {
    width: 22,
    height: 22,
    borderRadius: 11,
    alignItems: "center",
    justifyContent: "center",
    marginLeft: 2,
  },
  catBadgeTxt: { color: "#FFF", fontSize: 11, fontWeight: "800" },
  itemRow: { paddingHorizontal: spacing.xl, gap: spacing.md },
  itemCard: {
    width: 156,
    borderRadius: radius.lg,
    borderWidth: 1,
    overflow: "hidden",
    position: "relative",
    ...platformShadow("#17235B", { x: 0, y: 4, opacity: 0.10, radius: 10 }),
  },
  itemImg: { width: "100%", height: 168, backgroundColor: "#F3E8EC" },
  itemAccent: { height: 3 },
  itemMeta: { paddingHorizontal: 11, paddingVertical: 10, gap: 4 },
  itemCategory: { fontSize: 12, fontWeight: "800" },
  itemDetails: { fontSize: 10 },
  iconButton: {
    position: "absolute",
    zIndex: 1,
    top: 8,
    width: 32,
    height: 32,
    borderRadius: 16,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "rgba(255,255,255,0.94)",
  },
  heartBadge: { right: 8 },
  deleteBadge: { left: 8 },
  heartText: { fontSize: 17, fontWeight: "800" },
  deleteText: { fontSize: 14, lineHeight: 18 },
  removingOverlay: {
    ...StyleSheet.absoluteFillObject,
    zIndex: 2,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "rgba(26,10,20,0.38)",
  },
});
