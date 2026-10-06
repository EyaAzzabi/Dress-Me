import { useState } from "react";
import { KeyboardAvoidingView, Platform, Pressable, StyleSheet, Text, View } from "react-native";

import { Button } from "@/components/Button";
import { ScreenSubtitle, ScreenTitle } from "@/components/Typography";
import { TextField } from "@/components/TextField";
import { useAuth } from "@/context/AuthContext";
import { useTheme } from "@/theme/ThemeContext";
import { spacing } from "@/theme/tokens";

export default function LoginScreen({ onGoToOnboarding }: { onGoToOnboarding: () => void }) {
  const { colors } = useTheme();
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit() {
    setError(null);
    setLoading(true);
    try {
      await login({ email, password });
    } catch {
      setError("Incorrect email or password");
    } finally {
      setLoading(false);
    }
  }

  return (
    <KeyboardAvoidingView
      style={[styles.container, { backgroundColor: colors.bg }]}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <View style={styles.header}>
        <ScreenTitle>DressMe</ScreenTitle>
        <ScreenSubtitle>Your wardrobe, intelligently styled.</ScreenSubtitle>
      </View>

      <View style={styles.form}>
        <TextField
          placeholder="Email"
          autoCapitalize="none"
          keyboardType="email-address"
          value={email}
          onChangeText={setEmail}
        />
        <TextField
          placeholder="Password"
          secureTextEntry
          value={password}
          onChangeText={setPassword}
        />
        {error && <Text style={[styles.error, { color: colors.error }]}>{error}</Text>}
        <Button title="Log in" onPress={handleSubmit} loading={loading} />
      </View>

      <Pressable onPress={onGoToOnboarding} style={styles.footer}>
        <Text style={{ color: colors.textMuted }}>
          New here? <Text style={{ color: colors.primary, fontWeight: "600" }}>Create an account</Text>
        </Text>
      </Pressable>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, justifyContent: "center", padding: spacing.xl },
  header: { alignItems: "center", marginBottom: spacing.xxl },
  form: { gap: spacing.md },
  error: { fontSize: 13 },
  footer: { marginTop: spacing.xxl, alignItems: "center" },
});
