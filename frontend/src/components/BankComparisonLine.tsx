/**
 * "≈ X more than a typical bank transfer" line under a remit quote.
 * Same illustrative assumption as phoenix-atlas.com: £25 fee + 3% FX margin.
 */
import { Text, View, StyleSheet } from "react-native";
import { colors } from "@/src/lib/theme";

const BANK_FEE_GBP = 25;
const BANK_FX_MARGIN = 0.03;

type Props = {
  sourceAmount: number;
  sourceAmountGbp: number;
  sourceAmountUsd: number;
  serviceFeeUsd: number;
  fxRate: number;
  recipientAmount: number;
  currency: string;
};

export default function BankComparisonLine({ sourceAmount, sourceAmountGbp, sourceAmountUsd, serviceFeeUsd, fxRate, recipientAmount, currency }: Props) {
  if (!sourceAmount || !sourceAmountGbp || !fxRate || !sourceAmountUsd) return null;
  const feeInSource = BANK_FEE_GBP * (sourceAmount / sourceAmountGbp);
  // A bank fee that swallows the whole send isn't a fair comparison — hide the line.
  if (sourceAmount <= feeInSource) return null;
  const bankGets = (sourceAmount - feeInSource) * fxRate * (1 - BANK_FX_MARGIN);
  // Net of our own service fee so the saving isn't overstated.
  const ourFeeInDest = (serviceFeeUsd || 0) * (recipientAmount / sourceAmountUsd);
  const diff = recipientAmount - ourFeeInDest - bankGets;
  if (diff <= 0) return null;
  const digits = fxRate > 100 ? 0 : 2;
  return (
    <View style={st.wrap} testID="remit-bank-comparison">
      <Text style={st.main}>
        ≈ {diff.toLocaleString(undefined, { maximumFractionDigits: digits })} {currency} more than a typical bank transfer*
      </Text>
      <Text style={st.note}>
        *Illustrative: assumes a £{BANK_FEE_GBP} bank fee and {BANK_FX_MARGIN * 100}% exchange-rate margin. Real bank costs vary.
      </Text>
    </View>
  );
}

const st = StyleSheet.create({
  wrap: { marginTop: 8 },
  main: { fontSize: 13, fontWeight: "700", color: colors.success },
  note: { fontSize: 11, color: colors.onSurfaceTertiary, marginTop: 2 },
});
