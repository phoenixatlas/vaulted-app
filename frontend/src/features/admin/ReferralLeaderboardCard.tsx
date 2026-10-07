/**
 * ReferralLeaderboardCard — Top referrers + Founding Members count.
 */
import { View, Text } from "react-native";
import { ReferralLeaderboard } from "@/src/components/AdminCharts";
import { s } from "./styles";
import type { ReferralsResp } from "./types";

type Props = {
  data: ReferralsResp | null;
  loading: boolean;
  errorMsg?: string;
};

export function ReferralLeaderboardCard({ data, loading, errorMsg }: Props) {
  if (loading && !data) {
    return (
      <View style={s.card}>
        <Text style={s.cardTitle}>Referral leaderboard</Text>
        <Text style={s.subtle}>Loading…</Text>
      </View>
    );
  }
  if (!data) {
    return (
      <View style={s.card}>
        <Text style={s.cardTitle}>Referral leaderboard</Text>
        <Text style={s.subtle}>
          Unavailable. {errorMsg ? `(${errorMsg})` : "Endpoint returned an error."}
        </Text>
      </View>
    );
  }
  return (
    <View style={s.card}>
      <Text style={s.cardTitle}>Referral leaderboard</Text>
      <Text style={s.subtle}>
        Top waitlist referrers. Every {data.totals.boost_interval} refs moves them up {data.totals.boost_spots} spots; {data.totals.founding_threshold}+ unlocks the Founding Member badge.
      </Text>
      <ReferralLeaderboard leaders={data.leaders} totals={data.totals} />
    </View>
  );
}
