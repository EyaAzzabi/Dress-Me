import * as ImagePicker from "expo-image-picker";
import { useState } from "react";
import {
    Image,
    KeyboardAvoidingView,
    Platform,
    Pressable,
    ScrollView,
    StyleSheet,
    Text,
    View,
} from "react-native";


import { platformShadow } from "@/utils/platformStyles";
import { setAvatar } from "@/api/tryon";
import { uploadPhoto } from "@/api/wardrobe";
import { Button } from "@/components/Button";
import { SeasonalBanner } from "@/components/SeasonalBanner";
import { TextField } from "@/components/TextField";
import { TunisianHeader } from "@/components/TunisianHeader";
import { useAuth } from "@/context/AuthContext";
import { useTheme } from "@/theme/ThemeContext";
import { radius, spacing } from "@/theme/tokens";

type Step = "signup" | "avatar";

// Step indicator pill
function StepDot({ active }: { active: boolean }) {
  const { colors } = useTheme();
  return (
    <View style={[
      styles.stepDot,
      { backgroundColor: active ? colors.primary : colors.border,
        transform: [{ scale: active ? 1.3 : 1 }] }
    ]} />
  );
}

export default function OnboardingScreen({ onBackToLogin }: { onBackToLogin: () => void }) {
  const { colors } = useTheme();
  const { register } = useAuth();
  const [step, setStep]         = useState<Step>("signup");
  const [fullName, setFullName] = useState("");
  const [email, setEmail]       = useState("");
  const [password, setPassword] = useState("");
  const [error, setError]       = useState<string | null>(null);
  const [loading, setLoading]   = useState(false);
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
      style={[styles.root, { backgroundColor: colors.bg }]}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <SeasonalBanner />
      <TunisianHeader bandHeight={120} logoWidth={190} />

      <ScrollView
        contentContainerStyle={styles.scrollBody}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        {/* Step indicator */}
        <View style={styles.steps}>
          <StepDot active={step === "signup"} />
          <View style={[styles.stepLine, { backgroundColor: step === "avatar" ? colors.primary : colors.border }]} />
          <StepDot active={step === "avatar"} />
        </View>

        {step === "signup" ? (
          <>
            {/* Card */}
            <View style={[styles.card, {
              backgroundColor: colors.surfaceElevated,
              borderColor: colors.border,
              ...platformShadow(colors.primary),
            }]}>
              <View style={[styles.cardAccent, { backgroundColor: colors.primary }]} />
              <View style={styles.cardBody}>
                <Text style={[styles.cardTitle, { color: colors.text }]}>Create your account</Text>
                <Text style={[styles.cardSub, { color: colors.textMuted }]}>
                  Let's build your smart wardrobe 🌸
                </Text>
                <View style={styles.fields}>
                  <TextField placeholder="Full name" value={fullName} onChangeText={setFullName} />
                  <TextField
                    placeholder="Email address"
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
                </View>
                {error && (
                  <View style={[styles.errorBox, { backgroundColor: colors.errorBg, borderColor: colors.error }]}>
                    <Text style={[styles.errorText, { color: colors.error }]}>⚠ {error}</Text>
                  </View>
                )}
                <Button title="Create account →" onPress={handleCreateAccount} loading={loading} />
              </View>
            </View>

            <Pressable onPress={onBackToLogin} style={styles.backRow}>
              <Text style={[styles.backText, { color: colors.textMuted }]}>
                Already have an account?{" "}
                <Text style={{ color: colors.primary, fontWeight: "700" }}>Log in</Text>
              </Text>
            </Pressable>
          </>
        ) : (
          <>
            <View style={[styles.card, {
              backgroundColor: colors.surfaceElevated,
              borderColor: colors.border,
              ...platformShadow(colors.primary),
            }]}>
              <View style={[styles.cardAccent, { backgroundColor: colors.accent }]} />
              <View style={styles.cardBody}>
                {/* Optional badge */}
                <View style={[styles.optionalBadge, { backgroundColor: colors.pillBg }]}>
                  <Text style={[styles.optionalText, { color: colors.pillText }]}>Optional step</Text>
                </View>
                <Text style={[styles.cardTitle, { color: colors.text }]}>Add your photo</Text>
                <Text style={[styles.cardSub, { color: colors.textMuted }]}>
                  Used for virtual try-on — you can skip this for now.
                </Text>

                <Pressable
                  onPress={handlePickAvatar}
                  style={[styles.avatarPicker, {
                    backgroundColor: colors.surface,
                    borderColor: avatarUri ? colors.primary : colors.border,
                  }]}
                >
                  {avatarUri ? (
                    <Image source={{ uri: avatarUri }} style={styles.avatarImage} />
                  ) : (
                    <View style={styles.avatarPlaceholder}>
                      <Text style={styles.avatarIcon}>🤳</Text>
                      <Text style={[styles.avatarHint, { color: colors.textMuted }]}>
                        Tap to choose a full-body photo
                      </Text>
                    </View>
                  )}
                </Pressable>

                {error && (
                  <View style={[styles.errorBox, { backgroundColor: colors.errorBg, borderColor: colors.error }]}>
                    <Text style={[styles.errorText, { color: colors.error }]}>⚠ {error}</Text>
                  </View>
                )}

                <Button
                  title={avatarUri ? "Finish & save photo →" : "Skip for now →"}
                  onPress={avatarUri ? handleFinishWithAvatar : onBackToLogin}
                  loading={loading}
                />
                {avatarUri && (
                  <Button title="Skip" variant="ghost" onPress={onBackToLogin} />
                )}
              </View>
            </View>
          </>
        )}
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },

  hero: {
    height: 130,
    overflow: "hidden",
    position: "relative",
  },
  blob1: { position: "absolute", width: 180, height: 180, borderRadius: 90, top: -50, right: -30, opacity: 0.35 },
  blob2: { position: "absolute", width: 120, height: 120, borderRadius: 60, bottom: 10, left: -20, opacity: 0.25 },
  pal:   { position: "absolute", fontSize: 28, bottom: 20, left: 14 },
  msq:   { position: "absolute", fontSize: 24, bottom: 18, right: 12 },
  fl1:   { position: "absolute", fontSize: 18, top: 12, left: "40%", opacity: 0.7 },
  arab:  { position: "absolute", fontSize: 50, color: "rgba(255,255,255,0.12)", top: -5, right: 40 },
  heroCurve: {
    position: "absolute",
    bottom: -2, left: -20, right: -20,
    height: 36,
    borderTopLeftRadius: 36,
    borderTopRightRadius: 36,
  },
  logoZone: { alignItems: "center", paddingVertical: 10 },

  scrollBody: { padding: spacing.xl, gap: spacing.md, paddingBottom: 40 },

  steps: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 0,
    marginBottom: spacing.md,
  },
  stepDot: { width: 10, height: 10, borderRadius: 5 },
  stepLine: { width: 60, height: 2, marginHorizontal: 6 },

  card: {
    borderRadius: radius.lg,
    borderWidth: 1,
    overflow: "hidden",
    ...platformShadow("#17235B", { x: 0, y: 6, opacity: 0.12, radius: 16 }),
  },
  cardAccent: { height: 4 },
  cardBody:   { padding: spacing.xl, gap: spacing.md },
  cardTitle:  { fontSize: 22, fontWeight: "800", letterSpacing: -0.3 },
  cardSub:    { fontSize: 14, marginTop: -8 },
  fields:     { gap: spacing.sm },

  errorBox:  { padding: spacing.md, borderRadius: radius.md, borderWidth: 1 },
  errorText: { fontSize: 13, fontWeight: "500" },

  backRow: { alignItems: "center", paddingVertical: spacing.lg },
  backText: { fontSize: 14 },

  optionalBadge: {
    alignSelf: "flex-start",
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: radius.pill,
    marginBottom: -4,
  },
  optionalText: { fontSize: 11, fontWeight: "700" },

  avatarPicker: {
    height: 220,
    borderRadius: radius.lg,
    borderWidth: 2,
    overflow: "hidden",
  },
  avatarImage: { width: "100%", height: "100%" },
  avatarPlaceholder: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
  },
  avatarIcon: { fontSize: 40 },
  avatarHint: { fontSize: 14 },
});
