import { useFocusEffect } from "@react-navigation/native";
import { useCallback, useState } from "react";
import { ActivityIndicator, FlatList, Image, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import {
  checkPackingItem,
  createPackingList,
  deletePackingList,
  listPackingLists,
  PackingList,
  TripType,
} from "@/api/packing";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { Pill } from "@/components/Pill";
import { SectionLabel } from "@/components/Typography";
import { TextField } from "@/components/TextField";
import { TunisianPhotoHero } from "@/components/TunisianPhotoHero";
import { useTheme } from "@/theme/ThemeContext";
import { radius, spacing } from "@/theme/tokens";

const TRIP_TYPES: { value: TripType; label: string }[] = [
  { value: "plage", label: "Beach" },
  { value: "business", label: "Business" },
  { value: "tourisme", label: "Sightseeing" },
];

export default function PackingScreen() {
  const { colors } = useTheme();
  const [lists, setLists] = useState<PackingList[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [destination, setDestination] = useState("");
  const [durationDays, setDurationDays] = useState("3");
  const [tripType, setTripType] = useState<TripType>("plage");
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(() => {
    setLoading(true);
    return listPackingLists()
      .then(setLists)
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

  async function handleGenerate() {
    const duration = parseInt(durationDays, 10);
    if (!destination.trim() || !duration || duration < 1) {
      setError("Enter a destination and a valid number of days.");
      return;
    }
    setError(null);
    setCreating(true);
    try {
      const created = await createPackingList(destination.trim(), duration, tripType);
      setLists((prev) => [created, ...prev]);
      setDestination("");
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? "Something went wrong — try again.");
    } finally {
      setCreating(false);
    }
  }

  async function handleToggleItem(list: PackingList, itemId: string) {
    const checked = !list.checked_item_ids.includes(itemId);
    const updated = await checkPackingItem(list.id, itemId, checked);
    setLists((prev) => prev.map((l) => (l.id === updated.id ? updated : l)));
  }

  async function handleDelete(id: string) {
    await deletePackingList(id);
    setLists((prev) => prev.filter((l) => l.id !== id));
  }

  return (
    <ScrollView style={{ backgroundColor: colors.bg }} contentContainerStyle={styles.container}>
      <TunisianPhotoHero
        icon="✧"
        title="Prête pour le voyage"
        subtitle="Emporte tes essentiels, de Sidi Bou aux vacances"
        image="wardrobe"
      />

      <Card style={styles.formCard}>
        <TextField placeholder="Destination" value={destination} onChangeText={setDestination} />
        <TextField
          placeholder="Number of days"
          keyboardType="number-pad"
          value={durationDays}
          onChangeText={setDurationDays}
        />
        <View style={styles.pillRow}>
          {TRIP_TYPES.map((t) => (
            <Pill key={t.value} label={t.label} active={tripType === t.value} onPress={() => setTripType(t.value)} />
          ))}
        </View>
        {error && <Text style={[styles.error, { color: colors.error }]}>{error}</Text>}
        <Button title="Generate packing list" onPress={handleGenerate} loading={creating} />
      </Card>

      {loading ? (
        <ActivityIndicator color={colors.primary} style={styles.spinner} />
      ) : (
        lists.map((list) => (
          <Card key={list.id} style={styles.listCard}>
            <View style={styles.listHeader}>
              <View>
                <Text style={[styles.destination, { color: colors.text }]}>{list.destination}</Text>
                <SectionLabel>
                  {list.duration_days} days · {TRIP_TYPES.find((t) => t.value === list.trip_type)?.label ?? list.trip_type}
                </SectionLabel>
              </View>
              <Pressable onPress={() => handleDelete(list.id)}>
                <Text style={{ color: colors.error, fontSize: 13 }}>Delete</Text>
              </Pressable>
            </View>

            <FlatList
              data={list.items}
              keyExtractor={(item) => item.id}
              scrollEnabled={false}
              renderItem={({ item }) => {
                const checked = list.checked_item_ids.includes(item.id);
                return (
                  <Pressable onPress={() => handleToggleItem(list, item.id)} style={styles.checkRow}>
                    <View
                      style={[
                        styles.checkbox,
                        {
                          borderColor: colors.borderStrong,
                          backgroundColor: checked ? colors.primary : "transparent",
                        },
                      ]}
                    >
                      {checked && <Text style={styles.checkMark}>✓</Text>}
                    </View>
                    <Image source={{ uri: item.image_url }} style={styles.checkImage} />
                    <Text
                      style={[
                        styles.checkLabel,
                        { color: colors.text, textDecorationLine: checked ? "line-through" : "none" },
                      ]}
                    >
                      {item.category ?? "Item"}
                    </Text>
                  </Pressable>
                );
              }}
              ListEmptyComponent={
                <Text style={{ color: colors.textMuted, fontSize: 13 }}>
                  Not enough wardrobe items to pack for this trip yet.
                </Text>
              }
            />
          </Card>
        ))
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { padding: spacing.xl, gap: spacing.md },
  formCard: { padding: spacing.lg, gap: spacing.sm },
  pillRow: { flexDirection: "row", gap: spacing.sm, flexWrap: "wrap" },
  error: { fontSize: 13 },
  spinner: { marginTop: spacing.xl },
  listCard: { padding: spacing.lg, gap: spacing.sm },
  listHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start" },
  destination: { fontSize: 16, fontWeight: "700" },
  checkRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingVertical: spacing.xs },
  checkbox: {
    width: 22,
    height: 22,
    borderRadius: radius.sm,
    borderWidth: 1.5,
    alignItems: "center",
    justifyContent: "center",
  },
  checkMark: { color: "#fff", fontSize: 13, fontWeight: "700" },
  checkImage: { width: 36, height: 36, borderRadius: radius.sm },
  checkLabel: { fontSize: 14, textTransform: "capitalize" },
});
