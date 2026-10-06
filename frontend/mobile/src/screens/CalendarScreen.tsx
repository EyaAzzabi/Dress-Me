import { useFocusEffect } from "@react-navigation/native";
import { useCallback, useState } from "react";
import { ActivityIndicator, FlatList, Image, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { listPlannedOutfits, planOutfit, ScheduledOutfit, unplanOutfit } from "@/api/calendar";
import { listWardrobeItems } from "@/api/wardrobe";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { ScreenTitle } from "@/components/Typography";
import { useTheme } from "@/theme/ThemeContext";
import { radius, spacing } from "@/theme/tokens";
import { ClothingItem } from "@/types/models";

function toDay(date: Date): string {
  return date.toISOString().slice(0, 10);
}

function startOfMonth(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), 1);
}

function endOfMonth(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth() + 1, 0);
}

function buildMonthGrid(monthAnchor: Date): (Date | null)[] {
  const first = startOfMonth(monthAnchor);
  const last = endOfMonth(monthAnchor);
  // Monday-first grid, matching the HTML's week layout.
  const leadingBlanks = (first.getDay() + 6) % 7;
  const days: (Date | null)[] = Array(leadingBlanks).fill(null);
  for (let d = 1; d <= last.getDate(); d++) {
    days.push(new Date(monthAnchor.getFullYear(), monthAnchor.getMonth(), d));
  }
  while (days.length % 7 !== 0) days.push(null);
  return days;
}

export default function CalendarScreen() {
  const { colors } = useTheme();
  const [monthAnchor, setMonthAnchor] = useState(() => new Date());
  const [scheduled, setScheduled] = useState<Record<string, ScheduledOutfit>>({});
  const [loading, setLoading] = useState(true);
  const [selectedDay, setSelectedDay] = useState<string | null>(null);
  const [picking, setPicking] = useState(false);
  const [wardrobe, setWardrobe] = useState<ClothingItem[]>([]);
  const [selectedItemIds, setSelectedItemIds] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);

  const reload = useCallback(() => {
    setLoading(true);
    const start = toDay(startOfMonth(monthAnchor));
    const end = toDay(endOfMonth(monthAnchor));
    return listPlannedOutfits(start, end)
      .then((list) => {
        const byDay: Record<string, ScheduledOutfit> = {};
        for (const s of list) byDay[s.date] = s;
        setScheduled(byDay);
      })
      .finally(() => setLoading(false));
  }, [monthAnchor]);

  useFocusEffect(
    useCallback(() => {
      let active = true;
      reload().catch(() => active && undefined);
      return () => {
        active = false;
      };
    }, [reload])
  );

  function changeMonth(delta: number) {
    setSelectedDay(null);
    setPicking(false);
    setMonthAnchor((prev) => new Date(prev.getFullYear(), prev.getMonth() + delta, 1));
  }

  function selectDay(day: string) {
    setSelectedDay(day);
    setPicking(false);
  }

  async function startPicking() {
    setPicking(true);
    setSelectedItemIds(selectedDay && scheduled[selectedDay] ? scheduled[selectedDay].item_ids : []);
    if (wardrobe.length === 0) {
      const items = await listWardrobeItems();
      setWardrobe(items);
    }
  }

  function toggleItem(id: string) {
    setSelectedItemIds((prev) => (prev.includes(id) ? prev.filter((i) => i !== id) : [...prev, id]));
  }

  async function confirmPlan() {
    if (!selectedDay) return;
    setSaving(true);
    try {
      const result = await planOutfit(selectedDay, selectedItemIds);
      setScheduled((prev) => ({ ...prev, [selectedDay]: result }));
      setPicking(false);
    } finally {
      setSaving(false);
    }
  }

  async function handleUnplan() {
    if (!selectedDay) return;
    await unplanOutfit(selectedDay);
    setScheduled((prev) => {
      const next = { ...prev };
      delete next[selectedDay];
      return next;
    });
  }

  const days = buildMonthGrid(monthAnchor);
  const monthLabel = monthAnchor.toLocaleDateString(undefined, { month: "long", year: "numeric" });
  const detail = selectedDay ? scheduled[selectedDay] : null;

  return (
    <ScrollView style={{ backgroundColor: colors.bg }} contentContainerStyle={styles.container}>
      <ScreenTitle>Calendar</ScreenTitle>

      <View style={styles.monthNav}>
        <Pressable onPress={() => changeMonth(-1)}>
          <Text style={[styles.monthArrow, { color: colors.primary }]}>‹</Text>
        </Pressable>
        <Text style={[styles.monthLabel, { color: colors.text }]}>{monthLabel}</Text>
        <Pressable onPress={() => changeMonth(1)}>
          <Text style={[styles.monthArrow, { color: colors.primary }]}>›</Text>
        </Pressable>
      </View>

      {loading ? (
        <ActivityIndicator color={colors.primary} style={styles.spinner} />
      ) : (
        <View style={styles.grid}>
          {days.map((date, i) => {
            if (!date) return <View key={i} style={styles.cell} />;
            const day = toDay(date);
            const isPlanned = Boolean(scheduled[day]);
            const isSelected = selectedDay === day;
            return (
              <Pressable
                key={i}
                onPress={() => selectDay(day)}
                style={[
                  styles.cell,
                  styles.dayCell,
                  { borderColor: isSelected ? colors.primary : "transparent" },
                ]}
              >
                <Text style={[styles.dayNumber, { color: colors.text }]}>{date.getDate()}</Text>
                {isPlanned && <View style={[styles.dot, { backgroundColor: colors.primary }]} />}
              </Pressable>
            );
          })}
        </View>
      )}

      {selectedDay && (
        <Card style={styles.detailCard}>
          <Text style={[styles.detailTitle, { color: colors.text }]}>{selectedDay}</Text>

          {!picking && detail && detail.items.length > 0 && (
            <>
              <FlatList
                horizontal
                data={detail.items}
                keyExtractor={(item) => item.id}
                showsHorizontalScrollIndicator={false}
                contentContainerStyle={styles.detailItems}
                renderItem={({ item }) => (
                  <Image source={{ uri: item.image_url }} style={styles.detailImage} />
                )}
              />
              <View style={styles.detailActions}>
                <Button title="Change outfit" variant="small" onPress={startPicking} />
                <Button title="Remove" variant="ghost" onPress={handleUnplan} />
              </View>
            </>
          )}

          {!picking && !detail && (
            <Button title="Plan an outfit" variant="small" onPress={startPicking} />
          )}

          {picking && (
            <>
              <Text style={[styles.pickHint, { color: colors.textMuted }]}>
                Pick the pieces you'll wear this day.
              </Text>
              <FlatList
                data={wardrobe}
                keyExtractor={(item) => item.id}
                numColumns={3}
                contentContainerStyle={styles.pickGrid}
                renderItem={({ item }) => {
                  const selected = selectedItemIds.includes(item.id);
                  return (
                    <Pressable onPress={() => toggleItem(item.id)} style={styles.pickCell}>
                      <Image
                        source={{ uri: item.image_url }}
                        style={[
                          styles.pickImage,
                          { borderColor: selected ? colors.primary : "transparent" },
                        ]}
                      />
                    </Pressable>
                  );
                }}
              />
              <View style={styles.detailActions}>
                <Button title="Save" variant="small" onPress={confirmPlan} loading={saving} />
                <Button title="Cancel" variant="ghost" onPress={() => setPicking(false)} />
              </View>
            </>
          )}
        </Card>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { padding: spacing.xl, gap: spacing.md },
  monthNav: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.xl },
  monthArrow: { fontSize: 24, fontWeight: "700" },
  monthLabel: { fontSize: 16, fontWeight: "600", textTransform: "capitalize" },
  spinner: { marginTop: spacing.xl },
  grid: { flexDirection: "row", flexWrap: "wrap" },
  cell: { width: "14.28%", aspectRatio: 1, alignItems: "center", justifyContent: "center" },
  dayCell: { borderWidth: 1.5, borderRadius: radius.sm },
  dayNumber: { fontSize: 14 },
  dot: { width: 5, height: 5, borderRadius: 3, marginTop: 2 },
  detailCard: { padding: spacing.lg, gap: spacing.sm },
  detailTitle: { fontSize: 15, fontWeight: "700" },
  detailItems: { gap: spacing.sm },
  detailImage: { width: 80, height: 80, borderRadius: radius.md },
  detailActions: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.xs },
  pickHint: { fontSize: 13 },
  pickGrid: { gap: spacing.xs },
  pickCell: { width: "33.33%", padding: 4 },
  pickImage: { width: "100%", height: 90, borderRadius: radius.sm, borderWidth: 2 },
});
