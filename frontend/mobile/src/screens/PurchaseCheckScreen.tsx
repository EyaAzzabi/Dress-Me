import * as ImagePicker from "expo-image-picker";
import { useState } from "react";
import { Button, Image, ScrollView, StyleSheet, Text } from "react-native";

import { checkPurchase, PurchaseCheckResult } from "@/api/recommendations";

const VERDICT_LABEL: Record<PurchaseCheckResult["verdict"], string> = {
  recommended: "Recommended purchase",
  think_twice: "Think twice",
  not_recommended: "Not recommended",
};

export default function PurchaseCheckScreen() {
  const [imageUri, setImageUri] = useState<string | null>(null);
  const [result, setResult] = useState<PurchaseCheckResult | null>(null);
  const [loading, setLoading] = useState(false);

  async function pickImage() {
    const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!permission.granted) return;

    const picked = await ImagePicker.launchImageLibraryAsync({ quality: 0.8 });
    if (picked.canceled) return;

    const uri = picked.assets[0].uri;
    setImageUri(uri);
    setResult(null);
    setLoading(true);
    try {
      // NOTE: assumes `uri` has already been uploaded and resolves to a reachable URL.
      // TODO: wire this to the storage upload endpoint before calling checkPurchase.
      const data = await checkPurchase(uri);
      setResult(data);
    } finally {
      setLoading(false);
    }
  }

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <Text style={styles.title}>Should I buy this?</Text>
      <Button title="Pick a photo" onPress={pickImage} />
      {imageUri && <Image source={{ uri: imageUri }} style={styles.preview} />}
      {loading && <Text>Analyzing…</Text>}
      {result && (
        <>
          <Text style={styles.verdict}>{VERDICT_LABEL[result.verdict]}</Text>
          <Text>{result.explanation}</Text>
        </>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { padding: 24, gap: 16 },
  title: { fontSize: 22, fontWeight: "600" },
  preview: { width: "100%", height: 240, borderRadius: 12, backgroundColor: "#eee" },
  verdict: { fontSize: 18, fontWeight: "700" },
});
