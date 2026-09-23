import { Button, StyleSheet, Text, View } from "react-native";

import { useAuth } from "@/context/AuthContext";

export default function StyleProfileScreen() {
  const { logout } = useAuth();

  return (
    <View style={styles.container}>
      <Text style={styles.title}>Your style profile</Text>
      <Text style={styles.placeholder}>
        Favorite styles, colors, and occasions will show up here once the Style Profile
        Agent has enough wardrobe and feedback data.
      </Text>
      <Button title="Log out" onPress={logout} />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, padding: 24, gap: 16 },
  title: { fontSize: 22, fontWeight: "600" },
  placeholder: { color: "#666" },
});
