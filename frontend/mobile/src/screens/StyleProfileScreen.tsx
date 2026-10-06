import { useFocusEffect } from "@react-navigation/native";
import { useCallback, useState } from "react";
import { ActivityIndicator, Image, ScrollView, StyleSheet, Text, View } from "react-native";

import { getMe } from "@/api/auth";
import { getStyleProfile, StyleProfile } from "@/api/styleProfile";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { ScreenTitle, SectionLabel } from "@/components/Typography";
import { useAuth } from "@/context/AuthContext";
import { useTheme } from "@/theme/ThemeContext";
import { radius, spacing } from "@/theme/tokens";

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
  const [profile, setProfile] = useState<StyleProfile | null>(null);
  const [avatarUrl, setAvatarUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

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
      return () => {
        active = false;
      };
    }, [])
  );

  const maxCategoryCount = profile
    ? Math.max(1, ...Object.values(profile.category_counts))
    : 1;

  return (
    <ScrollView style={{ backgroundColor: colors.bg }} contentContainerStyle={styles.container}>
      <ScreenTitle>Your profile</ScreenTitle>

      <View style={styles.avatarRow}>
        <View style={[styles.avatarCircle, { backgroundColor: colors.surface, borderColor: colors.border }]}>
          {avatarUrl ? (
            <Image source={{ uri: avatarUrl }} style={styles.avatarImage} />
          ) : (
            <Text style={{ color: colors.textSubtle, fontSize: 12 }}>No photo</Text>
          )}
        </View>
      </View>

      {loading && <ActivityIndicator color={colors.primary} style={styles.spinner} />}

      {!loading && profile && profile.wardrobe_size === 0 && (
        <Text style={[styles.placeholder, { color: colors.textMuted }]}>
          Add a few wardrobe items first — your style profile builds up from what's
          actually in your wardrobe.
        </Text>
      )}

      {!loading && profile && profile.wardrobe_size > 0 && (
        <Card style={styles.section}>
          <Text style={[styles.stat, { color: colors.text }]}>
            {profile.wardrobe_size} items in your wardrobe
          </Text>

          {Object.keys(profile.category_counts).length > 0 && (
            <View style={styles.bars}>
              {Object.entries(profile.category_counts).map(([category, count]) => (
                <View key={category} style={styles.barRow}>
                  <Text style={[styles.barLabel, { color: colors.textMuted }]}>{category}</Text>
                  <View style={[styles.barTrack, { backgroundColor: colors.border }]}>
                    <View
                      style={[
                        styles.barFill,
                        { backgroundColor: colors.primary, width: `${(count / maxCategoryCount) * 100}%` },
                      ]}
                    />
                  </View>
                  <Text style={[styles.barCount, { color: colors.textSubtle }]}>{count}</Text>
                </View>
              ))}
            </View>
          )}

          {profile.favorite_colors.length > 0 && (
            <Text style={[styles.stat, { color: colors.textMuted }]}>
              Favorite colors: {profile.favorite_colors.join(", ")}
            </Text>
          )}
          {profile.favorite_styles.length > 0 && (
            <Text style={[styles.stat, { color: colors.textMuted }]}>
              Favorite styles: {profile.favorite_styles.join(", ")}
            </Text>
          )}

          {profile.narrative && (
            <Text style={[styles.narrative, { color: colors.text }]}>{profile.narrative}</Text>
          )}
        </Card>
      )}

      <SectionLabel style={styles.quickLinksLabel}>Quick links</SectionLabel>
      <View style={styles.quickLinks}>
        <Button title="Calendar" variant="secondary" onPress={onGoToCalendar} style={styles.quickLink} />
        <Button title="Packing (la valise)" variant="secondary" onPress={onGoToPacking} style={styles.quickLink} />
        <Button title="Try on outfits" variant="secondary" onPress={onGoToTryOn} style={styles.quickLink} />
      </View>

      <Button title="Log out" variant="logout" onPress={logout} style={styles.logout} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { padding: spacing.xl, gap: spacing.md },
  avatarRow: { alignItems: "center", marginVertical: spacing.md },
  avatarCircle: {
    width: 96,
    height: 96,
    borderRadius: 48,
    borderWidth: 1,
    alignItems: "center",
    justifyContent: "center",
    overflow: "hidden",
  },
  avatarImage: { width: "100%", height: "100%" },
  spinner: { marginTop: spacing.xl },
  placeholder: {},
  section: { padding: spacing.lg, gap: spacing.sm },
  stat: { fontSize: 15 },
  bars: { gap: spacing.xs, marginVertical: spacing.xs },
  barRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  barLabel: { width: 90, fontSize: 12, textTransform: "capitalize" },
  barTrack: { flex: 1, height: 8, borderRadius: radius.pill, overflow: "hidden" },
  barFill: { height: "100%", borderRadius: radius.pill },
  barCount: { width: 24, fontSize: 12, textAlign: "right" },
  narrative: { fontSize: 15, fontStyle: "italic", marginTop: spacing.xs },
  quickLinksLabel: { marginTop: spacing.md },
  quickLinks: { gap: spacing.sm },
  quickLink: { width: "100%" },
  logout: { marginTop: spacing.lg },
});
