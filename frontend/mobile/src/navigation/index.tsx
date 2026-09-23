import { NavigationContainer } from "@react-navigation/native";
import { createBottomTabNavigator } from "@react-navigation/bottom-tabs";
import { ActivityIndicator, View } from "react-native";

import { useAuth } from "@/context/AuthContext";
import LoginScreen from "@/screens/LoginScreen";
import OutfitRecommendationsScreen from "@/screens/OutfitRecommendationsScreen";
import PurchaseCheckScreen from "@/screens/PurchaseCheckScreen";
import StyleProfileScreen from "@/screens/StyleProfileScreen";
import WardrobeScreen from "@/screens/WardrobeScreen";

const Tab = createBottomTabNavigator();

function AppTabs() {
  return (
    <Tab.Navigator>
      <Tab.Screen name="Wardrobe" component={WardrobeScreen} />
      <Tab.Screen name="Outfits" component={OutfitRecommendationsScreen} />
      <Tab.Screen name="Should I buy this?" component={PurchaseCheckScreen} />
      <Tab.Screen name="Profile" component={StyleProfileScreen} />
    </Tab.Navigator>
  );
}

export default function RootNavigator() {
  const { isAuthenticated, isLoading } = useAuth();

  if (isLoading) {
    return (
      <View style={{ flex: 1, justifyContent: "center", alignItems: "center" }}>
        <ActivityIndicator />
      </View>
    );
  }

  return (
    <NavigationContainer>
      {isAuthenticated ? <AppTabs /> : <LoginScreen />}
    </NavigationContainer>
  );
}
