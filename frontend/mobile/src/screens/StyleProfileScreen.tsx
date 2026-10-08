import { useFocusEffect } from "@react-navigation/native";
import { useCallback, useState } from "react";
import {
    ActivityIndicator,
    Image,
    ImageBackground,
    Pressable,
    ScrollView,
    StyleSheet,
    Text,
    View,
} from "react-native";


import { platformShadow } from "@/utils/platformStyles";
import { getMe } from "@/api/auth";
import { getStyleProfile, StyleProfile } from "@/api/styleProfile";
import { DressMeLogo } from "@/components/DressMeLogo";
import { useAuth } from "@/context/AuthContext";
import { useTheme } from "@/theme/ThemeContext";
import { radius, spacing } from "@/theme/tokens";

interface QuickLinkProps {
  icon: string;
  label: string;
  onPress: () => void;
}
function QuickLink({ icon, label, onPress }: QuickLinkProps) {
  const { colors } = useTheme();
  return (
    <Pressable
      onPress={onPress}
      style={[styles.ql, {
        backgroundColor: colors.surfaceElevated,
        borderColor: colors.border,
        ...platformShadow(colors.primary),
      }]}
    >
      <Text style={styles.qlIcon}>{icon}</Text>
      <Text style={[styles.qlLabel, { color: colors.text }]}>{label}</Text>
      <Text style={[styles.qlArrow, { color: colors.primary }]}>›</Text>
    </Pressable>
  );
}

export default function StyleProfileScreen({
  onGoToPacking,
  onGoToTryOn,
  onGoToCalendar,
}: {
  onGoToPacking: () => void;
  onGoToTryOn: () => void;
  onGoToCalendar: () => void;
}) {
  const { colors } = useTheme();
  const { logout } = useAuth();
  const [profile, setProfile]   = useState<StyleProfile | null>(null);
  const [avatarUrl, setAvatarUrl] = useState<string | null>(null);
  const [loading, setLoading]   = useState(true);

  useFocusEffect(
    useCallback(() => {
      let active = true;
      setLoading(true);
      Promise.all([getStyleProfile(), getMe()])
        .then(([profileData, me]) => {
          if (!active) return;
          setProfile(profileData);
          setAvatarUrl(me.avatar_photo_url);
        })
        .finally(() => active && setLoading(false));
      return () => { active = false; };
    }, [])
  );

  const maxCategoryCount = profile
    ? Math.max(1, ...Object.values(profile.category_counts))
    : 1;

  return (
    <ScrollView
      style={{ backgroundColor: colors.bg }}
      contentContainerStyle={styles.root}
      showsVerticalScrollIndicator={false}
    >
      {/* ── Bande hero tunisienne ── */}
      <ImageBackground
        source={require("@/assets/sidi-bou-coast-inspiration.jpg")}
        resizeMode="cover"
        style={styles.hero}
      >
        <View style={[styles.heroTint, { backgroundColor: colors.tunisianNavy }]} />
        {/* Avatar centré dans la bande */}
        <View style={styles.avatarWrapper}>
          <View style={[styles.avatarRing, { borderColor: "#FFFFFF" }]}>
            <View style={[styles.avatarInner, { backgroundColor: colors.surface }]}>
              {avatarUrl
                ? <Image source={{ uri: avatarUrl }} style={styles.avatarImage} />
                : <Text style={styles.avatarPlaceholder}>👤</Text>}
            </View>
          </View>
        </View>
        <View style={[styles.heroCurve, { backgroundColor: colors.bg }]} />
      </ImageBackground>

      {/* Logo hors overflow */}
      <View style={styles.logoZone}>
        <DressMeLogo width={180} showTagline={false} />
      </View>

      <View style={styles.content}>
        {loading && (
          <ActivityIndicator color={colors.primary} style={{ marginVertical: spacing.xl }} />
        )}

        {/* ── Stats card ── */}
        {!loading && profile && profile.wardrobe_size > 0 && (
          <View style={[styles.statsCard, {
            backgroundColor: colors.surfaceElevated,
            borderColor: colors.border,
            ...platformShadow(colors.primary),
          }]}>
            <View style={[styles.statsAccent, { backgroundColor: colors.primary }]} />
            <View style={styles.statsBody}>
              {/* Wardrobe size */}
              <View style={styles.statRow}>
                <Text style={styles.statIcon}>👗</Text>
                <View>
                  <Text style={[styles.statValue, { color: colors.text }]}>{profile.wardrobe_size}</Text>
                  <Text style={[styles.statDesc, { color: colors.textMuted }]}>items in your wardrobe</Text>
                </View>
              </View>

              {/* Category bars */}
              {Object.keys(profile.category_counts).length > 0 && (
                <View style={styles.bars}>
                  {Object.entries(profile.category_counts).map(([cat, count]) => (
                    <View key={cat} style={styles.barRow}>
                      <Text style={[styles.barLabel, { color: colors.textMuted }]}>
                        {cat.charAt(0).toUpperCase() + cat.slice(1)}
                      </Text>
                      <View style={[styles.barTrack, { backgroundColor: colors.border }]}>
                        <View style={[styles.barFill, {
                          backgroundColor: colors.primary,
                          width: `${(count / maxCategoryCount) * 100}%`,
                        }]} />
                      </View>
                      <Text style={[styles.barCount, { color: colors.textSubtle }]}>{count}</Text>
                    </View>
                  ))}
                </View>
              )}

              {/* Chips row */}
              <View style={styles.chips}>
                {profile.favorite_colors.slice(0, 3).map(c => (
                  <View key={c} style={[styles.chip, { backgroundColor: colors.pillBg }]}>
                    <Text style={[styles.chipText, { color: colors.pillText }]}>🎨 {c}</Text>
                  </View>
                ))}
                {profile.favorite_styles.slice(0, 2).map(s => (
                  <View key={s} style={[styles.chip, { backgroundColor: colors.pillBg }]}>
                    <Text style={[styles.chipText, { color: colors.pillText }]}>✦ {s}</Text>
                  </View>
                ))}
              </View>

              {profile.narrative && (
                <View style={[styles.narrativeBox, { backgroundColor: colors.surface, borderColor: colors.border }]}>
                  <Text style={[styles.narrativeText, { color: colors.text }]}>
                    "{profile.narrative}"
                  </Text>
                </View>
              )}
            </View>
          </View>
        )}

        {!loading && profile && profile.wardrobe_size === 0 && (
          <View style={[styles.emptyCard, { borderColor: colors.border }]}>
            <Text style={styles.emptyIcon}>🪡</Text>
            <Text style={[styles.emptyTitle, { color: colors.text }]}>Style profile is empty</Text>
            <Text style={[styles.emptySub, { color: colors.textMuted }]}>
              Add wardrobe items to unlock your personal style profile.
            </Text>
          </View>
        )}

        {/* ── Quick links ── */}
        <Text style={[styles.sectionTitle, { color: colors.text }]}>Quick access</Text>
        <View style={styles.qls}>
          <QuickLink icon="📅" label="Calendar"         onPress={onGoToCalendar} />
          <QuickLink icon="🧳" label="Packing list"     onPress={onGoToPacking} />
          <QuickLink icon="🪞" label="Virtual try-on"   onPress={onGoToTryOn} />
        </View>

        {/* ── Log out ── */}
        <Pressable
          onPress={logout}
          style={[styles.logoutBtn, { borderColor: colors.error }]}
        >
          <Text style={[styles.logoutText, { color: colors.error }]}>Log out</Text>
        </Pressable>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  root: { paddingBottom: 40 },

  hero: {
    height: 150,
    overflow: "hidden",
    position: "relative",
    paddingHorizontal: spacing.xl,
  },
  heroTint: { ...StyleSheet.absoluteFillObject, opacity: 0.27 },
  avatarWrapper: { position: "absolute", bottom: -44, alignSelf: "center", left: 0, right: 0, alignItems: "center" },
  avatarRing: {
    width: 90, height: 90, borderRadius: 45,
    borderWidth: 3, padding: 3,
  },
  avatarInner: {
    width: "100%", height: "100%", borderRadius: 42,
    overflow: "hidden", alignItems: "center", justifyContent: "center",
  },
  avatarImage:       { width: "100%", height: "100%" },
  avatarPlaceholder: { fontSize: 36 },
  heroCurve: {
    position: "absolute",
    bottom: -2, left: -20, right: -20,
    height: 40, borderTopLeftRadius: 40, borderTopRightRadius: 40,
  },
  logoZone: { alignItems: "center", paddingTop: 52, paddingBottom: 8 },

  content: { padding: spacing.xl, gap: spacing.lg },

  statsCard: {
    borderRadius: radius.lg,
    borderWidth: 1,
    overflow: "hidden",
    ...platformShadow("#17235B", { x: 0, y: 4, opacity: 0.10, radius: 12 }),
  },
  statsAccent: { height: 3 },
  statsBody:   { padding: spacing.lg, gap: spacing.md },
  statRow:     { flexDirection: "row", alignItems: "center", gap: spacing.md },
  statIcon:    { fontSize: 28 },
  statValue:   { fontSize: 26, fontWeight: "800" },
  statDesc:    { fontSize: 13 },

  bars:     { gap: 8 },
  barRow:   { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  barLabel: { width: 85, fontSize: 12, textTransform: "capitalize" },
  barTrack: { flex: 1, height: 8, borderRadius: 4, overflow: "hidden" },
  barFill:  { height: "100%", borderRadius: 4 },
  barCount: { width: 22, fontSize: 12, textAlign: "right" },

  chips:    { flexDirection: "row", flexWrap: "wrap", gap: 6, marginTop: 4 },
  chip:     { paddingHorizontal: 10, paddingVertical: 5, borderRadius: radius.pill },
  chipText: { fontSize: 12, fontWeight: "600" },

  narrativeBox: {
    padding: spacing.md,
    borderRadius: radius.md,
    borderWidth: 1,
    marginTop: 4,
  },
  narrativeText: { fontSize: 14, fontStyle: "italic", lineHeight: 20 },

  emptyCard: {
    padding: spacing.xxl,
    borderRadius: radius.lg,
    borderWidth: 1.5,
    borderStyle: "dashed",
    alignItems: "center",
    gap: 8,
  },
  emptyIcon:  { fontSize: 44 },
  emptyTitle: { fontSize: 17, fontWeight: "700" },
  emptySub:   { fontSize: 14, textAlign: "center", lineHeight: 20 },

  sectionTitle: { fontSize: 16, fontWeight: "700", marginBottom: -spacing.xs },

  qls: { gap: spacing.sm },
  ql: {
    flexDirection: "row",
    alignItems: "center",
    padding: spacing.lg,
    borderRadius: radius.lg,
    borderWidth: 1,
    gap: spacing.md,
    ...platformShadow("#17235B", { x: 0, y: 2, opacity: 0.06, radius: 6 }),
  },
  qlIcon:  { fontSize: 22 },
  qlLabel: { flex: 1, fontSize: 15, fontWeight: "600" },
  qlArrow: { fontSize: 22, fontWeight: "700" },

  logoutBtn: {
    marginTop: spacing.sm,
    paddingVertical: 14,
    borderRadius: radius.pill,
    borderWidth: 1.5,
    alignItems: "center",
  },
  logoutText: { fontWeight: "700", fontSize: 15 },
});
