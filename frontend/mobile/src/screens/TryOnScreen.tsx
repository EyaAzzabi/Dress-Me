import { useFocusEffect } from "@react-navigation/native";
import * as ImagePicker from "expo-image-picker";
import { useCallback, useState } from "react";
import { isAxiosError } from "axios";
import {
    ActivityIndicator,
    FlatList,
    Image,
    Pressable,
    ScrollView,
    StyleSheet,
    Text,
    View,
} from "react-native";


import { platformShadow } from "@/utils/platformStyles";
import { getMe } from "@/api/auth";
import { setAvatar, tryOnGarment } from "@/api/tryon";
import { listWardrobeItems, uploadPhoto } from "@/api/wardrobe";
import { TunisianPhotoHero } from "@/components/TunisianPhotoHero";
import { useTheme } from "@/theme/ThemeContext";
import { radius, spacing } from "@/theme/tokens";
import { ClothingItem } from "@/types/models";

function getTryOnErrorMessage(error: unknown): string {
  if (isAxiosError(error) && error.response?.status === 503) {
    return "L’essayage virtuel n’est pas encore activé sur ce serveur. L’administrateur doit renseigner REPLICATE_API_TOKEN et REPLICATE_TRYON_MODEL_VERSION dans backend/.env, puis redémarrer l’API. Ne partage pas ton token dans le chat.";
  }
  if (isAxiosError(error) && typeof error.response?.data?.detail === "string") {
    return error.response.data.detail;
  }
  return "L’essayage virtuel est indisponible pour le moment. Réessaie plus tard.";
}

export default function TryOnScreen() {
  const { colors } = useTheme();
  const [avatarUrl, setAvatarUrl]       = useState<string | null>(null);
  const [wardrobe, setWardrobe]         = useState<ClothingItem[]>([]);
  const [selectedItemId, setSelectedItemId] = useState<string | null>(null);
  const [resultUrl, setResultUrl]       = useState<string | null>(null);
  const [loading, setLoading]           = useState(true);
  const [uploadingAvatar, setUploadingAvatar] = useState(false);
  const [generating, setGenerating]     = useState(false);
  const [error, setError]               = useState<string | null>(null);

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
      return () => { active = false; };
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
    } catch (err: unknown) {
      setError(getTryOnErrorMessage(err));
    } finally {
      setGenerating(false);
    }
  }

  if (loading) {
    return (
      <View style={[styles.centered, { backgroundColor: colors.bg }]}>
        <ActivityIndicator color={colors.primary} size="large" />
        <Text style={[styles.loadingText, { color: colors.textMuted }]}>Loading…</Text>
      </View>
    );
  }

  return (
    <ScrollView
      style={{ backgroundColor: colors.bg }}
      contentContainerStyle={styles.root}
      showsVerticalScrollIndicator={false}
    >
      <TunisianPhotoHero
        icon="✧"
        title="Essayage virtuel"
        subtitle="Imagine ton prochain look avant de le porter"
      />

      <View style={styles.content}>
        {/* ── Avatar section ── */}
        <Text style={[styles.sectionTitle, { color: colors.text }]}>Your photo</Text>
        <Pressable
          onPress={handleChangeAvatar}
          style={[styles.avatarBox, {
            backgroundColor: colors.surface,
            borderColor: avatarUrl ? colors.primary : colors.border,
            ...platformShadow(colors.primary),
          }]}
        >
          {avatarUrl ? (
            <Image source={{ uri: avatarUrl }} style={styles.avatarImage} />
          ) : (
            <View style={styles.avatarEmpty}>
              <Text style={styles.avatarEmoji}>🤳</Text>
              <Text style={[styles.avatarHint, { color: colors.textMuted }]}>
                Tap to add a full-body photo
              </Text>
            </View>
          )}
          {uploadingAvatar && (
            <View style={[styles.avatarOverlay, { backgroundColor: "rgba(0,0,0,0.4)" }]}>
              <ActivityIndicator color="#FFFFFF" size="large" />
            </View>
          )}
          {/* Change badge */}
          {avatarUrl && (
            <View style={[styles.changeBadge, { backgroundColor: colors.primary }]}>
              <Text style={styles.changeBadgeText}>Change ✎</Text>
            </View>
          )}
        </Pressable>

        {/* ── Garment picker ── */}
        <Text style={[styles.sectionTitle, { color: colors.text }]}>Choose a piece</Text>
        {wardrobe.length === 0 ? (
          <View style={[styles.emptyRow, { borderColor: colors.border }]}>
            <Text style={[styles.emptyText, { color: colors.textMuted }]}>
              Add items to your wardrobe first.
            </Text>
          </View>
        ) : (
          <FlatList
            data={wardrobe}
            keyExtractor={(item) => item.id}
            horizontal
            showsHorizontalScrollIndicator={false}
            contentContainerStyle={styles.garmentRow}
            scrollEnabled
            renderItem={({ item }) => {
              const selected = selectedItemId === item.id;
              return (
                <Pressable
                  onPress={() => setSelectedItemId(item.id)}
                  style={[
                    styles.garmentCard,
                    {
                      borderColor: selected ? colors.primary : colors.border,
                      backgroundColor: selected ? colors.surface : colors.surfaceElevated,
                      ...platformShadow(colors.primary),
                    },
                  ]}
                >
                  <Image source={{ uri: item.image_url }} style={styles.garmentImage} />
                  {selected && (
                    <View style={[styles.selectedBadge, { backgroundColor: colors.primary }]}>
                      <Text style={styles.selectedBadgeText}>✓</Text>
                    </View>
                  )}
                  {item.category && (
                    <Text style={[styles.garmentLabel, { color: colors.textMuted }]} numberOfLines={1}>
                      {item.category}
                    </Text>
                  )}
                </Pressable>
              );
            }}
          />
        )}

        {error && (
          <View style={[styles.errorBox, { backgroundColor: colors.errorBg, borderColor: colors.error }]}>
            <Text style={[styles.errorText, { color: colors.error }]}>⚠ {error}</Text>
          </View>
        )}

        {/* ── CTA ── */}
        <Pressable
          onPress={handleTryOn}
          disabled={!avatarUrl || !selectedItemId || generating}
          style={[
            styles.tryBtn,
            {
              backgroundColor: (!avatarUrl || !selectedItemId) ? colors.border : colors.primary,
              ...platformShadow(colors.primary),
            },
          ]}
        >
          {generating
            ? <ActivityIndicator color="#FFFFFF" />
            : <>
                <Text style={styles.tryBtnIcon}>🪄</Text>
                <Text style={styles.tryBtnText}>
                  {!avatarUrl ? "Add a photo first" : !selectedItemId ? "Select a piece" : "Try it on"}
                </Text>
              </>
          }
        </Pressable>

        {/* ── Result ── */}
        {resultUrl && (
          <View style={[styles.resultCard, {
            backgroundColor: colors.surfaceElevated,
            borderColor: colors.primary,
            ...platformShadow(colors.primary),
          }]}>
            <View style={[styles.resultAccent, { backgroundColor: colors.primary }]} />
            <View style={styles.resultBody}>
              <Text style={[styles.resultTitle, { color: colors.text }]}>✨ Your look</Text>
              <Image source={{ uri: resultUrl }} style={styles.resultImage} />
            </View>
          </View>
        )}
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  centered:    { flex: 1, alignItems: "center", justifyContent: "center", gap: 12 },
  loadingText: { fontSize: 14 },
  root:        { flexGrow: 1 },

  hero: {
    paddingTop: 50,
    paddingBottom: 44,
    overflow: "hidden",
    position: "relative",
  },
  blob1: { position: "absolute", width: 200, height: 200, borderRadius: 100, top: -60, right: -40, opacity: 0.35 },
  heroContent: { alignItems: "center", gap: 4, zIndex: 2 },
  heroEmoji:   { fontSize: 40 },
  heroTitle:   { fontSize: 26, fontWeight: "800", color: "#FFFFFF", letterSpacing: -0.3 },
  heroSub:     { fontSize: 13, color: "rgba(255,255,255,0.8)" },
  heroCurve: {
    position: "absolute",
    bottom: -2, left: -20, right: -20,
    height: 36,
    borderTopLeftRadius: 36,
    borderTopRightRadius: 36,
  },

  content: { padding: spacing.xl, gap: spacing.lg },

  sectionTitle: { fontSize: 16, fontWeight: "700" },

  avatarBox: {
    height: 260,
    borderRadius: radius.lg,
    borderWidth: 2,
    overflow: "hidden",
    ...platformShadow("#17235B", { x: 0, y: 4, opacity: 0.12, radius: 12 }),
    position: "relative",
  },
  avatarImage:   { width: "100%", height: "100%" },
  avatarEmpty:   { flex: 1, alignItems: "center", justifyContent: "center", gap: 8 },
  avatarEmoji:   { fontSize: 44 },
  avatarHint:    { fontSize: 14 },
  avatarOverlay: {
    ...StyleSheet.absoluteFillObject,
    alignItems: "center",
    justifyContent: "center",
  },
  changeBadge: {
    position: "absolute",
    bottom: 12,
    right: 12,
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: radius.pill,
  },
  changeBadgeText: { color: "#FFFFFF", fontSize: 12, fontWeight: "700" },

  emptyRow: {
    padding: spacing.xl,
    borderRadius: radius.lg,
    borderWidth: 1.5,
    borderStyle: "dashed",
    alignItems: "center",
  },
  emptyText: { fontSize: 14 },

  garmentRow:  { gap: spacing.md },
  garmentCard: {
    width: 100,
    borderRadius: radius.md,
    borderWidth: 2,
    overflow: "hidden",
    ...platformShadow("#17235B", { x: 0, y: 2, opacity: 0.08, radius: 6 }),
    position: "relative",
  },
  garmentImage: { width: "100%", height: 100 },
  garmentLabel: { fontSize: 11, textAlign: "center", padding: 4 },
  selectedBadge: {
    position: "absolute",
    top: 6,
    right: 6,
    width: 22,
    height: 22,
    borderRadius: 11,
    alignItems: "center",
    justifyContent: "center",
  },
  selectedBadgeText: { color: "#FFFFFF", fontSize: 12, fontWeight: "800" },

  errorBox:  { padding: spacing.md, borderRadius: radius.md, borderWidth: 1 },
  errorText: { fontSize: 13, fontWeight: "500" },

  tryBtn: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: spacing.sm,
    paddingVertical: 16,
    borderRadius: radius.pill,
    ...platformShadow("#17235B", { x: 0, y: 6, opacity: 0.25, radius: 12 }),
  },
  tryBtnIcon: { fontSize: 20 },
  tryBtnText: { color: "#FFFFFF", fontSize: 16, fontWeight: "700" },

  resultCard: {
    borderRadius: radius.lg,
    borderWidth: 2,
    overflow: "hidden",
    ...platformShadow("#17235B", { x: 0, y: 4, opacity: 0.15, radius: 14 }),
  },
  resultAccent: { height: 4 },
  resultBody:   { padding: spacing.lg, gap: spacing.md },
  resultTitle:  { fontSize: 18, fontWeight: "700" },
  resultImage:  { width: "100%", height: 420, borderRadius: radius.md, backgroundColor: "#f0f0f0" },
});
