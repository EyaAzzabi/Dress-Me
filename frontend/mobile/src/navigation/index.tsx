import { createBottomTabNavigator } from "@react-navigation/bottom-tabs";
import { DarkTheme, DefaultTheme, NavigationContainer } from "@react-navigation/native";
import { createNativeStackNavigator } from "@react-navigation/native-stack";
import { useState } from "react";
import { ActivityIndicator, View } from "react-native";

import { useAuth } from "@/context/AuthContext";
import { useTheme } from "@/theme/ThemeContext";
import CalendarScreen from "@/screens/CalendarScreen";
import LoginScreen from "@/screens/LoginScreen";
import OnboardingScreen from "@/screens/OnboardingScreen";
import OutfitRecommendationsScreen from "@/screens/OutfitRecommendationsScreen";
import PackingScreen from "@/screens/PackingScreen";
import PurchaseCheckScreen from "@/screens/PurchaseCheckScreen";
import StyleProfileScreen from "@/screens/StyleProfileScreen";
import TryOnScreen from "@/screens/TryOnScreen";
import WardrobeScreen from "@/screens/WardrobeScreen";

const Tab = createBottomTabNavigator();
const AppStack = createNativeStackNavigator();

function AppTabs() {
  const { colors } = useTheme();
  return (
    <Tab.Navigator
      screenOptions={{
        headerShown: false,
        tabBarStyle: { backgroundColor: colors.tabBg, borderTopColor: colors.tabBorder },
        tabBarActiveTintColor: colors.tabActive,
        tabBarInactiveTintColor: colors.tabInactive,
      }}
    >
      <Tab.Screen name="Wardrobe" component={WardrobeScreen} />
      <Tab.Screen name="Outfits" component={OutfitRecommendationsScreen} />
      <Tab.Screen name="Buy" component={PurchaseCheckScreen} options={{ title: "Should I buy this?" }} />
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
  );
}

function AppFlow() {
  return (
    <AppStack.Navigator screenOptions={{ headerShown: false }}>
      <AppStack.Screen name="Tabs" component={AppTabs} />
      <AppStack.Screen name="Packing" component={PackingScreen} options={{ headerShown: true, title: "La valise" }} />
      <AppStack.Screen name="TryOn" component={TryOnScreen} options={{ headerShown: true, title: "Try it on" }} />
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
        <ActivityIndicator color={colors.primary} />
      </View>
    );
  }

  const navTheme = isDark ? DarkTheme : DefaultTheme;

  return (
    <NavigationContainer theme={navTheme}>
      {isAuthenticated ? <AppFlow /> : <AuthFlow />}
    </NavigationContainer>
  );
}
