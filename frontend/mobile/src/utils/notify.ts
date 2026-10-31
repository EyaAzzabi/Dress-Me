import { Alert, Platform } from "react-native";

/**
 * react-native-web's Alert.alert is a total no-op (see its source), so a plain
 * Alert.alert() silently swallows errors when running on web — fall back to the
 * browser's own alert() there.
 */
export function notify(title: string, message: string) {
  if (Platform.OS === "web") {
    window.alert(`${title}\n\n${message}`);
  } else {
    Alert.alert(title, message);
  }
}
