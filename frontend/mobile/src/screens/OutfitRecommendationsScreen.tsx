import AsyncStorage from "@react-native-async-storage/async-storage";
import { useCallback, useMemo, useState } from "react";
import {
    Alert,
    ActivityIndicator,
    Image,
    Platform,
    Pressable,
    ScrollView,
    StyleSheet,
    Text,
    TextInput,
    View,
} from "react-native";
import { isAxiosError } from "axios";
import { useFocusEffect } from "@react-navigation/native";


import { platformShadow } from "@/utils/platformStyles";
import { getPlannedOutfit, planOutfit } from "@/api/calendar";
import {
  feedbackOutfit,
  listOutfits,
  Outfit,
  OutfitFeedback,
  recommendOutfits,
  ReActStep,
} from "@/api/recommendations";
import { listWardrobeItems } from "@/api/wardrobe";
import { TunisianPhotoHero } from "@/components/TunisianPhotoHero";
import { useTheme } from "@/theme/ThemeContext";
import { radius, spacing } from "@/theme/tokens";
import { ClothingItem } from "@/types/models";

const OCCASIONS = [
  { label: "Quotidien", value: "quotidien" },
  { label: "Travail", value: "travail" },
  { label: "Sortie", value: "sortie" },
  { label: "Soirée", value: "soirée" },
  { label: "Événement", value: "événement" },
];

const CITIES = ["Tunis", "Sousse", "Sfax", "Djerba"];
const FAVORITE_OUTFITS_STORAGE_KEY = "dressme_favorite_outfits";

const CRITIC_LABELS = {
  meteo: "Météo",
  occasion: "Occasion",
  couleurs: "Harmonie des couleurs",
  completude: "Tenue complète",
  fraicheur: "Fraîcheur",
} as const;

function CollapsibleSection({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  const { colors } = useTheme();
  const [open, setOpen] = useState(false);
  return (
    <View style={styles.collapsible}>
      <Pressable
        onPress={() => setOpen((o) => !o)}
        accessibilityRole="button"
        style={styles.collapsibleHeader}
      >
        <Text style={[styles.collapsibleTitle, { color: colors.text }]}>
          {title}
        </Text>
        <Text style={[styles.collapsibleChevron, { color: colors.textMuted }]}>
          {open ? "▲" : "▼"}
        </Text>
      </Pressable>
      {open && <View style={styles.collapsibleBody}>{children}</View>}
    </View>
  );
}

function getErrorMessage(error: unknown): string {
  if (isAxiosError(error) && typeof error.response?.data?.detail === "string") {
    return error.response.data.detail;
  }
  return "Une erreur est survenue. Réessaie dans un instant.";
}

function formatLocalDate(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function isValidDate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const [year, month, day] = value.split("-").map(Number);
  const date = new Date(year, month - 1, day);
  return date.getFullYear() === year
    && date.getMonth() === month - 1
    && date.getDate() === day;
}

function parseFavoriteOutfitIds(raw: string | null): string[] {
  if (!raw) return [];
  const parsed: unknown = JSON.parse(raw);
  if (!Array.isArray(parsed) || !parsed.every((id) => typeof id === "string")) {
    throw new Error("Invalid saved looks");
  }
  return parsed;
}

function ScoreRing({ score }: { score: number }) {
  const { colors } = useTheme();
  const pct = Math.round(score * 100);
  const ringColor = pct >= 75 ? colors.primary : pct >= 50 ? colors.accent : colors.border;
  return (
    <View style={[styles.ring, { borderColor: ringColor }]}>
      <Text style={[styles.ringText, { color: ringColor }]}>{pct}%</Text>
      <Text style={[styles.ringLabel, { color: colors.textSubtle }]}>match</Text>
    </View>
  );
}

function OutfitCard({
  outfit,
  itemsById,
  isFavorite,
  onToggleFavorite,
  onSchedule,
  onFeedback,
  isScheduling,
  isSubmittingFeedback,
}: {
  outfit: Outfit;
  itemsById: Map<string, ClothingItem>;
  isFavorite: boolean;
  onToggleFavorite: () => void;
  onSchedule: () => void;
  onFeedback: (rating: OutfitFeedback | null) => void;
  isScheduling: boolean;
  isSubmittingFeedback: boolean;
}) {
  const { colors } = useTheme();
  const [expanded, setExpanded] = useState(false);
  const items = outfit.item_ids
    .map((id) => itemsById.get(id))
    .filter((item): item is ClothingItem => item !== undefined);

  return (
    <View
      style={[
        styles.card,
        {
          backgroundColor: colors.surfaceElevated,
          borderColor: isFavorite ? colors.primary : colors.border,
          ...platformShadow(colors.primary),
        },
      ]}
    >
      <View style={[styles.cardStripe, { backgroundColor: isFavorite ? colors.tunisianGold : colors.primary }]} />
      <Pressable
        onPress={() => setExpanded(e => !e)}
        accessibilityRole="button"
        accessibilityLabel={`Tenue ${outfit.occasion ?? "recommandée"}, ${items.length} pièces. Appuyer pour afficher les détails.`}
        style={styles.cardBody}
      >
        <View style={styles.cardTop}>
          <View style={styles.cardLeft}>
            {outfit.occasion && (
              <View style={[styles.occasionChip, { backgroundColor: colors.pillBg }]}>
                <Text style={[styles.occasionText, { color: colors.pillText }]}>
                  ✦ {outfit.occasion}
                </Text>
              </View>
            )}
            <Text style={[styles.piecesText, { color: colors.textMuted }]}>
              {outfit.item_ids.length} {outfit.item_ids.length === 1 ? "pièce" : "pièces"}
            </Text>
          </View>
          <Pressable
            onPress={onToggleFavorite}
            accessibilityRole="button"
            accessibilityLabel={isFavorite ? "Retirer des looks favoris" : "Enregistrer dans les looks favoris"}
            accessibilityState={{ selected: isFavorite }}
            hitSlop={8}
            style={[
              styles.favoriteButton,
              { backgroundColor: isFavorite ? colors.pillBg : colors.bgAlt },
            ]}
          >
            <Text style={[styles.favoriteIcon, { color: colors.primary }]}>
              {isFavorite ? "♥" : "♡"}
            </Text>
          </Pressable>
          {outfit.relevance_score != null && (
            <ScoreRing score={outfit.relevance_score} />
          )}
        </View>

        {items.length > 0 && (
          <View style={styles.piecesRow}>
            {items.map((item) => (
              <View key={item.id} style={styles.piece}>
                <Image source={{ uri: item.image_url }} style={styles.pieceImage} />
                <Text style={[styles.pieceLabel, { color: colors.textMuted }]} numberOfLines={1}>
                  {item.category ?? "Pièce"}
                </Text>
              </View>
            ))}
          </View>
        )}

        {expanded && outfit.explanation && (
          <View style={[styles.explanationBox, { backgroundColor: colors.surface, borderColor: colors.border }]}>
            <Text style={[styles.explanationText, { color: colors.text }]}>
              {outfit.explanation}
            </Text>
          </View>
        )}

        <Text style={[styles.expandHint, { color: colors.textSubtle }]}>
          {expanded ? "Réduire ↑" : "Voir le conseil de style ↓"}
        </Text>
      </Pressable>
      {outfit.react_trace && outfit.react_trace.length > 0 && (
        <CollapsibleSection title="🧠 Raisonnement de l'agent">
          {outfit.react_trace.map((step: ReActStep, i: number) => (
            <View key={i} style={styles.reactStep}>
              <Text style={[styles.reactThought, { color: colors.text }]}>
                💭 {step.thought}
              </Text>
              <Text style={[styles.reactAction, { color: colors.textMuted }]}>
                ⚙ {String((step.action as { tool?: string }).tool ?? "")}({JSON.stringify((step.action as { args?: unknown }).args)})
              </Text>
              <Text style={[styles.reactObservation, { color: colors.textSubtle }]}>
                👁 {JSON.stringify((step.observation as { result?: unknown }).result).slice(0, 120)}
              </Text>
            </View>
          ))}
        </CollapsibleSection>
      )}
      {outfit.critic_score && (
        <CollapsibleSection title="⚖️ Avis du Critic">
          <Text style={[styles.criticTotal, { color: colors.text }]}>
            Score : {outfit.critic_score.total}/25
            {outfit.critic_score.approved ? " ✅" : " ⚠️"}
          </Text>
          {(Object.entries(outfit.critic_score.scores) as Array<[keyof typeof CRITIC_LABELS, number]>).map(([key, value]) => (
            <View key={key} style={styles.criticRow}>
              <Text style={[styles.criticLabel, { color: colors.textMuted }]}>
                {CRITIC_LABELS[key]}
              </Text>
              <View style={[styles.criticBarBg, { backgroundColor: colors.border }]}>
                <View
                  style={[
                    styles.criticBarFill,
                    {
                      width: `${(value / 5) * 100}%` as `${number}%`,
                      backgroundColor:
                        value >= 4
                          ? colors.success
                          : value >= 3
                          ? colors.primary
                          : colors.error,
                    },
                  ]}
                />
              </View>
              <Text style={[styles.criticScore, { color: colors.text }]}>
                {value}/5
              </Text>
            </View>
          ))}
          {outfit.critic_feedback && (
            <Text style={[styles.criticFeedback, { color: colors.textMuted }]}>
              {outfit.critic_feedback}
            </Text>
          )}
          {outfit.critic_iterations !== undefined && (
            <Text style={[styles.criticIterations, { color: colors.textSubtle }]}>
              {outfit.critic_iterations} itération{outfit.critic_iterations !== 1 ? "s" : ""}
            </Text>
          )}
        </CollapsibleSection>
      )}
      {outfit.style_guidelines_used && outfit.style_guidelines_used.length > 0 && (
        <CollapsibleSection title="📚 Guidelines de style utilisées">
          {outfit.style_guidelines_used.map((rule: string, i: number) => (
            <Text key={i} style={[styles.guidelineText, { color: colors.textMuted }]}>
              • {rule}
            </Text>
          ))}
        </CollapsibleSection>
      )}
      <Pressable
        onPress={onSchedule}
        disabled={isScheduling}
        accessibilityRole="button"
        style={[
          styles.scheduleButton,
          {
            backgroundColor: colors.primary,
            opacity: isScheduling ? 0.72 : 1,
          },
        ]}
      >
        {isScheduling
          ? <ActivityIndicator size="small" color="#FFFFFF" />
          : <Text style={styles.scheduleButtonText}>📅  Planifier cette tenue</Text>}
      </Pressable>
      <View style={styles.feedbackActions}>
        {([
          ["like", "👍 J’aime"],
          ["dislike", "👎 Pas pour moi"],
          ["worn", "✓ Déjà portée"],
        ] as const).map(([rating, label]) => (
          <Pressable
            key={rating}
            onPress={() => onFeedback(outfit.feedback === rating ? null : rating)}
            disabled={isSubmittingFeedback}
            accessibilityRole="button"
            accessibilityState={{ selected: outfit.feedback === rating, disabled: isSubmittingFeedback }}
            style={[
              styles.feedbackButton,
              {
                borderColor: outfit.feedback === rating ? colors.primary : colors.border,
                backgroundColor: outfit.feedback === rating ? colors.pillBg : colors.surface,
                opacity: isSubmittingFeedback ? 0.6 : 1,
              },
            ]}
          >
            <Text style={[styles.feedbackButtonText, { color: colors.text }]}>
              {isSubmittingFeedback ? "…" : label}
            </Text>
          </Pressable>
        ))}
      </View>
    </View>
  );
}

export default function OutfitRecommendationsScreen() {
  const { colors, season } = useTheme();
  const [outfits, setOutfits] = useState<Outfit[]>([]);
  const [wardrobe, setWardrobe] = useState<ClothingItem[]>([]);
  const [favoriteOutfitIds, setFavoriteOutfitIds] = useState<string[]>([]);
  const [showFavorites, setShowFavorites] = useState(false);
  const [wardrobeLoading, setWardrobeLoading] = useState(true);
  const [loading, setLoading] = useState(false);
  const [loadingPhase, setLoadingPhase] = useState<"stylist" | "critic" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [occasion, setOccasion] = useState<string | null>(null);
  const [requestText, setRequestText] = useState("");
  const [city, setCity] = useState<string | null>(null);
  const [planDate, setPlanDate] = useState(() => formatLocalDate(new Date()));
  const [planningOutfitId, setPlanningOutfitId] = useState<string | null>(null);
  const [planMessage, setPlanMessage] = useState<string | null>(null);
  const [planMessageIsError, setPlanMessageIsError] = useState(false);
  const [feedbackOutfitId, setFeedbackOutfitId] = useState<string | null>(null);
  const [feedbackAlignment, setFeedbackAlignment] = useState<number | null>(null);

  useFocusEffect(
    useCallback(() => {
      let active = true;
      setWardrobeLoading(true);
      Promise.all([
        listWardrobeItems(),
        listOutfits(),
        AsyncStorage.getItem(FAVORITE_OUTFITS_STORAGE_KEY).then(parseFavoriteOutfitIds),
      ])
        .then(([items, savedOutfits, savedFavoriteIds]) => {
          if (active) setWardrobe(items);
          if (active) setOutfits(savedOutfits);
          if (active) setFavoriteOutfitIds(savedFavoriteIds);
        })
        .catch((err: unknown) => {
          if (active) setError(getErrorMessage(err));
        })
        .finally(() => {
          if (active) setWardrobeLoading(false);
        });
      return () => {
        active = false;
      };
    }, [])
  );

  const itemsById = useMemo(
    () => new Map(wardrobe.map((item) => [item.id, item])),
    [wardrobe]
  );

  const visibleOutfits = useMemo(
    () => showFavorites
      ? outfits.filter((outfit) => favoriteOutfitIds.includes(outfit.id))
      : outfits,
    [favoriteOutfitIds, outfits, showFavorites]
  );

  async function handleGenerate() {
    setLoading(true);
    setLoadingPhase(null);
    setError(null);
    const phaseTimer = setTimeout(() => setLoadingPhase("critic"), 1500);
    try {
      const data = await recommendOutfits({
        occasion: occasion ?? undefined,
        request_text: requestText.trim() || undefined,
        season: season.id,
        city: city ?? undefined,
      });
      setOutfits(data.outfits);
      setFeedbackAlignment(data.evaluation?.feedback_alignment_at_k ?? null);
    } catch (err: unknown) {
      setError(getErrorMessage(err));
    } finally {
      clearTimeout(phaseTimer);
      setLoading(false);
      setLoadingPhase(null);
    }
  }

  async function handleFeedback(outfitId: string, rating: OutfitFeedback | null) {
    setFeedbackOutfitId(outfitId);
    setError(null);
    try {
      const updated = await feedbackOutfit(outfitId, rating);
      setOutfits((current) => current.map((outfit) => outfit.id === updated.id ? updated : outfit));
    } catch (err: unknown) {
      setError(getErrorMessage(err));
    } finally {
      setFeedbackOutfitId(null);
    }
  }

  async function handlePlanOutfit(outfit: Outfit) {
    const normalizedDate = planDate.trim();
    if (!isValidDate(normalizedDate)) {
      setPlanMessage("Entre une date valide au format AAAA-MM-JJ.");
      setPlanMessageIsError(true);
      return;
    }

    setPlanningOutfitId(outfit.id);
    setPlanMessage(null);
    setPlanMessageIsError(false);
    try {
      let alreadyPlanned = false;
      try {
        await getPlannedOutfit(normalizedDate);
        alreadyPlanned = true;
      } catch (error: unknown) {
        if (!isAxiosError(error) || error.response?.status !== 404) {
          throw error;
        }
      }

      if (alreadyPlanned) {
        const confirmed = await confirmReplacePlannedOutfit(normalizedDate);
        if (!confirmed) return;
      }

      await planOutfit(normalizedDate, outfit.item_ids);
      setPlanMessage(`Tenue planifiée pour le ${normalizedDate}. Tu la retrouveras dans ton calendrier.`);
      setPlanMessageIsError(false);
    } catch (error: unknown) {
      setPlanMessage(getErrorMessage(error));
      setPlanMessageIsError(true);
    } finally {
      setPlanningOutfitId(null);
    }
  }

  async function toggleFavoriteOutfit(outfitId: string) {
    const nextIds = favoriteOutfitIds.includes(outfitId)
      ? favoriteOutfitIds.filter((id) => id !== outfitId)
      : [...favoriteOutfitIds, outfitId];
    try {
      await AsyncStorage.setItem(FAVORITE_OUTFITS_STORAGE_KEY, JSON.stringify(nextIds));
      setFavoriteOutfitIds(nextIds);
    } catch (error: unknown) {
      setError(getErrorMessage(error));
    }
  }

  return (
    <View style={[styles.root, { backgroundColor: colors.bg }]}>
      <TunisianPhotoHero
        icon="✧"
        title="Idées de tenues"
        subtitle="Des looks pensés pour ton style, tes envies et la météo"
        image="style"
      />

      <ScrollView
        style={styles.scroll}
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
      >
        <View style={[styles.contextCard, {
          backgroundColor: colors.surfaceElevated,
          borderColor: colors.border,
          ...platformShadow(colors.primary),
        }]}>
          <Text style={[styles.sectionTitle, { color: colors.text }]}>Pour quelle occasion ?</Text>
          <Text style={[styles.sectionHint, { color: colors.textMuted }]}>
            Choisis un contexte pour personnaliser tes looks.
          </Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chipRow}>
            {OCCASIONS.map((option) => {
              const selected = occasion === option.value;
              return (
                <Pressable
                  key={option.value}
                  onPress={() => setOccasion(selected ? null : option.value)}
                  accessibilityRole="button"
                  accessibilityState={{ selected }}
                  style={[
                    styles.choiceChip,
                    {
                      backgroundColor: selected ? colors.pillActiveBg : colors.pillBg,
                      borderColor: selected ? colors.primary : "transparent",
                    },
                  ]}
                >
                  <Text style={[
                    styles.choiceText,
                    { color: selected ? colors.pillActiveText : colors.pillText },
                  ]}>
                    {option.label}
                  </Text>
                </Pressable>
              );
            })}
          </ScrollView>
          <Text style={[styles.sectionTitle, styles.cityTitle, { color: colors.text }]}>
            Une envie précise ? <Text style={[styles.optional, { color: colors.textMuted }]}>· facultatif</Text>
          </Text>
          <TextInput
            value={requestText}
            onChangeText={setRequestText}
            placeholder="Ex. Je vais dîner au restaurant après le travail"
            placeholderTextColor={colors.textSubtle}
            maxLength={500}
            multiline
            accessibilityLabel="Décris la tenue que tu recherches"
            style={[
              styles.requestInput,
              { color: colors.text, backgroundColor: colors.inputBg, borderColor: colors.inputBorder },
            ]}
          />

          <Text style={[styles.sectionTitle, styles.cityTitle, { color: colors.text }]}>
            Météo locale <Text style={[styles.optional, { color: colors.textMuted }]}>· facultatif</Text>
          </Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chipRow}>
            {CITIES.map((cityOption) => {
              const selected = city === cityOption;
              return (
                <Pressable
                  key={cityOption}
                  onPress={() => setCity(selected ? null : cityOption)}
                  accessibilityRole="button"
                  accessibilityState={{ selected }}
                  style={[
                    styles.cityChip,
                    {
                      backgroundColor: selected ? colors.surface : "transparent",
                      borderColor: selected ? colors.primary : colors.border,
                    },
                  ]}
                >
                  <Text style={[
                    styles.choiceText,
                    { color: selected ? colors.primary : colors.textMuted },
                  ]}>
                    {cityOption}
                  </Text>
                </Pressable>
              );
            })}
          </ScrollView>
          <Text style={[styles.seasonNote, { color: colors.textSubtle }]}>
            ✦ Saison prise en compte : {season.label}
          </Text>
        </View>

        <Pressable
          onPress={handleGenerate}
          disabled={loading || wardrobeLoading || wardrobe.length === 0}
          style={[styles.generateBtn, {
            backgroundColor: colors.primary,
            ...platformShadow(colors.primary),
            opacity: loading || wardrobeLoading || wardrobe.length === 0 ? 0.65 : 1,
          }]}
        >
          {loading
            ? <ActivityIndicator color="#FFFFFF" />
            : null}
          {loading && loadingPhase === null
            ? <Text style={styles.generateText}>Le Stylist réfléchit...</Text>
            : null}
          {loading && loadingPhase === "critic"
            ? <Text style={styles.generateText}>Le Critic évalue...</Text>
            : null}
          {!loading
            ? <>
                <Text style={styles.generateIcon}>🪄</Text>
                <Text style={styles.generateText}>
                  {wardrobeLoading ? "Chargement du dressing…" : "Créer mes idées de looks"}
                </Text>
              </>
            : null}
        </Pressable>

        {error && (
          <View style={[styles.errorBox, { backgroundColor: colors.errorBg, borderColor: colors.error }]}>
            <Text style={[styles.errorText, { color: colors.error }]}>⚠ {error}</Text>
          </View>
        )}

        {feedbackAlignment !== null && (
          <Text style={[styles.evaluationNote, { color: colors.textMuted }]}>
            Alignement avec tes retours précédents : {feedbackAlignment >= 0 ? "+" : ""}
            {feedbackAlignment.toFixed(2)}
          </Text>
        )}

        {!wardrobeLoading && wardrobe.length === 0 && !error && (
          <View style={[styles.empty, { borderColor: colors.border }]}>
            <Text style={styles.emptyIcon}>👗</Text>
            <Text style={[styles.emptyTitle, { color: colors.text }]}>Ton dressing attend ses premières pièces</Text>
            <Text style={[styles.emptySub, { color: colors.textMuted }]}>
              Ajoute quelques vêtements pour recevoir des associations adaptées à ton style.
            </Text>
          </View>
        )}

        {!loading && !wardrobeLoading && wardrobe.length > 0 && outfits.length === 0 && !error && (
          <View style={[styles.empty, { borderColor: colors.border }]}>
            <Text style={styles.emptyIcon}>✨</Text>
            <Text style={[styles.emptyTitle, { color: colors.text }]}>À toi le premier look</Text>
            <Text style={[styles.emptySub, { color: colors.textMuted }]}>
              Choisis une occasion et DressMe compose des tenues à partir de ton dressing.
            </Text>
          </View>
        )}

        {outfits.length > 0 && (
          <>
            <View style={styles.studioHeading}>
              <View style={styles.studioCopy}>
                <Text style={[styles.studioEyebrow, { color: colors.primary }]}>TON STUDIO DE STYLE</Text>
                <Text style={[styles.studioTitle, { color: colors.text }]}>Des looks à garder ✨</Text>
              </View>
              <View style={[styles.lookCount, { backgroundColor: colors.surface, borderColor: colors.border }]}>
                <Text style={[styles.lookCountNumber, { color: colors.primary }]}>{outfits.length}</Text>
                <Text style={[styles.lookCountLabel, { color: colors.textMuted }]}>
                  {outfits.length === 1 ? "look" : "looks"}
                </Text>
              </View>
            </View>
            <View style={[styles.statsStrip, { backgroundColor: colors.surfaceElevated, borderColor: colors.border }]}>
              <View style={styles.statBlock}>
                <Text style={styles.statIcon}>👗</Text>
                <Text style={[styles.statValue, { color: colors.text }]}>{wardrobe.length}</Text>
                <Text style={[styles.statLabel, { color: colors.textMuted }]}>pièces</Text>
              </View>
              <View style={[styles.statDivider, { backgroundColor: colors.border }]} />
              <View style={styles.statBlock}>
                <Text style={styles.statIcon}>♥</Text>
                <Text style={[styles.statValue, { color: colors.text }]}>{favoriteOutfitIds.length}</Text>
                <Text style={[styles.statLabel, { color: colors.textMuted }]}>favoris</Text>
              </View>
              <View style={[styles.statDivider, { backgroundColor: colors.border }]} />
              <View style={styles.statBlock}>
                <Text style={styles.statIcon}>☀</Text>
                <Text style={[styles.statValue, { color: colors.text }]} numberOfLines={1}>{season.label}</Text>
                <Text style={[styles.statLabel, { color: colors.textMuted }]}>saison</Text>
              </View>
            </View>

            <View
              style={[styles.segmentedControl, { backgroundColor: colors.surface, borderColor: colors.border }]}
              accessibilityRole="tablist"
            >
              <Pressable
                onPress={() => setShowFavorites(false)}
                accessibilityRole="tab"
                accessibilityState={{ selected: !showFavorites }}
                style={[
                  styles.segment,
                  !showFavorites && { backgroundColor: colors.surfaceElevated, ...platformShadow(colors.primary) },
                ]}
              >
                <Text style={[styles.segmentText, { color: !showFavorites ? colors.primary : colors.textMuted }]}>
                  ✨  Tous les looks
                </Text>
              </Pressable>
              <Pressable
                onPress={() => setShowFavorites(true)}
                accessibilityRole="tab"
                accessibilityState={{ selected: showFavorites }}
                style={[
                  styles.segment,
                  showFavorites && { backgroundColor: colors.surfaceElevated, ...platformShadow(colors.primary) },
                ]}
              >
                <Text style={[styles.segmentText, { color: showFavorites ? colors.primary : colors.textMuted }]}>
                  ♥  Favoris {favoriteOutfitIds.length > 0 ? `· ${favoriteOutfitIds.length}` : ""}
                </Text>
              </Pressable>
            </View>

            {showFavorites && visibleOutfits.length === 0 && (
              <View style={[styles.favoritesEmpty, { backgroundColor: colors.surfaceElevated, borderColor: colors.border }]}>
                <Text style={styles.favoritesEmptyIcon}>♡</Text>
                <Text style={[styles.emptyTitle, { color: colors.text }]}>Tes looks préférés seront ici</Text>
                <Text style={[styles.emptySub, { color: colors.textMuted }]}>
                  Appuie sur le cœur d’un look pour le retrouver facilement.
                </Text>
              </View>
            )}
          </>
        )}

        {visibleOutfits.length > 0 && (
          <View style={[
            styles.planDateCard,
            { backgroundColor: colors.surfaceElevated, borderColor: colors.border },
          ]}>
            <View style={styles.planDateCopy}>
              <Text style={[styles.planDateTitle, { color: colors.text }]}>Garde un look pour plus tard</Text>
              <Text style={[styles.planDateHint, { color: colors.textMuted }]}>
                Choisis une date, puis planifie la tenue qui te plaît.
              </Text>
            </View>
            <View style={[
              styles.dateInputWrap,
              { backgroundColor: colors.inputBg, borderColor: colors.inputBorder },
            ]}>
              <Text style={styles.dateIcon}>📅</Text>
              <TextInput
                value={planDate}
                onChangeText={(value) => {
                  setPlanDate(value);
                  setPlanMessage(null);
                  setPlanMessageIsError(false);
                }}
                placeholder="AAAA-MM-JJ"
                placeholderTextColor={colors.textSubtle}
                keyboardType="numbers-and-punctuation"
                maxLength={10}
                accessibilityLabel="Date de planification au format année-mois-jour"
                style={[styles.dateInput, { color: colors.text }]}
              />
            </View>
            {planMessage && (
              <Text style={[
                styles.planMessage,
                { color: planMessageIsError ? colors.error : colors.success },
              ]}>
                {planMessage}
              </Text>
            )}
          </View>
        )}

        {visibleOutfits.map((outfit) => (
          <OutfitCard
            key={outfit.id}
            outfit={outfit}
            itemsById={itemsById}
            isFavorite={favoriteOutfitIds.includes(outfit.id)}
            onToggleFavorite={() => void toggleFavoriteOutfit(outfit.id)}
            onSchedule={() => void handlePlanOutfit(outfit)}
            onFeedback={(rating) => void handleFeedback(outfit.id, rating)}
            isScheduling={planningOutfitId === outfit.id}
            isSubmittingFeedback={feedbackOutfitId === outfit.id}
          />
        ))}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },

  hero: {
    paddingTop: 50,
    paddingBottom: 40,
    overflow: "hidden",
    position: "relative",
  },
  blob1: {
    position: "absolute",
    width: 180,
    height: 180,
    borderRadius: 90,
    top: -50,
    right: -30,
    opacity: 0.35,
  },
  blob2: {
    position: "absolute",
    width: 120,
    height: 120,
    borderRadius: 60,
    bottom: 10,
    left: -20,
    opacity: 0.25,
  },
  heroContent: { alignItems: "center", gap: 4, zIndex: 2 },
  heroEmoji:   { fontSize: 40 },
  heroTitle:   { fontSize: 28, fontWeight: "800", color: "#FFFFFF", letterSpacing: -0.4 },
  heroSub:     { fontSize: 13, color: "rgba(255,255,255,0.8)" },
  heroCurve: {
    position: "absolute",
    bottom: -2,
    left: -20,
    right: -20,
    height: 36,
    borderTopLeftRadius: 36,
    borderTopRightRadius: 36,
  },

  scroll:        { flex: 1 },
  scrollContent: { paddingHorizontal: spacing.xl, paddingTop: spacing.md, gap: spacing.md, paddingBottom: 40 },

  contextCard: {
    padding: spacing.lg,
    borderRadius: radius.lg,
    borderWidth: 1,
    gap: spacing.sm,
  },
  sectionTitle: { fontSize: 16, fontWeight: "800" },
  sectionHint: { fontSize: 12, lineHeight: 18 },
  requestInput: {
    minHeight: 76,
    borderWidth: 1,
    borderRadius: radius.md,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    fontSize: 13,
    textAlignVertical: "top",
  },
  chipRow: { gap: spacing.sm, paddingVertical: 4 },
  choiceChip: {
    paddingHorizontal: 15,
    paddingVertical: 10,
    borderRadius: radius.pill,
    borderWidth: 1,
  },
  choiceText: { fontSize: 12, fontWeight: "700" },
  cityTitle: { marginTop: spacing.sm },
  optional: { fontSize: 11, fontWeight: "500" },
  cityChip: {
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: radius.pill,
    borderWidth: 1,
  },
  seasonNote: { fontSize: 11, fontWeight: "600", marginTop: spacing.xs },

  generateBtn: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: spacing.sm,
    paddingVertical: 16,
    borderRadius: radius.pill,
    ...platformShadow("#17235B", { x: 0, y: 6, opacity: 0.3, radius: 12 }),
  },
  generateIcon: { fontSize: 20 },
  generateText: { color: "#FFFFFF", fontSize: 15, fontWeight: "700" },

  errorBox: { padding: spacing.md, borderRadius: radius.md, borderWidth: 1 },
  errorText: { fontSize: 13, fontWeight: "500" },
  evaluationNote: { fontSize: 12, textAlign: "center", fontWeight: "600" },

  empty: {
    padding: spacing.xxl,
    borderRadius: radius.lg,
    borderWidth: 1.5,
    borderStyle: "dashed",
    alignItems: "center",
    gap: 8,
    marginTop: spacing.lg,
  },
  emptyIcon:  { fontSize: 44 },
  emptyTitle: { fontSize: 18, fontWeight: "700" },
  emptySub:   { fontSize: 14, textAlign: "center", lineHeight: 20 },

  studioHeading: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginTop: spacing.sm,
  },
  studioCopy: { gap: 3 },
  studioEyebrow: { fontSize: 9, fontWeight: "900", letterSpacing: 1.5 },
  studioTitle: { fontSize: 21, fontWeight: "900", letterSpacing: -0.5 },
  lookCount: {
    minWidth: 56,
    minHeight: 50,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1,
    borderRadius: radius.md,
    paddingHorizontal: spacing.sm,
  },
  lookCountNumber: { fontSize: 18, fontWeight: "900" },
  lookCountLabel: { fontSize: 9, fontWeight: "700" },
  statsStrip: {
    minHeight: 82,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-around",
    borderWidth: 1,
    borderRadius: radius.lg,
    paddingVertical: spacing.sm,
  },
  statBlock: { flex: 1, alignItems: "center", gap: 2 },
  statIcon: { fontSize: 13 },
  statValue: { maxWidth: "95%", fontSize: 13, fontWeight: "900", textTransform: "capitalize" },
  statLabel: { fontSize: 9, fontWeight: "600" },
  statDivider: { width: 1, height: 38 },
  segmentedControl: {
    minHeight: 49,
    flexDirection: "row",
    padding: 4,
    borderWidth: 1,
    borderRadius: radius.pill,
  },
  segment: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: radius.pill,
    paddingHorizontal: 8,
  },
  segmentText: { fontSize: 11, fontWeight: "800" },
  favoritesEmpty: {
    alignItems: "center",
    gap: spacing.sm,
    padding: spacing.xxl,
    borderWidth: 1,
    borderRadius: radius.lg,
  },
  favoritesEmptyIcon: { color: "#C9984A", fontSize: 42 },
  piecesRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, marginTop: spacing.xs },
  piece: { width: 76, alignItems: "center", gap: 5 },
  pieceImage: { width: 76, height: 88, borderRadius: radius.sm, backgroundColor: "#F3E8EC" },
  pieceLabel: { fontSize: 10, textAlign: "center", textTransform: "capitalize" },
  planDateCard: {
    padding: spacing.lg,
    borderRadius: radius.lg,
    borderWidth: 1,
    gap: spacing.md,
  },
  planDateCopy: { gap: 4 },
  planDateTitle: { fontSize: 15, fontWeight: "800" },
  planDateHint: { fontSize: 12, lineHeight: 18 },
  dateInputWrap: {
    minHeight: 46,
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    paddingHorizontal: spacing.md,
    borderWidth: 1,
    borderRadius: radius.md,
  },
  dateIcon: { fontSize: 16 },
  dateInput: { flex: 1, minHeight: 44, fontSize: 14, fontWeight: "700" },
  planMessage: { fontSize: 12, lineHeight: 18, fontWeight: "600" },

  // ── Outfit card ──
  card: {
    borderRadius: radius.lg,
    borderWidth: 1,
    overflow: "hidden",
    ...platformShadow("#17235B", { x: 0, y: 3, opacity: 0.08, radius: 10 }),
  },
  cardStripe: { height: 3 },
  cardBody:   { padding: spacing.lg, gap: spacing.sm },
  scheduleButton: {
    minHeight: 44,
    marginHorizontal: spacing.lg,
    marginBottom: spacing.md,
    paddingHorizontal: spacing.md,
    borderRadius: radius.pill,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
  },
  scheduleButtonText: { color: "#FFFFFF", fontSize: 13, fontWeight: "800" },
  feedbackActions: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: spacing.sm,
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.md,
  },
  feedbackButton: {
    minHeight: 36,
    justifyContent: "center",
    paddingHorizontal: spacing.sm,
    borderWidth: 1,
    borderRadius: radius.pill,
  },
  feedbackButtonText: { fontSize: 11, fontWeight: "700" },
  cardTop: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  cardLeft: { gap: 6, flex: 1 },
  favoriteButton: {
    width: 40,
    height: 40,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 20,
  },
  favoriteIcon: { fontSize: 22, fontWeight: "800" },
  occasionChip: {
    alignSelf: "flex-start",
    paddingHorizontal: 12,
    paddingVertical: 5,
    borderRadius: radius.pill,
  },
  occasionText: { fontSize: 12, fontWeight: "600" },
  piecesText:   { fontSize: 13 },

  ring: {
    width: 60,
    height: 60,
    borderRadius: 30,
    borderWidth: 3,
    alignItems: "center",
    justifyContent: "center",
  },
  ringText:  { fontSize: 14, fontWeight: "800" },
  ringLabel: { fontSize: 9, fontWeight: "600" },

  explanationBox: {
    padding: spacing.md,
    borderRadius: radius.md,
    borderWidth: 1,
    marginTop: spacing.xs,
  },
  explanationText: { fontSize: 14, lineHeight: 20 },
  expandHint: { fontSize: 11, textAlign: "right", marginTop: 2 },

  // ── Collapsible sections ──
  collapsible: { marginHorizontal: spacing.lg, marginBottom: spacing.sm },
  collapsibleHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingVertical: spacing.sm,
  },
  collapsibleTitle: { fontSize: 13, fontWeight: "700", flex: 1 },
  collapsibleChevron: { fontSize: 11, marginLeft: spacing.sm },
  collapsibleBody: { paddingBottom: spacing.sm, gap: spacing.xs },

  // ReAct trace
  reactStep: { gap: 2, marginBottom: spacing.xs },
  reactThought: { fontSize: 12, fontWeight: "600", lineHeight: 18 },
  reactAction: { fontSize: 11, lineHeight: 16, fontFamily: "monospace" },
  reactObservation: { fontSize: 11, lineHeight: 16 },

  // Critic
  criticTotal: { fontSize: 14, fontWeight: "800", marginBottom: spacing.xs },
  criticRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    marginBottom: 4,
  },
  criticLabel: { fontSize: 11, fontWeight: "600", width: 120 },
  criticBarBg: {
    flex: 1,
    height: 6,
    borderRadius: 3,
    overflow: "hidden",
  },
  criticBarFill: { height: "100%", borderRadius: 3 },
  criticScore: { fontSize: 11, fontWeight: "700", width: 28, textAlign: "right" },
  criticFeedback: { fontSize: 12, lineHeight: 18, marginTop: spacing.xs, fontStyle: "italic" },
  criticIterations: { fontSize: 10, marginTop: 4 },

  // Style guidelines
  guidelineText: { fontSize: 12, lineHeight: 18 },
});

function confirmReplacePlannedOutfit(day: string): Promise<boolean> {
  const message = `Une tenue est déjà planifiée le ${day}. Veux-tu la remplacer ?`;
  if (Platform.OS === "web") {
    return Promise.resolve(window.confirm(message));
  }
  return new Promise((resolve) => {
    Alert.alert("Remplacer la tenue ?", message, [
      { text: "Garder l'ancienne", style: "cancel", onPress: () => resolve(false) },
      { text: "Remplacer", onPress: () => resolve(true) },
    ]);
  });
}
