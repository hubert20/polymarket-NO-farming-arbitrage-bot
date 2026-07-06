import { botApiUrl } from "@/lib/format";
import { BotSettings, BotSettingsPayload } from "@/types/settings";

export async function fetchSettings(): Promise<BotSettings> {
  const resp = await fetch(`${botApiUrl()}/api/settings`);
  if (!resp.ok) throw new Error("Could not load settings");
  return resp.json();
}

export async function saveSettings(payload: BotSettingsPayload): Promise<{ ok: boolean; message?: string; error?: string }> {
  const resp = await fetch(`${botApiUrl()}/api/settings`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await resp.json();
  if (!resp.ok) throw new Error(data.error || "Save failed");
  return data;
}
