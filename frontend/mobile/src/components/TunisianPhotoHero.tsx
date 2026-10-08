import { ImageBackground, StyleSheet, Text, View } from "react-native";

import { useTheme } from "@/theme/ThemeContext";
import { platformTextShadow } from "@/utils/platformStyles";

const TUNISIAN_HERO = require("@/assets/tunisian-fashion-hero.jpg");

interface TunisianPhotoHeroProps {
  icon: string;
  title: string;
  subtitle: string;
  image?: "style" | "wardrobe" | "medina";
}

const HERO_IMAGES = {
  style: require("@/assets/sidi-bou-style-inspiration.jpg"),
  wardrobe: require("@/assets/tunisian-wardrobe-inspiration.jpg"),
  medina: require("@/assets/sidi-bou-coast-inspiration.jpg"),
};

export function TunisianPhotoHero({
  icon,
  title,
  subtitle,
  image = "medina",
}: TunisianPhotoHeroProps) {
  const { colors } = useTheme();

  return (
    <ImageBackground
      source={HERO_IMAGES[image]}
      resizeMode="cover"
      style={[styles.hero, { backgroundColor: colors.tunisianNavy }]}
      imageStyle={styles.image}
    >
      <View style={[styles.tint, { backgroundColor: colors.tunisianNavy }]} />
      <View style={[styles.glow, { borderColor: colors.tunisianGold }]} />
      <View style={styles.content}>
        <Text style={[styles.kicker, { color: colors.tunisianGold }]}>
          TUNIS · SIDI BOU SAÏD
        </Text>
        <Text style={styles.icon}>{icon}</Text>
        <Text style={styles.title}>{title}</Text>
        <Text style={styles.subtitle}>{subtitle}</Text>
      </View>
      <View style={[styles.curve, { backgroundColor: colors.bg }]} />
    </ImageBackground>
  );
}

const styles = StyleSheet.create({
  hero: {
    height: 215,
    width: "100%",
    alignSelf: "stretch",
    justifyContent: "center",
    overflow: "hidden",
  },
  image: {
    position: "absolute",
    top: 0,
    right: 0,
    bottom: 0,
    left: 0,
    width: "100%",
    height: "100%",
    transform: [{ scale: 1.08 }],
  },
  tint: {
    ...StyleSheet.absoluteFillObject,
    opacity: 0.37,
  },
  glow: {
    position: "absolute",
    width: 210,
    height: 210,
    borderRadius: 105,
    borderWidth: 1,
    top: -88,
    right: -35,
    opacity: 0.42,
  },
  content: {
    alignItems: "center",
    paddingHorizontal: 18,
    paddingBottom: 16,
  },
  kicker: {
    marginBottom: 5,
    fontSize: 9,
    fontWeight: "800",
    letterSpacing: 2,
  },
  icon: {
    marginBottom: 2,
    fontSize: 29,
  },
  title: {
    color: "#FFFFFF",
    fontSize: 24,
    fontWeight: "800",
    letterSpacing: -0.35,
    ...platformTextShadow(),
  },
  subtitle: {
    marginTop: 5,
    color: "rgba(255,255,255,0.92)",
    fontSize: 12,
    fontWeight: "500",
    textAlign: "center",
  },
  curve: {
    position: "absolute",
    right: -24,
    bottom: -3,
    left: -24,
    height: 24,
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
  },
});
