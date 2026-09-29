export const DATA_SUB_TABS = ["world", "experience", "entities", "preferences", "context"] as const;

export type DataSubTab = (typeof DATA_SUB_TABS)[number];

const LEGACY_DATA_SUB_TAB_ALIASES: Record<string, DataSubTab> = {
  observations: "preferences",
  "mental-models": "preferences",
  "guidance-v1": "preferences",
};

export function normalizeDataSubTab(rawSubTab: string | null): DataSubTab {
  if (!rawSubTab) return "world";
  if (rawSubTab in LEGACY_DATA_SUB_TAB_ALIASES) return LEGACY_DATA_SUB_TAB_ALIASES[rawSubTab];
  return (DATA_SUB_TABS as readonly string[]).includes(rawSubTab) ? (rawSubTab as DataSubTab) : "world";
}
