/**
 * PasswordInput
 * =============
 * Text input with a built-in eye toggle to reveal/hide the typed
 * password. Keeps the look consistent across Register / Login /
 * Settings-change-password screens.
 *
 * Why a dedicated component?
 *   • One place for the reveal UX (platform-safe, no auto-fill
 *     interference, correct `autoComplete` + `textContentType` hints
 *     for iOS/Android password managers).
 *   • Enforces the same visual weight as the existing `s.input` style
 *     on auth screens so there's no visual drift when swapped in.
 */
import { useState } from "react";
import {
  View, TextInput, Pressable, StyleSheet,
  type TextInputProps, type StyleProp, type ViewStyle,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { colors, radius, spacing } from "@/src/lib/theme";

type Props = Omit<TextInputProps, "secureTextEntry"> & {
  /** Wrapper override — matches the host screen's existing `s.input` style. */
  containerStyle?: StyleProp<ViewStyle>;
  /** `new-password` for sign-up flows unlocks strong-password suggestions on
   * iOS/Android. `current-password` for sign-in. Defaults to `current-password`
   * so unlabelled callers behave like a login input. */
  passwordType?: "new-password" | "current-password";
  /** Shown as the accessibility label on the reveal button. */
  revealLabel?: string;
};

export function PasswordInput({
  containerStyle,
  style,
  passwordType = "current-password",
  revealLabel,
  testID,
  ...rest
}: Props) {
  const [visible, setVisible] = useState(false);
  return (
    <View style={[localStyles.wrap, containerStyle]}>
      <TextInput
        {...rest}
        testID={testID}
        secureTextEntry={!visible}
        // Keep caret predictable while toggling and prevent iOS from
        // appending ·spaces during autocorrect in password fields.
        autoCapitalize="none"
        autoCorrect={false}
        // Platform hints so the OS password manager offers the right
        // affordance (save vs autofill).
        autoComplete={passwordType === "new-password" ? "password-new" : "password"}
        textContentType={passwordType === "new-password" ? "newPassword" : "password"}
        style={[localStyles.input, style]}
        placeholderTextColor={colors.onSurfaceTertiary}
      />
      <Pressable
        onPress={() => setVisible((v) => !v)}
        hitSlop={10}
        style={localStyles.eye}
        accessibilityRole="button"
        accessibilityLabel={revealLabel || (visible ? "Hide password" : "Show password")}
        testID={testID ? `${testID}-reveal` : "password-reveal"}
      >
        <Ionicons
          name={visible ? "eye-off-outline" : "eye-outline"}
          size={20}
          color={colors.onSurfaceSecondary}
        />
      </Pressable>
    </View>
  );
}

const localStyles = StyleSheet.create({
  wrap: {
    position: "relative",
    justifyContent: "center",
  },
  input: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    paddingHorizontal: spacing.lg,
    // Extra right padding to clear the eye icon.
    paddingRight: 44,
    paddingVertical: 14,
    fontSize: 16,
    color: colors.onSurface,
    backgroundColor: colors.surface,
  },
  eye: {
    position: "absolute",
    right: 10,
    top: 0,
    bottom: 0,
    width: 32,
    alignItems: "center",
    justifyContent: "center",
  },
});
