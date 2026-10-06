import * as ImagePicker from "expo-image-picker";
import { useState } from "react";
import { Image, KeyboardAvoidingView, Platform, Pressable, StyleSheet, Text, View } from "react-native";

import { uploadPhoto } from "@/api/wardrobe";
import { setAvatar } from "@/api/tryon";
import { Button } from "@/components/Button";
import { ScreenSubtitle, ScreenTitle, SectionLabel } from "@/components/Typography";
import { TextField } from "@/components/TextField";
import { useAuth } from "@/context/AuthContext";
import { useTheme } from "@/theme/ThemeContext";
import { radius, spacing } from "@/theme/tokens";

type Step = "signup" | "avatar";

export default function OnboardingScreen({ onBackToLogin }: { onBackToLogin: () => void }) {
  const { colors } = useTheme();
  const { register } = useAuth();
  const [step, setStep] = useState<Step>("signup");
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [avatarUri, setAvatarUri] = useState<string | null>(null);

  async function handleCreateAccount() {
    setError(null);
    setLoading(true);
    try {
      await register({ full_name: fullName, email, password });
      setStep("avatar");
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? "Couldn't create your account — try again.");
    } finally {
      setLoading(false);
    }
  }

  async function handlePickAvatar() {
    const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!permission.granted) return;
    const picked = await ImagePicker.launchImageLibraryAsync({ quality: 0.8 });
    if (picked.canceled) return;
    setAvatarUri(picked.assets[0].uri);
  }

  async function handleFinishWithAvatar() {
    if (!avatarUri) return;
    setLoading(true);
    setError(null);
    try {
      const imageUrl = await uploadPhoto(avatarUri);
      await setAvatar(imageUrl);
      onBackToLogin();
    } catch {
      setError("Couldn't save your photo — you can add it later from your profile.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <KeyboardAvoidingView
      style={[styles.container, { backgroundColor: colors.bg }]}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      {step === "signup" ? (
        <>
          <View style={styles.header}>
            <ScreenTitle>Create your account</ScreenTitle>
            <ScreenSubtitle>We'll learn your style from your real wardrobe.</ScreenSubtitle>
          </View>
          <View style={styles.form}>
            <TextField placeholder="Full name" value={fullName} onChangeText={setFullName} />
            <TextField
              placeholder="Email"
              autoCapitalize="none"
              keyboardType="email-address"
              value={email}
              onChangeText={setEmail}
            />
            <TextField placeholder="Password" secureTextEntry value={password} onChangeText={setPassword} />
            {error && <Text style={[styles.error, { color: colors.error }]}>{error}</Text>}
            <Button title="Create account" onPress={handleCreateAccount} loading={loading} />
          </View>
          <Pressable onPress={onBackToLogin} style={styles.footer}>
            <Text style={{ color: colors.textMuted }}>
              Already have an account? <Text style={{ color: colors.primary, fontWeight: "600" }}>Log in</Text>
            </Text>
          </Pressable>
        </>
      ) : (
        <>
          <View style={styles.header}>
            <SectionLabel>Optional</SectionLabel>
            <ScreenTitle>Add a photo of yourself</ScreenTitle>
            <ScreenSubtitle>Used to try outfits on virtually. You can skip this for now.</ScreenSubtitle>
          </View>

          <Pressable
            onPress={handlePickAvatar}
            style={[styles.avatarBox, { backgroundColor: colors.surface, borderColor: colors.border }]}
          >
            {avatarUri ? (
              <Image source={{ uri: avatarUri }} style={styles.avatarImage} />
            ) : (
              <Text style={{ color: colors.textSubtle }}>Tap to choose a full-body photo</Text>
            )}
          </Pressable>

          {error && <Text style={[styles.error, { color: colors.error }]}>{error}</Text>}

          <View style={styles.form}>
            <Button
              title="Finish"
              onPress={avatarUri ? handleFinishWithAvatar : onBackToLogin}
              loading={loading}
            />
            {avatarUri && <Button title="Skip" variant="ghost" onPress={onBackToLogin} />}
          </View>
        </>
      )}
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, justifyContent: "center", padding: spacing.xl },
  header: { alignItems: "center", marginBottom: spacing.xxl, gap: 4 },
  form: { gap: spacing.md, marginTop: spacing.xl },
  error: { fontSize: 13, textAlign: "center" },
  footer: { marginTop: spacing.xxl, alignItems: "center" },
  avatarBox: {
    height: 260,
    borderRadius: radius.lg,
    borderWidth: 1,
    alignItems: "center",
    justifyContent: "center",
    overflow: "hidden",
  },
  avatarImage: { width: "100%", height: "100%" },
});
