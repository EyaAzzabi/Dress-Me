import { Image, StyleSheet, View } from "react-native";

interface DressMeLogoProps {
  width?: number;
  light?: boolean;
  showTagline?: boolean;
}

const FULL_LOGO = require("@/assets/dressme-logo.png");
const LOGO_MARK = require("@/assets/dressme-logo-mark.png");

export function DressMeLogo({
  width = 200,
  light = false,
  showTagline = true,
}: DressMeLogoProps) {
  return (
    <View
      accessible
      accessibilityLabel="DressMe, a smarter wardrobe for a brighter you"
      style={[
        styles.root,
        {
          width,
          aspectRatio: showTagline ? 297 / 285 : 297 / 251,
          backgroundColor: light ? "rgba(255,248,250,0.92)" : "transparent",
          borderRadius: light ? 14 : 0,
        },
      ]}
    >
      <Image
        source={showTagline ? FULL_LOGO : LOGO_MARK}
        resizeMode="contain"
        style={styles.image}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    overflow: "hidden",
    alignItems: "center",
    justifyContent: "center",
  },
  image: {
    width: "100%",
    height: "100%",
  },
});
