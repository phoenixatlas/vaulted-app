/**
 * InvestorLeadsCard — captured leads from the "Get the one-pager" form
 * on the landing page. Shows total, repeat visitors (2+ downloads), top
 * company breakdown, and the 5 most recent leads with role + note preview.
 */
import { View, Text } from "react-native";
import { colors, spacing } from "@/src/lib/theme";
import { s } from "./styles";
import type { InvestorLeadsResp } from "./types";

type Props = {
  data: InvestorLeadsResp | null;
  loading: boolean;
  errorMsg?: string;
};

export function InvestorLeadsCard({ data, loading, errorMsg }: Props) {
  if (loading && !data) {
    return (
      <View style={s.card}>
        <Text style={s.cardTitle}>Investor leads</Text>
        <Text style={s.subtle}>Loading…</Text>
      </View>
    );
  }
  if (!data) {
    return (
      <View style={s.card}>
        <Text style={s.cardTitle}>Investor leads</Text>
        <Text style={s.subtle}>
          Unavailable. {errorMsg ? `(${errorMsg})` : "Endpoint returned an error."}
        </Text>
      </View>
    );
  }
  const recent = (data.leads || []).slice(0, 5);
  return (
    <View style={s.card}>
      <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: 4 }}>
        <Text style={s.cardTitle}>Investor leads</Text>
        <View style={{ flexDirection: "row", gap: 6 }}>
          <View style={s.pill}><Text style={s.pillText}>{data.total} total</Text></View>
          {data.total_repeat_visitors > 0 && (
            <View style={[s.pill, { backgroundColor: colors.brandTertiary, borderColor: colors.brand }]}>
              <Text style={[s.pillText, { color: colors.brandDeep }]}>{data.total_repeat_visitors} repeat</Text>
            </View>
          )}
        </View>
      </View>
      <Text style={s.subtle}>
        PDF downloads from the &ldquo;For Investors&rdquo; section on phoenix-atlas.com. Repeat visitors = 2+ downloads.
      </Text>

      {data.total === 0 ? (
        <Text style={[s.subtle, { marginTop: spacing.md }]}>
          No leads yet — share phoenix-atlas.com/#invest with your first prospect.
        </Text>
      ) : (
        <>
          {/* Top companies */}
          {data.top_companies.length > 0 && (
            <View style={{ marginTop: spacing.md, marginBottom: spacing.sm }}>
              <Text style={s.microLabel}>TOP COMPANIES</Text>
              <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 6, marginTop: 6 }}>
                {data.top_companies.map((c, i) => (
                  <View key={c.company + i} style={s.companyChip}>
                    <Text style={s.companyChipName}>{c.company}</Text>
                    <Text style={s.companyChipCount}>{c.count}</Text>
                  </View>
                ))}
              </View>
            </View>
          )}

          {/* Recent leads */}
          <View style={{ marginTop: spacing.md }}>
            <Text style={s.microLabel}>MOST RECENT</Text>
            {recent.map((lead) => (
              <View key={lead.email} style={s.leadRow}>
                <View style={{ flex: 1, minWidth: 0 }}>
                  <Text style={s.leadName} numberOfLines={1}>
                    {lead.name || lead.email}
                    {lead.role ? <Text style={s.leadRole}>{"  ·  "}{lead.role}</Text> : null}
                  </Text>
                  <Text style={s.leadEmail} numberOfLines={1}>
                    {lead.company ? `${lead.company} · ` : ""}{lead.email}
                  </Text>
                  {lead.note ? (
                    <Text style={s.leadNote} numberOfLines={2}>&ldquo;{lead.note}&rdquo;</Text>
                  ) : null}
                </View>
                {(lead.downloads || 0) > 1 && (
                  <View style={s.leadBadge}>
                    <Text style={s.leadBadgeText}>×{lead.downloads}</Text>
                  </View>
                )}
              </View>
            ))}
          </View>
        </>
      )}
    </View>
  );
}
