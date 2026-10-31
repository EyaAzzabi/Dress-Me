import { Ionicons } from "@expo/vector-icons";
import { ComponentProps, useState } from "react";
import { Image, Pressable, StyleSheet, Text, View } from "react-native";

import { formatTnd, PurchaseHistoryItem, Verdict, WishlistEntry } from "@/api/purchase";
import { useTheme } from "@/theme/ThemeContext";
import { radius, spacing } from "@/theme/tokens";
import { platformShadow } from "@/utils/platformStyles";

type IconName = ComponentProps<typeof Ionicons>["name"];
type Tab = "history" | "wishlist";

const CATEGORY_LABELS: Record<string, string> = {
  haut: "Haut", bas: "Bas", robe: "Robe", veste: "Veste",
  chaussures: "Chaussures", sac: "Sac", accessoire: "Accessoire",
};

const VERDICTS: Record<Verdict, { label: string; icon: IconName }> = {
  recommended: { label: "Recommandé", icon: "checkmark-circle" },
  think_twice: { label: "À réfléchir", icon: "help-circle" },
  not_recommended: { label: "Déconseillé", icon: "close-circle" },
};

function timeAgo(iso: string): string {
  const minutes = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  if (minutes < 1) return "à l'instant";
  if (minutes < 60) return `il y a ${minutes} min`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `il y a ${hours} h`;
  const days = Math.round(hours / 24);
  if (days < 7) return `il y a ${days} j`;
  return new Date(iso).toLocaleDateString("fr-FR", { day: "numeric", month: "short" });
}

interface Props {
  history: PurchaseHistoryItem[];
  activeHistoryId: string | null;
  onOpenHistory: (item: PurchaseHistoryItem) => void;
  onRemoveHistory: (item: PurchaseHistoryItem) => void;
  onClearHistory: () => void;
  wishlist: WishlistEntry[];
  onOpenWish: (item: WishlistEntry) => void;
  onRemoveWish: (item: WishlistEntry) => void;
}

/** The user's shopping dashboard: key figures, then past checks and saved products. */
export function ShoppingSpace(props: Props) {
  const { colors } = useTheme();
  const { history, wishlist } = props;
  const [tab, setTab] = useState<Tab>("history");

  const recommended = history.filter((h) => h.verdict === "recommended").length;
  const savings = wishlist.reduce((sum, w) => sum + (w.price_drop ?? 0), 0);

  const stats: { icon: IconName; value: string; label: string; tone: string }[] = [
    { icon: "scan-outline", value: String(history.length), label: "Analyses", tone: colors.primary },
    { icon: "checkmark-done", value: String(recommended), label: "Bons achats", tone: colors.success },
    { icon: "heart", value: String(wishlist.length), label: "Wishlist", tone: colors.accent },
    { icon: "trending-down", value: savings ? formatTnd(savings)! : "0", label: "Économies", tone: colors.tunisianNavy },
  ];

  return (
    <View style={styles.root}>
      <View style={styles.header}>
        <View style={[styles.headerIcon, { backgroundColor: colors.primary }]}>
          <Ionicons name="bag-handle" size={18} color="#FFFFFF" />
        </View>
        <View style={{ flex: 1 }}>
          <Text style={[styles.title, { color: colors.tunisianNavy }]}>Mon espace shopping</Text>
          <Text style={[styles.subtitle, { color: colors.tunisianNavy, opacity: 0.65 }]}>
            Tes analyses et tes coups de cœur, suivis en direct
          </Text>
        </View>
      </View>

      <View style={styles.stats}>
        {stats.map((s) => (
          <View key={s.label} style={[styles.stat, { backgroundColor: colors.surfaceElevated, borderColor: colors.border }]}>
            <Ionicons name={s.icon} size={18} color={s.tone} />
            <Text style={[styles.statValue, { color: colors.text }]} numberOfLines={1}>{s.value}</Text>
            <Text style={[styles.statLabel, { color: colors.textMuted }]}>{s.label}</Text>
          </View>
        ))}
      </View>

      <View style={[styles.tabs, { backgroundColor: colors.pillBg }]}>
        {([
          { key: "history", label: "Historique", icon: "time-outline", count: history.length },
          { key: "wishlist", label: "Wishlist", icon: "heart-outline", count: wishlist.length },
        ] as const).map((t) => {
          const active = tab === t.key;
          return (
            <Pressable
              key={t.key}
              onPress={() => setTab(t.key)}
              style={[styles.tab, active && { backgroundColor: colors.surfaceElevated },
                active && platformShadow(colors.primary, { y: 1, opacity: 0.1, radius: 4 })]}
            >
              <Ionicons name={t.icon} size={16} color={active ? colors.primary : colors.textMuted} />
              <Text style={[styles.tabText, { color: active ? colors.primary : colors.textMuted }]}>{t.label}</Text>
              <View style={[styles.count, { backgroundColor: active ? colors.primary : colors.border }]}>
                <Text style={styles.countText}>{t.count}</Text>
              </View>
            </Pressable>
          );
        })}
      </View>

      <View style={[styles.panel, { backgroundColor: colors.surfaceElevated, borderColor: colors.border }]}>
        {tab === "history"
          ? <HistoryList {...props} />
          : <WishList {...props} />}
      </View>
    </View>
  );
}

function HistoryList({ history, activeHistoryId, onOpenHistory, onRemoveHistory, onClearHistory }: Props) {
  const { colors } = useTheme();
  if (history.length === 0) {
    return <Empty icon="time-outline" title="Aucune analyse pour l'instant"
                  hint="Chaque article analysé est enregistré ici, pour le revoir en un geste." />;
  }
  const tones: Record<Verdict, string> = {
    recommended: colors.success, think_twice: colors.warning, not_recommended: colors.error,
  };

  return (
    <>
      {history.map((item, i) => {
        const verdict = VERDICTS[item.verdict];
        const active = item.id === activeHistoryId;
        return (
          <Pressable
            key={item.id}
            onPress={() => onOpenHistory(item)}
            style={[styles.row, i > 0 && { borderTopWidth: 1, borderTopColor: colors.border },
              active && { backgroundColor: colors.bgAlt }]}
          >
            <View>
              <Image source={{ uri: item.image_url }} style={styles.thumb} resizeMode="contain" />
              <View style={[styles.scoreBadge, { backgroundColor: tones[item.verdict] }]}>
                <Text style={styles.scoreText}>{item.score}</Text>
              </View>
            </View>
            <View style={styles.rowBody}>
              <Text style={[styles.rowTitle, { color: colors.text }]} numberOfLines={1}>
                {CATEGORY_LABELS[item.category] ?? item.category}{item.color ? ` · ${item.color}` : ""}
              </Text>
              <View style={styles.metaRow}>
                <Ionicons name={verdict.icon} size={13} color={tones[item.verdict]} />
                <Text style={[styles.meta, { color: tones[item.verdict], fontWeight: "800" }]}>{verdict.label}</Text>
              </View>
              <View style={styles.metaRow}>
                {item.price != null && (
                  <>
                    <Ionicons name="pricetag-outline" size={12} color={colors.textMuted} />
                    <Text style={[styles.meta, { color: colors.textMuted }]}>{formatTnd(item.price)}</Text>
                  </>
                )}
                <Ionicons name="time-outline" size={12} color={colors.textMuted} />
                <Text style={[styles.meta, { color: colors.textMuted }]}>{timeAgo(item.created_at)}</Text>
              </View>
            </View>
            <IconButton icon="trash-outline" onPress={() => onRemoveHistory(item)} color={colors.textMuted} />
            <Ionicons name="chevron-forward" size={18} color={colors.textSubtle} />
          </Pressable>
        );
      })}
      <Pressable onPress={onClearHistory} style={[styles.footer, { borderTopColor: colors.border }]}>
        <Ionicons name="trash-bin-outline" size={14} color={colors.error} />
        <Text style={[styles.footerText, { color: colors.error }]}>Effacer tout l'historique</Text>
      </Pressable>
    </>
  );
}

function WishList({ wishlist, onOpenWish, onRemoveWish }: Props) {
  const { colors } = useTheme();
  if (wishlist.length === 0) {
    return <Empty icon="heart-outline" title="Ta wishlist est vide"
                  hint="Touche ♡ sur une alternative : on suit son prix et on te prévient s'il baisse." />;
  }

  return (
    <>
      {wishlist.map((item, i) => (
        <Pressable
          key={item.item_key}
          onPress={() => onOpenWish(item)}
          style={[styles.row, i > 0 && { borderTopWidth: 1, borderTopColor: colors.border }]}
        >
          <Image source={{ uri: item.image_url ?? undefined }} style={styles.thumb} />
          <View style={styles.rowBody}>
            <Text style={[styles.rowTitle, { color: colors.text }]} numberOfLines={1}>{item.name}</Text>
            {item.brand && (
              <View style={styles.metaRow}>
                <Ionicons name="storefront-outline" size={12} color={colors.textMuted} />
                <Text style={[styles.meta, { color: colors.textMuted }]}>{item.brand}</Text>
              </View>
            )}
            <View style={styles.metaRow}>
              <Text style={[styles.price, { color: colors.primary }]}>
                {formatTnd(item.live_price ?? item.saved_price) ?? "Prix n.c."}
              </Text>
              {item.price_drop != null && (
                <>
                  <Text style={[styles.oldPrice, { color: colors.textMuted }]}>{formatTnd(item.saved_price)}</Text>
                  <View style={[styles.pill, { backgroundColor: colors.successBg }]}>
                    <Ionicons name="trending-down" size={11} color={colors.success} />
                    <Text style={[styles.pillText, { color: colors.success }]}>-{formatTnd(item.price_drop)}</Text>
                  </View>
                </>
              )}
              {item.available === false && (
                <View style={[styles.pill, { backgroundColor: colors.errorBg }]}>
                  <Ionicons name="alert-circle-outline" size={11} color={colors.error} />
                  <Text style={[styles.pillText, { color: colors.error }]}>Rupture</Text>
                </View>
              )}
            </View>
          </View>
          <IconButton icon="heart-dislike-outline" onPress={() => onRemoveWish(item)} color={colors.textMuted} />
          <View style={[styles.cartBtn, { backgroundColor: item.buyable ? colors.primary : colors.pillBg }]}>
            <Ionicons
              name={item.buyable ? "cart-outline" : "open-outline"}
              size={16}
              color={item.buyable ? "#FFFFFF" : colors.pillText}
            />
          </View>
        </Pressable>
      ))}
    </>
  );
}

function IconButton({ icon, onPress, color }: { icon: IconName; onPress: () => void; color: string }) {
  return (
    <Pressable onPress={onPress} hitSlop={8} style={styles.iconBtn}>
      <Ionicons name={icon} size={18} color={color} />
    </Pressable>
  );
}

function Empty({ icon, title, hint }: { icon: IconName; title: string; hint: string }) {
  const { colors } = useTheme();
  return (
    <View style={styles.empty}>
      <View style={[styles.emptyIcon, { backgroundColor: colors.pillBg }]}>
        <Ionicons name={icon} size={26} color={colors.primary} />
      </View>
      <Text style={[styles.emptyTitle, { color: colors.text }]}>{title}</Text>
      <Text style={[styles.emptyHint, { color: colors.textMuted }]}>{hint}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { gap: spacing.md },
  header: { flexDirection: "row", alignItems: "center", gap: spacing.md },
  headerIcon: { width: 36, height: 36, borderRadius: 18, alignItems: "center", justifyContent: "center" },
  title: { fontSize: 18, fontWeight: "900" },
  subtitle: { fontSize: 12 },

  stats: { flexDirection: "row", gap: spacing.sm },
  stat: { flex: 1, alignItems: "center", gap: 2, paddingVertical: spacing.md, borderRadius: radius.md, borderWidth: 1 },
  statValue: { fontSize: 16, fontWeight: "900" },
  statLabel: { fontSize: 10, fontWeight: "600" },

  tabs: { flexDirection: "row", padding: 4, borderRadius: radius.pill, gap: 4 },
  tab: {
    flex: 1, flexDirection: "row", alignItems: "center", justifyContent: "center",
    gap: 6, paddingVertical: 9, borderRadius: radius.pill,
  },
  tabText: { fontSize: 13, fontWeight: "800" },
  count: { minWidth: 20, height: 18, paddingHorizontal: 5, borderRadius: 9, alignItems: "center", justifyContent: "center" },
  countText: { color: "#FFFFFF", fontSize: 10, fontWeight: "900" },

  panel: { borderRadius: radius.lg, borderWidth: 1, overflow: "hidden" },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.md, padding: spacing.md },
  thumb: { width: 56, height: 56, borderRadius: radius.md, backgroundColor: "#FFFFFF" },
  scoreBadge: {
    position: "absolute", right: -6, bottom: -6,
    minWidth: 26, height: 20, paddingHorizontal: 4, borderRadius: 10,
    alignItems: "center", justifyContent: "center", borderWidth: 2, borderColor: "#FFFFFF",
  },
  scoreText: { color: "#FFFFFF", fontSize: 10, fontWeight: "900" },
  rowBody: { flex: 1, gap: 3 },
  rowTitle: { fontSize: 14, fontWeight: "800", textTransform: "capitalize" },
  metaRow: { flexDirection: "row", alignItems: "center", gap: 4, flexWrap: "wrap" },
  meta: { fontSize: 11, marginRight: 6 },
  price: { fontSize: 14, fontWeight: "900" },
  oldPrice: { fontSize: 11, textDecorationLine: "line-through" },
  pill: { flexDirection: "row", alignItems: "center", gap: 3, paddingHorizontal: 6, paddingVertical: 2, borderRadius: radius.pill },
  pillText: { fontSize: 10, fontWeight: "900" },
  iconBtn: { padding: 4 },
  cartBtn: { width: 34, height: 34, borderRadius: 17, alignItems: "center", justifyContent: "center" },

  footer: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, padding: spacing.md, borderTopWidth: 1 },
  footerText: { fontSize: 12, fontWeight: "800" },

  empty: { alignItems: "center", gap: spacing.sm, padding: spacing.xl },
  emptyIcon: { width: 56, height: 56, borderRadius: 28, alignItems: "center", justifyContent: "center" },
  emptyTitle: { fontSize: 15, fontWeight: "800" },
  emptyHint: { fontSize: 12, textAlign: "center", lineHeight: 17 },
});
