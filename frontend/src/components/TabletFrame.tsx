import { ReactNode } from "react";
import { View, StyleSheet } from "react-native";
import { colors } from "@/src/lib/theme";

// Keeps the phone-first layouts readable on iPad / large screens by
// centring all content in a comfortable column instead of stretching it.
export const MAX_CONTENT_WIDTH = 720;

export default function TabletFrame({ children }: { children: ReactNode }) {
  return (
    <View style={s.outer}>
      <View style={s.inner}>{children}</View>
    </View>
  );
}

const s = StyleSheet.create({
  outer: { flex: 1, alignItems: "center", backgroundColor: colors.surfaceSecondary },
  inner: { flex: 1, width: "100%", maxWidth: MAX_CONTENT_WIDTH, backgroundColor: colors.surface },
});
