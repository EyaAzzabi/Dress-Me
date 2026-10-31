import { useState } from "react";
import {
    KeyboardAvoidingView,
    Platform,
    Pressable,
    ScrollView,
    StyleSheet,
    Text,
    View,
} from "react-native";


import { platformShadow } from "@/utils/platformStyles";
import { PremiumCard } from "@/components/PremiumCard";
import { SeasonalBanner } from "@/components/SeasonalBanner";
import { TextField } from "@/components/TextField";
import { TunisianHeader } from "@/components/TunisianHeader";
import { useAuth } from "@/context/AuthContext";
import { useTheme } from "@/theme/ThemeContext";
import { radius, spacing } from "@/theme/tokens";

export default function LoginScreen({ onGoToOnboarding }: { onGoToOnboarding: () => void }) {
  const { colors } = useTheme();
  const { login }  = useAuth();

  const [email,    setEmail]    = useState("");
  const [password, setPassword] = useState("");
  const [error,    setError]    = useState<string | null>(null);
  const [loading,  setLoading]  = useState(false);

  async function handleSubmit() {
    setError(null);
    setLoading(true);
    try { await login({ email, password }); }
    catch { setError("Email ou mot de passe incorrect"); }
    finally { setLoading(false); }
  }

  return (
    <KeyboardAvoidingView
      style={[styles.root, { backgroundColor: colors.bg }]}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <SeasonalBanner />
      <ScrollView
        contentContainerStyle={styles.scroll}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        {/* ── Header tunisien avec logo ── */}
        <TunisianHeader bandHeight={185} logoWidth={210} />

        {/* ── Carte de connexion ── */}
        <View style={styles.cardWrap}>
          <PremiumCard variant="default" accent>
            {/* Titre */}
            <View style={styles.cardHead}>
              <Text style={[styles.hello, { color: colors.tunisianNavy }]}>Bon retour 👋</Text>
              <Text style={[styles.helloBadge, {
                backgroundColor: colors.surface,
                color: colors.primary,
              }]}>
                DressMe
              </Text>
            </View>
            <Text style={[styles.sub, { color: colors.textMuted }]}>
              Connecte-toi pour accéder à ta garde-robe
            </Text>

            {/* Champs */}
            <View style={styles.fields}>
              <View style={styles.fieldWrap}>
                <Text style={[styles.label, { color: colors.textMuted }]}>Email</Text>
                <TextField
                  placeholder="ton@email.com"
                  autoCapitalize="none"
                  keyboardType="email-address"
                  value={email}
                  onChangeText={setEmail}
                />
              </View>
              <View style={styles.fieldWrap}>
                <Text style={[styles.label, { color: colors.textMuted }]}>Mot de passe</Text>
                <TextField
                  placeholder="••••••••"
                  secureTextEntry
                  value={password}
                  onChangeText={setPassword}
                />
              </View>
            </View>

            {/* Erreur */}
            {error && (
              <View style={[styles.errorBox, {
                backgroundColor: colors.errorBg,
                borderColor: colors.error,
              }]}>
                <Text style={[styles.errorText, { color: colors.error }]}>⚠  {error}</Text>
              </View>
            )}

            {/* Bouton principal */}
            <Pressable
              onPress={handleSubmit}
              disabled={loading}
              style={[styles.loginBtn, {
                backgroundColor: loading ? colors.primaryLight : colors.primary,
                ...platformShadow(colors.primary),
              }]}
            >
              <Text style={styles.loginBtnText}>
                {loading ? "Connexion…" : "Se connecter  →"}
              </Text>
            </Pressable>
          </PremiumCard>
        </View>

        {/* Ornement tunisien entre les sections */}
        <View style={styles.ornRow}>
          <View style={[styles.ornLine, { backgroundColor: colors.border }]} />
          <Text style={[styles.ornGold, { color: colors.tunisianGold }]}>✦</Text>
          <View style={[styles.ornLine, { backgroundColor: colors.border }]} />
        </View>

        {/* Inscription */}
        <Pressable onPress={onGoToOnboarding} style={styles.signupRow}>
          <Text style={[styles.signupText, { color: colors.textMuted }]}>
            Nouveau sur DressMe ?
          </Text>
          <View style={[styles.signupBtn, {
            borderColor: colors.primary,
            backgroundColor: colors.bg,
          }]}>
            <Text style={[styles.signupBtnText, { color: colors.primary }]}>
              Créer un compte
            </Text>
          </View>
        </Pressable>

        {/* Pied de page décoratif */}
        <View style={styles.footer}>
          <Text style={[styles.footerText, { color: colors.tunisianGold }]}>
            ✦  ─────  ✦  ─────  ✦
          </Text>
          <Text style={[styles.footerTagline, { color: colors.textSubtle }]}>
            A SMARTER WARDROBE FOR A BRIGHTER YOU
          </Text>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  root:   { flex: 1 },
  scroll: { paddingBottom: 40 },

  cardWrap: { paddingHorizontal: spacing.xl, marginTop: spacing.sm },

  /* Card head */
  cardHead: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: 4,
  },
  hello: { fontSize: 22, fontWeight: "800", letterSpacing: -0.3 },
  helloBadge: {
    fontSize: 11,
    fontWeight: "800",
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: radius.pill,
    letterSpacing: 0.5,
  },
  sub: { fontSize: 14, marginBottom: spacing.lg },

  /* Champs */
  fields:   { gap: spacing.md, marginBottom: spacing.lg },
  fieldWrap:{ gap: 5 },
  label:    { fontSize: 12, fontWeight: "700", letterSpacing: 0.4, marginLeft: 2 },

  /* Erreur */
  errorBox: {
    padding: spacing.md,
    borderRadius: radius.md,
    borderWidth: 1,
    marginBottom: spacing.md,
  },
  errorText: { fontSize: 13, fontWeight: "600" },

  /* Bouton login */
  loginBtn: {
    paddingVertical: 16,
    borderRadius: radius.pill,
    alignItems: "center",
    ...platformShadow("#17235B", { x: 0, y: 6, opacity: 0.30, radius: 14 }),
  },
  loginBtnText: {
    color: "#FFFFFF",
    fontSize: 16,
    fontWeight: "800",
    letterSpacing: 0.3,
  },

  /* Ornement */
  ornRow: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: spacing.xxl,
    marginVertical: spacing.xl,
    gap: spacing.md,
  },
  ornLine: { flex: 1, height: 1 },
  ornGold: { fontSize: 16, fontWeight: "900" },

  /* Inscription */
  signupRow: {
    alignItems: "center",
    gap: spacing.sm,
    paddingHorizontal: spacing.xl,
  },
  signupText: { fontSize: 14 },
  signupBtn: {
    paddingVertical: 12,
    paddingHorizontal: 32,
    borderRadius: radius.pill,
    borderWidth: 2,
    width: "100%",
    alignItems: "center",
  },
  signupBtnText: { fontSize: 15, fontWeight: "700" },

  /* Footer */
  footer: {
    alignItems: "center",
    paddingTop: spacing.xxl,
    gap: 6,
  },
  footerText:    { fontSize: 13, letterSpacing: 3 },
  footerTagline: { fontSize: 9, fontWeight: "700", letterSpacing: 1.8 },
});
