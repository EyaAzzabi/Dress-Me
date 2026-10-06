import { useFocusEffect } from "@react-navigation/native";
import * as ImagePicker from "expo-image-picker";
import { useCallback, useState } from "react";
import { ActivityIndicator, FlatList, Image, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { getMe } from "@/api/auth";
import { setAvatar, tryOnGarment } from "@/api/tryon";
import { listWardrobeItems, uploadPhoto } from "@/api/wardrobe";
import { Button } from "@/components/Button";
import { ScreenSubtitle, ScreenTitle, SectionLabel } from "@/components/Typography";
import { useTheme } from "@/theme/ThemeContext";
import { radius, spacing } from "@/theme/tokens";
import { ClothingItem } from "@/types/models";

export default function TryOnScreen() {
  const { colors } = useTheme();
  const [avatarUrl, setAvatarUrl] = useState<string | null>(null);
  const [wardrobe, setWardrobe] = useState<ClothingItem[]>([]);
  const [selectedItemId, setSelectedItemId] = useState<string | null>(null);
  const [resultUrl, setResultUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [uploadingAvatar, setUploadingAvatar] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useFocusEffect(
    useCallback(() => {
      let active = true;
      setLoading(true);
      Promise.all([getMe(), listWardrobeItems()])
        .then(([me, items]) => {
          if (!active) return;
          setAvatarUrl(me.avatar_photo_url);
          setWardrobe(items);
        })
        .finally(() => active && setLoading(false));
      return () => {
        active = false;
      };
    }, [])
  );

  async function handleChangeAvatar() {
    const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!permission.granted) return;
    const picked = await ImagePicker.launchImageLibraryAsync({ quality: 0.8 });
    if (picked.canceled) return;

    setUploadingAvatar(true);
    setError(null);
    try {
      const imageUrl = await uploadPhoto(picked.assets[0].uri);
      await setAvatar(imageUrl);
      setAvatarUrl(imageUrl);
    } catch {
      setError("Couldn't save your photo — try again.");
    } finally {
      setUploadingAvatar(false);
    }
  }

  async function handleTryOn() {
    if (!selectedItemId) return;
    setGenerating(true);
    setError(null);
    setResultUrl(null);
    try {
      const url = await tryOnGarment(selectedItemId);
      setResultUrl(url);
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? "Virtual try-on isn't available right now.");
    } finally {
      setGenerating(false);
    }
  }

  if (loading) {
    return (
      <View style={[styles.centered, { backgroundColor: colors.bg }]}>
        <ActivityIndicator color={colors.primary} />
      </View>
    );
  }

  return (
    <ScrollView style={{ backgroundColor: colors.bg }} contentContainerStyle={styles.container}>
      <ScreenTitle>Try it on</ScreenTitle>
      <ScreenSubtitle>See how a piece looks on you before you commit to an outfit.</ScreenSubtitle>

      <Pressable
        onPress={handleChangeAvatar}
        style={[styles.avatarBox, { backgroundColor: colors.surface, borderColor: colors.border }]}
      >
        {avatarUrl ? (
          <Image source={{ uri: avatarUrl }} style={styles.avatarImage} />
        ) : (
          <Text style={{ color: colors.textSubtle }}>Tap to add your photo</Text>
        )}
        {uploadingAvatar && <ActivityIndicator style={StyleSheet.absoluteFill} color={colors.primary} />}
      </Pressable>
      {avatarUrl && (
        <Button title="Change photo" variant="ghost" onPress={handleChangeAvatar} />
      )}

      <SectionLabel style={styles.sectionLabel}>Pick a piece</SectionLabel>
      <FlatList
        data={wardrobe}
        keyExtractor={(item) => item.id}
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.pieceRow}
        renderItem={({ item }) => {
          const selected = selectedItemId === item.id;
          return (
            <Pressable onPress={() => setSelectedItemId(item.id)}>
              <Image
                source={{ uri: item.image_url }}
                style={[styles.pieceImage, { borderColor: selected ? colors.primary : "transparent" }]}
              />
            </Pressable>
          );
        }}
        ListEmptyComponent={
          <Text style={{ color: colors.textMuted }}>Add some wardrobe items first.</Text>
        }
      />

      {error && <Text style={[styles.error, { color: colors.error }]}>{error}</Text>}

      <Button
        title="Try it on"
        onPress={handleTryOn}
        disabled={!avatarUrl || !selectedItemId}
        loading={generating}
      />

      {resultUrl && (
        <View style={styles.resultBox}>
          <SectionLabel>Result</SectionLabel>
          <Image source={{ uri: resultUrl }} style={styles.resultImage} />
        </View>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { padding: spacing.xl, gap: spacing.md },
  centered: { flex: 1, alignItems: "center", justifyContent: "center" },
  avatarBox: {
    height: 280,
    borderRadius: radius.lg,
    borderWidth: 1,
    alignItems: "center",
    justifyContent: "center",
    overflow: "hidden",
  },
  avatarImage: { width: "100%", height: "100%" },
  sectionLabel: { marginTop: spacing.sm },
  pieceRow: { gap: spacing.sm },
  pieceImage: { width: 90, height: 90, borderRadius: radius.md, borderWidth: 2 },
  error: { fontSize: 13 },
  resultBox: { gap: spacing.sm, marginTop: spacing.md },
  resultImage: { width: "100%", height: 400, borderRadius: radius.lg, backgroundColor: "#eee" },
});
