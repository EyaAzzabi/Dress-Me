import { useFocusEffect } from "@react-navigation/native";
import * as ImagePicker from "expo-image-picker";
import { useCallback, useMemo, useState } from "react";
import { ActivityIndicator, Image, ScrollView, StyleSheet, Text, View } from "react-native";

import { addWardrobeItem, listWardrobeItems, uploadPhoto } from "@/api/wardrobe";
import { Button } from "@/components/Button";
import { ScreenTitle, SectionLabel } from "@/components/Typography";
import { useTheme } from "@/theme/ThemeContext";
import { radius, spacing } from "@/theme/tokens";
import { ClothingItem } from "@/types/models";
import { notify } from "@/utils/notify";

function groupByCategory(items: ClothingItem[]): [string, ClothingItem[]][] {
  const groups = new Map<string, ClothingItem[]>();
  for (const item of items) {
    const category = item.category ?? "Uncategorized";
    const existing = groups.get(category);
    if (existing) existing.push(item);
    else groups.set(category, [item]);
  }
  return Array.from(groups.entries());
}

export default function WardrobeScreen() {
  const { colors } = useTheme();
  const [items, setItems] = useState<ClothingItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [adding, setAdding] = useState(false);

  const reload = useCallback(() => {
    setLoading(true);
    return listWardrobeItems()
      .then(setItems)
      .finally(() => setLoading(false));
  }, []);

  useFocusEffect(
    useCallback(() => {
      let active = true;
      reload().catch(() => active && undefined);
      return () => {
        active = false;
      };
    }, [reload])
  );

  async function handleAddItem() {
    const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!permission.granted) return;

    const picked = await ImagePicker.launchImageLibraryAsync({ quality: 0.8 });
    if (picked.canceled) return;

    setAdding(true);
    try {
      const imageUrl = await uploadPhoto(picked.assets[0].uri);
      await addWardrobeItem(imageUrl);
      await reload();
    } catch (error: any) {
      const detail = error?.response?.data?.detail;
      notify("Couldn't add item", detail ?? "Something went wrong — try again.");
    } finally {
      setAdding(false);
    }
  }

  const groups = useMemo(() => groupByCategory(items), [items]);

  if (loading) {
    return (
      <View style={[styles.centered, { backgroundColor: colors.bg }]}>
        <ActivityIndicator color={colors.primary} />
      </View>
    );
  }

  return (
    <View style={[styles.container, { backgroundColor: colors.bg }]}>
      <View style={styles.header}>
        <ScreenTitle>Wardrobe</ScreenTitle>
        <Button title="Add item" variant="small" onPress={handleAddItem} loading={adding} />
      </View>

      <ScrollView contentContainerStyle={styles.list}>
        {groups.length === 0 && (
          <Text style={[styles.empty, { color: colors.textMuted }]}>
            No items yet — add your first piece of clothing.
          </Text>
        )}

        {groups.map(([category, categoryItems]) => (
          <View key={category} style={styles.section}>
            <SectionLabel style={styles.sectionLabel}>
              {category} ({categoryItems.length})
            </SectionLabel>
            <View style={styles.grid}>
              {categoryItems.map((item) => (
                <View key={item.id} style={[styles.card, { backgroundColor: colors.surface }]}>
                  <Image source={{ uri: item.image_url }} style={styles.image} />
                </View>
              ))}
            </View>
          </View>
        ))}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  centered: { flex: 1, alignItems: "center", justifyContent: "center" },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: spacing.xl,
    paddingTop: spacing.xl,
    paddingBottom: spacing.md,
  },
  list: { paddingHorizontal: spacing.lg, paddingBottom: spacing.xl },
  section: { marginBottom: spacing.lg },
  sectionLabel: { marginBottom: spacing.sm, paddingHorizontal: spacing.xs, textTransform: "capitalize" },
  grid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.md },
  card: { width: "47%", borderRadius: radius.lg, overflow: "hidden", padding: spacing.sm },
  image: { width: "100%", height: 150, borderRadius: radius.md },
  empty: { textAlign: "center", marginTop: 40 },
});
