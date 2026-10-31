import { Platform, TextStyle, ViewStyle } from "react-native";

interface ShadowOptions {
  x?: number;
  y?: number;
  opacity?: number;
  radius?: number;
}

type CrossPlatformViewStyle = ViewStyle & { boxShadow?: string };
type CrossPlatformTextStyle = TextStyle & { textShadow?: string };

function withOpacity(color: string, opacity: number): string {
  const hex = color.match(/^#([\da-f]{3}|[\da-f]{6})$/i)?.[1];
  if (!hex) return `rgba(23, 35, 91, ${opacity})`;

  const expanded = hex.length === 3
    ? hex.split("").map((digit) => digit + digit).join("")
    : hex;
  const red = parseInt(expanded.slice(0, 2), 16);
  const green = parseInt(expanded.slice(2, 4), 16);
  const blue = parseInt(expanded.slice(4, 6), 16);
  return `rgba(${red}, ${green}, ${blue}, ${opacity})`;
}

export function platformShadow(
  color: string,
  { x = 0, y = 4, opacity = 0.12, radius = 12 }: ShadowOptions = {},
): CrossPlatformViewStyle {
  const shadow = Platform.select<CrossPlatformViewStyle>({
    web: {
      boxShadow: `${x}px ${y}px ${radius}px ${withOpacity(color, opacity)}`,
    },
    default: {
      shadowColor: color,
      shadowOffset: { width: x, height: y },
      shadowOpacity: opacity,
      shadowRadius: radius,
      elevation: Math.max(1, Math.round(radius / 3)),
    },
  });
  return shadow ?? {};
}

export function platformTextShadow(): CrossPlatformTextStyle {
  return Platform.select<CrossPlatformTextStyle>({
    web: {
      textShadow: "0px 2px 8px rgba(24, 18, 55, 0.28)",
    },
    default: {
      textShadowColor: "rgba(24, 18, 55, 0.28)",
      textShadowOffset: { width: 0, height: 2 },
      textShadowRadius: 8,
    },
  }) ?? {};
}
