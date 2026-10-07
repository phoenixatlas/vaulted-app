/**
 * BookClicksCard — surfaces how many investors have hit "Book a call"
 * and which surface (hero / invest section / post-download / email) is
 * doing the heaviest lifting. Feeds the same funnel as InvestorLeadsCard
 * and tells Umar where to invest more copy or design weight.
 */
import { View, Text } from "react-native";
import { colors, spacing } from "@/src/lib/theme";
import { s } from "./styles";
import type { BookClicksResp } from "./types";

type Props = {
  data: BookClicksResp | null;
  loading: boolean;
  errorMsg?: string;
};

export function BookClicksCard({ data, loading, errorMsg }: Props) {
  if (loading && !data) {
    return (
      <View style={s.card}>
        <Text style={s.cardTitle}>Book-a-call clicks</Text>
        <Text style={s.subtle}>Loading…</Text>
      </View>
    );
  }
  if (!data) {
    return (
      <View style={s.card}>
        <Text style={s.cardTitle}>Book-a-call clicks</Text>
        <Text style={s.subtle}>
          Unavailable. {errorMsg ? `(${errorMsg})` : "Endpoint returned an error."}
        </Text>
      </View>
    );
  }
  // Nicer human labels for each landing-page surface. Falls back to raw.
  const SOURCE_LABEL: Record<string, string> = {
    hero: "Hero link",
    "invest-section": "Investor section CTA",
    "post-download": "After PDF download",
    "modal-open": "Modal → Google Calendar",
    email: "Investor email",
    "shortlink": "PDF shortlink redirect",
  };
  const label = (raw: string) =>
    SOURCE_LABEL[raw] || raw.replace(/-shortlink$/i, " (PDF)");

  return (
    <View style={s.card}>
      <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: 4 }}>
        <Text style={s.cardTitle}>Book-a-call clicks</Text>
        <View style={s.pill}><Text style={s.pillText}>{data.total} total</Text></View>
      </View>
      <Text style={s.subtle}>
        Every &ldquo;Book a 20-min call&rdquo; CTA across the landing page, PDFs and investor emails.
      </Text>

      {data.total === 0 ? (
        <Text style={[s.subtle, { marginTop: spacing.md }]}>
          No clicks yet — CTAs live on the hero, investor section, post-download modal, and inside each investor email.
        </Text>
      ) : (
        <View style={{ marginTop: spacing.md, gap: 8 }}>
          {data.by_source.map((row) => {
            const maxCount = Math.max(...data.by_source.map((r) => r.count), 1);
            const pct = Math.max(6, Math.round((row.count / maxCount) * 100));
            return (
              <View key={row.source} style={{ gap: 4 }}>
                <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
                  <Text style={s.leadName} numberOfLines={1}>{label(row.source)}</Text>
                  <Text style={s.leadRole}>{row.count}</Text>
                </View>
                <View style={{ height: 6, borderRadius: 3, backgroundColor: colors.divider, overflow: "hidden" }}>
                  <View style={{ width: `${pct}%`, height: "100%", backgroundColor: colors.brand }} />
                </View>
              </View>
            );
          })}
        </View>
      )}
    </View>
  );
}
