import { useCallback, useState } from "react";
import { useFocusEffect } from "@react-navigation/native";
import { FlatList, Image, StyleSheet, Text, View } from "react-native";

import { listWardrobeItems } from "@/api/wardrobe";
import { ClothingItem } from "@/types/models";

export default function WardrobeScreen() {
  const [items, setItems] = useState<ClothingItem[]>([]);
  const [loading, setLoading] = useState(true);

  useFocusEffect(
    useCallback(() => {
      let active = true;
      setLoading(true);
      listWardrobeItems()
        .then((data) => active && setItems(data))
        .finally(() => active && setLoading(false));
      return () => {
        active = false;
      };
    }, [])
  );

  if (loading) return <Text style={styles.centered}>Loading wardrobe…</Text>;

  return (
    <FlatList
      data={items}
      keyExtractor={(item) => item.id}
      numColumns={2}
      contentContainerStyle={styles.list}
      ListEmptyComponent={
        <Text style={styles.centered}>No items yet — add your first piece of clothing.</Text>
      }
      renderItem={({ item }) => (
        <View style={styles.card}>
          <Image source={{ uri: item.image_url }} style={styles.image} />
          <Text style={styles.label}>{item.category ?? "Uncategorized"}</Text>
        </View>
      )}
    />
  );
}

const styles = StyleSheet.create({
  list: { padding: 12, gap: 12 },
  card: { flex: 1, margin: 6, alignItems: "center" },
  image: { width: 150, height: 150, borderRadius: 12, backgroundColor: "#eee" },
  label: { marginTop: 4, fontSize: 14 },
  centered: { textAlign: "center", marginTop: 40, color: "#666" },
});
