/**
 * HeroHeader — curved pink hero section used at the top of main screens.
 * Creates the premium "fashion app" look with a soft gradient background,
 * decorative circles, and the DressMe logo.
 */
import { DressMeLogo } from "@/components/DressMeLogo";
import { useTheme } from "@/theme/ThemeContext";
import { StyleSheet, Text, View } from "react-native";

interface HeroHeaderProps {
  title?: string;
  subtitle?: string;
  showLogo?: boolean;
  compact?: boolean;
}

export function HeroHeader({ title, subtitle, showLogo = false, compact = false }: HeroHeaderProps) {
  const { colors, season } = useTheme();

  return (
    <View style={[
      styles.hero,
      compact ? styles.heroCompact : styles.heroFull,
      { backgroundColor: colors.gradientStart }
    ]}>
      {/* Decorative blurred circles for depth */}
      <View style={[styles.circle1, { backgroundColor: colors.primary }]} />
      <View style={[styles.circle2, { backgroundColor: colors.accent }]} />
      <View style={[styles.circle3, { backgroundColor: colors.gradientEnd }]} />

      {/* Bottom curve cutout */}
      <View style={[styles.curve, { backgroundColor: colors.bg }]} />

      {/* Content */}
      <View style={styles.heroContent}>
        {showLogo && <DressMeLogo width={128} light showTagline={false} />}
        {title && (
          <Text style={[styles.heroTitle, { color: "#FFFFFF" }]}>{title}</Text>
        )}
        {subtitle && (
          <Text style={[styles.heroSubtitle, { color: "rgba(255,255,255,0.8)" }]}>{subtitle}</Text>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  hero: {
    width: "100%",
    overflow: "hidden",
    position: "relative",
  },
  heroFull:    { minHeight: 200, paddingTop: 50, paddingBottom: 50 },
  heroCompact: { minHeight: 120, paddingTop: 20, paddingBottom: 40 },

  // Decorative background circles
  circle1: {
    position: "absolute",
    width: 200,
    height: 200,
    borderRadius: 100,
    top: -60,
    right: -50,
    opacity: 0.35,
  },
  circle2: {
    position: "absolute",
    width: 140,
    height: 140,
    borderRadius: 70,
    top: 20,
    left: -40,
    opacity: 0.25,
  },
  circle3: {
    position: "absolute",
    width: 100,
    height: 100,
    borderRadius: 50,
    bottom: 10,
    right: 20,
    opacity: 0.20,
  },

  // Curved bottom edge — a tall View with rounded top corners
  curve: {
    position: "absolute",
    bottom: -2,
    left: -20,
    right: -20,
    height: 40,
    borderTopLeftRadius: 40,
    borderTopRightRadius: 40,
  },

  heroContent: {
    alignItems: "center",
    justifyContent: "center",
    gap: 6,
    zIndex: 2,
  },
  heroTitle: {
    fontSize: 26,
    fontWeight: "800",
    letterSpacing: -0.3,
  },
  heroSubtitle: {
    fontSize: 14,
    fontWeight: "500",
  },
});
