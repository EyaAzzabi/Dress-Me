import { createBottomTabNavigator } from "@react-navigation/bottom-tabs";
import { DarkTheme, DefaultTheme, NavigationContainer } from "@react-navigation/native";
import { createNativeStackNavigator } from "@react-navigation/native-stack";
import { useState } from "react";
import { ActivityIndicator, StyleSheet, Text, View } from "react-native";


import { platformShadow } from "@/utils/platformStyles";
import { SeasonalBanner } from "@/components/SeasonalBanner";
import { useAuth } from "@/context/AuthContext";
import CalendarScreen from "@/screens/CalendarScreen";
import LoginScreen from "@/screens/LoginScreen";
import OnboardingScreen from "@/screens/OnboardingScreen";
import OutfitRecommendationsScreen from "@/screens/OutfitRecommendationsScreen";
import PackingScreen from "@/screens/PackingScreen";
import PurchaseCheckScreen from "@/screens/PurchaseCheckScreen";
import StyleProfileScreen from "@/screens/StyleProfileScreen";
import TryOnScreen from "@/screens/TryOnScreen";
import WardrobeScreen from "@/screens/WardrobeScreen";
import { useTheme } from "@/theme/ThemeContext";

const Tab = createBottomTabNavigator();
const AppStack = createNativeStackNavigator();

const TAB_ICONS: Record<string, string> = {
  Wardrobe: "👗",
  Outfits: "✨",
  Buy: "🛍️",
  Calendar: "📅",
  Profile: "👤",
};

function AppTabs() {
  const { colors } = useTheme();
  return (
    <>
      <SeasonalBanner />
      <Tab.Navigator
        screenOptions={({ route }) => ({
          headerShown: false,
          tabBarStyle: {
            backgroundColor: colors.tabBg,
            borderTopColor: colors.tabBorder,
            borderTopWidth: 1,
            paddingTop: 7,
            paddingBottom: 5,
            ...platformShadow(colors.tunisianNavy, { y: -4, opacity: 0.08, radius: 12 }),
          },
          tabBarActiveTintColor: colors.tabActive,
          tabBarInactiveTintColor: colors.tabInactive,
          tabBarIcon: ({ color, size, focused }) => (
            <View
              style={[
                styles.tabIcon,
                { backgroundColor: focused ? colors.surface : "transparent" },
              ]}
            >
              <Text style={{ fontSize: size - 4, color }}>
                {TAB_ICONS[route.name] ?? "●"}
              </Text>
            </View>
          ),
          tabBarLabelStyle: {
            fontWeight: "700",
            fontSize: 10,
            marginTop: 2,
            marginBottom: 1,
          },
          tabBarItemStyle: { paddingVertical: 1 },
          tabBarHideOnKeyboard: true,
        })}
      >
        <Tab.Screen name="Wardrobe" component={WardrobeScreen} />
        <Tab.Screen name="Outfits" component={OutfitRecommendationsScreen} />
        <Tab.Screen name="Buy" component={PurchaseCheckScreen} options={{ title: "Buy?" }} />
        <Tab.Screen name="Calendar" component={CalendarScreen} />
        <Tab.Screen name="Profile">
          {(props) => (
            <StyleProfileScreen
              {...props}
              onGoToPacking={() => props.navigation.getParent()?.navigate("Packing")}
              onGoToTryOn={() => props.navigation.getParent()?.navigate("TryOn")}
              onGoToCalendar={() => props.navigation.navigate("Calendar")}
            />
          )}
        </Tab.Screen>
      </Tab.Navigator>
    </>
  );
}

const styles = StyleSheet.create({
  tabIcon: {
    minWidth: 38,
    height: 30,
    paddingHorizontal: 8,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 12,
  },
});

function AppFlow() {
  const { colors } = useTheme();
  return (
    <AppStack.Navigator screenOptions={{ headerShown: false }}>
      <AppStack.Screen name="Tabs" component={AppTabs} />
      <AppStack.Screen
        name="Packing"
        component={PackingScreen}
        options={{
          headerShown: true,
          title: "La valise",
          headerStyle: { backgroundColor: colors.bg },
          headerTintColor: colors.primary,
          headerTitleStyle: { color: colors.text, fontWeight: "700" },
        }}
      />
      <AppStack.Screen
        name="TryOn"
        component={TryOnScreen}
        options={{
          headerShown: true,
          title: "Try it on",
          headerStyle: { backgroundColor: colors.bg },
          headerTintColor: colors.primary,
          headerTitleStyle: { color: colors.text, fontWeight: "700" },
        }}
      />
    </AppStack.Navigator>
  );
}

function AuthFlow() {
  const [showOnboarding, setShowOnboarding] = useState(false);
  return showOnboarding ? (
    <OnboardingScreen onBackToLogin={() => setShowOnboarding(false)} />
  ) : (
    <LoginScreen onGoToOnboarding={() => setShowOnboarding(true)} />
  );
}

export default function RootNavigator() {
  const { isAuthenticated, isLoading } = useAuth();
  const { isDark, colors } = useTheme();

  if (isLoading) {
    return (
      <View style={{ flex: 1, justifyContent: "center", alignItems: "center", backgroundColor: colors.bg }}>
        <ActivityIndicator color={colors.primary} size="large" />
      </View>
    );
  }

  const navTheme = {
    ...(isDark ? DarkTheme : DefaultTheme),
    colors: {
      ...(isDark ? DarkTheme : DefaultTheme).colors,
      background: colors.bg,
      card: colors.tabBg,
      primary: colors.primary,
      border: colors.tabBorder,
      text: colors.text,
    },
  };

  return (
    <NavigationContainer theme={navTheme}>
      {isAuthenticated ? <AppFlow /> : <AuthFlow />}
    </NavigationContainer>
  );
}
