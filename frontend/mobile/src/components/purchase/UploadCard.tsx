import { Ionicons } from "@expo/vector-icons";
import { ActivityIndicator, Image, Pressable, StyleSheet, Text, View } from "react-native";

import { useTheme } from "@/theme/ThemeContext";
import { radius, spacing } from "@/theme/tokens";
import { platformShadow } from "@/utils/platformStyles";

interface Props {
  imageUri: string | null;
  busy: boolean;
  status: string; // what's happening with the photo, shown next to it
  hint?: string;
  onPick: () => void;
}

/** Compact photo slot: an inviting call-to-action when empty, a thumbnail with its
 * status once a photo is chosen. */
export function UploadCard({ imageUri, busy, status, hint, onPick }: Props) {
  const { colors } = useTheme();

  if (!imageUri) {
    return (
      <Pressable
        onPress={onPick}
        style={[styles.card, styles.empty, { backgroundColor: colors.surfaceElevated, borderColor: colors.borderStrong },
          platformShadow(colors.primary, { y: 4, opacity: 0.12, radius: 12 })]}
      >
        <View style={[styles.cameraIcon, { backgroundColor: colors.primary }]}>
          <Ionicons name="camera" size={26} color="#FFFFFF" />
        </View>
        <View style={styles.text}>
          <Text style={[styles.title, { color: colors.text }]}>Analyse un article en 1 photo</Text>
          <Text style={[styles.hint, { color: colors.textMuted }]}>
            Seul ou porté : l'IA isole chaque vêtement
          </Text>
        </View>
        <Ionicons name="add-circle" size={30} color={colors.primary} />
      </Pressable>
    );
  }

  return (
    <View style={[styles.card, { backgroundColor: colors.surfaceElevated, borderColor: colors.border },
      platformShadow(colors.primary, { y: 2, opacity: 0.08, radius: 8 })]}>
      <View>
        <Image source={{ uri: imageUri }} style={styles.thumb} resizeMode="cover" />
        {busy && (
          <View style={styles.thumbOverlay}>
            <ActivityIndicator color="#FFFFFF" />
          </View>
        )}
      </View>
      <View style={styles.text}>
        <View style={styles.statusRow}>
          <Ionicons
            name={busy ? "sparkles" : "checkmark-circle"}
            size={15}
            color={busy ? colors.accent : colors.success}
          />
          <Text style={[styles.status, { color: colors.text }]}>{status}</Text>
        </View>
        {hint && <Text style={[styles.hint, { color: colors.textMuted }]}>{hint}</Text>}
        {!busy && (
          <Pressable onPress={onPick} hitSlop={6} style={styles.change}>
            <Ionicons name="refresh" size={14} color={colors.primary} />
            <Text style={[styles.changeText, { color: colors.primary }]}>Changer de photo</Text>
          </Pressable>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    padding: spacing.md,
    borderRadius: radius.lg,
    borderWidth: 1,
  },
  empty: { borderStyle: "dashed", borderWidth: 1.5, paddingVertical: spacing.lg },
  cameraIcon: { width: 52, height: 52, borderRadius: 26, alignItems: "center", justifyContent: "center" },
  text: { flex: 1, gap: 3 },
  title: { fontSize: 15, fontWeight: "900" },
  hint: { fontSize: 12, lineHeight: 16 },
  thumb: { width: 84, height: 84, borderRadius: radius.md, backgroundColor: "#FFFFFF" },
  thumbOverlay: {
    ...StyleSheet.absoluteFillObject,
    borderRadius: radius.md,
    backgroundColor: "rgba(26,10,20,0.5)",
    alignItems: "center",
    justifyContent: "center",
  },
  statusRow: { flexDirection: "row", alignItems: "center", gap: 6 },
  status: { fontSize: 14, fontWeight: "800", flexShrink: 1 },
  change: { flexDirection: "row", alignItems: "center", gap: 4, marginTop: 4 },
  changeText: { fontSize: 12, fontWeight: "800" },
});
