/**
 * TunisianHeader — header premium thème tunisien rose.
 *
 * Structure :
 *  ┌─────────────────────────────────────────┐
 *  │  Photo de Sidi Bou Saïd + détails zellige│  ← overflow:hidden
 *  └────────────╮ courbe ╭───────────────────┘
 *               │  LOGO  │                      ← hors overflow
 *               └────────┘
 *  [  Titre  ]  [  Sous-titre  ]  [  Action  ]
 */
import { DressMeLogo } from "@/components/DressMeLogo";
import { useTheme } from "@/theme/ThemeContext";
import { radius, spacing } from "@/theme/tokens";
import { ReactNode } from "react";
import { ActivityIndicator, ImageBackground, Pressable, StyleSheet, Text, View } from "react-native";


import { platformShadow } from "@/utils/platformStyles";
const TUNISIAN_HERO = require("@/assets/tunisian-fashion-hero.jpg");

interface TunisianHeaderProps {
  /** Titre principal (blanc sur fond coloré) */
  title?: string;
  /** Sous-titre */
  subtitle?: string;
  /** Bouton d'action à droite */
  actionLabel?: string;
  onAction?: () => void;
  actionLoading?: boolean;
  /** Largeur du logo (défaut 190) */
  logoWidth?: number;
  /** Hauteur de la bande colorée (défaut 140) */
  bandHeight?: number;
  /** Contenu extra sous le logo */
  children?: ReactNode;
}

export function TunisianHeader({
  title,
  subtitle,
  actionLabel,
  onAction,
  actionLoading = false,
  logoWidth = 190,
  bandHeight = 140,
  children,
}: TunisianHeaderProps) {
  const { colors } = useTheme();

  return (
    <View style={styles.wrapper}>
      {/* ══ PHOTO TUNISIENNE ══ */}
      <ImageBackground
        source={TUNISIAN_HERO}
        resizeMode="cover"
        style={[styles.band, { height: bandHeight }]}
        imageStyle={styles.bandImage}
      >
        <View style={[styles.photoTint, { pointerEvents: "none" }]} />
        <Text style={[styles.zellige, styles.z1, { color: colors.tunisianGold }]}>✦</Text>
        <Text style={[styles.zellige, styles.z2, { color: colors.tunisianGold }]}>✦</Text>
        <Text style={[styles.zellige, styles.z3, { color: colors.tunisianGold }]}>✦</Text>
        <Text style={[styles.zellige, styles.z4, { color: colors.tunisianGold }]}>✦</Text>
        <View style={[styles.bandCurve, { backgroundColor: colors.bg }]} />
      </ImageBackground>

      {/* ══ LOGO (hors overflow) ══ */}
      <View style={styles.logoZone}>
        <DressMeLogo width={logoWidth} />
      </View>

      {/* ══ TITRE + ACTION ══ */}
      {(title || actionLabel) && (
        <View style={styles.titleRow}>
          <View style={styles.titleBlock}>
            {title && (
              <Text style={[styles.title, { color: colors.tunisianNavy }]}>{title}</Text>
            )}
            {subtitle && (
              <Text style={[styles.subtitle, { color: colors.textMuted }]}>{subtitle}</Text>
            )}
          </View>

          {actionLabel && onAction && (
            <Pressable
              onPress={onAction}
              disabled={actionLoading}
              style={[styles.actionBtn, {
                backgroundColor: colors.primary,
                ...platformShadow(colors.primary),
              }]}
            >
              {actionLoading
                ? <ActivityIndicator color="#FFF" size="small" />
                : <Text style={styles.actionText}>{actionLabel}</Text>
              }
            </Pressable>
          )}
        </View>
      )}

      {/* Ligne dorée séparatrice */}
      <View style={[styles.goldLine, { backgroundColor: colors.tunisianGold }]} />

      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  wrapper: {},

  /* ── Bande ── */
  band: {
    overflow: "hidden",
    position: "relative",
    width: "100%",
  },
  bandImage: {
    position: "absolute",
    top: 0,
    right: 0,
    bottom: 0,
    left: 0,
    width: "100%",
    height: "100%",
    transform: [{ scale: 1.08 }],
  },
  photoTint: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: "rgba(255, 230, 239, 0.12)",
  },

  /* Zellige arabesques */
  zellige: { position: "absolute", fontWeight: "900" },
  z1: { fontSize: 55, top: -6,  left: 6,   opacity: 0.18 },
  z2: { fontSize: 75, top: -8,  right: 8,  opacity: 0.13 },
  z3: { fontSize: 40, bottom: 28, left: "38%", opacity: 0.16 },
  z4: { fontSize: 30, top: 10,  right: "40%", opacity: 0.12 },

  /* Courbe bas */
  bandCurve: {
    position: "absolute",
    bottom: -2, left: -24, right: -24,
    height: 38,
    borderTopLeftRadius: 38,
    borderTopRightRadius: 38,
  },

  /* ── Logo ── */
  logoZone: {
    alignItems: "center",
    paddingTop: spacing.sm,
    paddingBottom: spacing.xs,
  },

  /* ── Titre ── */
  titleRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: spacing.xl,
    paddingTop: spacing.sm,
    paddingBottom: spacing.xs,
  },
  titleBlock: { flex: 1 },
  title:    { fontSize: 22, fontWeight: "800", letterSpacing: -0.4 },
  subtitle: { fontSize: 13, marginTop: 2 },

  actionBtn: {
    paddingHorizontal: 18,
    paddingVertical: 10,
    borderRadius: radius.pill,
    ...platformShadow("#17235B", { x: 0, y: 4, opacity: 0.28, radius: 8 }),
    marginLeft: spacing.md,
  },
  actionText: { color: "#FFFFFF", fontWeight: "700", fontSize: 14 },

  /* Ligne or séparatrice */
  goldLine: {
    height: 1.5,
    marginHorizontal: spacing.xl,
    marginTop: spacing.xs,
    opacity: 0.35,
    borderRadius: 1,
  },
});
