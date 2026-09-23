import { useState } from "react";
import { Button, ScrollView, StyleSheet, Text } from "react-native";

import { recommendOutfits } from "@/api/recommendations";

export default function OutfitRecommendationsScreen() {
  const [result, setResult] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);

  async function handleGenerate() {
    setLoading(true);
    try {
      const data = await recommendOutfits({});
      setResult(data);
    } finally {
      setLoading(false);
    }
  }

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <Text style={styles.title}>Outfit recommendations</Text>
      <Button title={loading ? "Generating…" : "Suggest an outfit"} onPress={handleGenerate} disabled={loading} />
      {result != null && <Text style={styles.result}>{JSON.stringify(result, null, 2)}</Text>}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { padding: 24, gap: 16 },
  title: { fontSize: 22, fontWeight: "600" },
  result: { fontFamily: "monospace", marginTop: 16 },
});
