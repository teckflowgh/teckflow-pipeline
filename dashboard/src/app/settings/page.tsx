import SettingsForm from "@/components/SettingsForm";
import { fetchSettings } from "@/lib/api";

export default async function SettingsPage() {
  let settings;
  try {
    settings = await fetchSettings();
  } catch {
    settings = {
      schedule_time: "06:00",
      timezone: "Europe/Brussels",
      topic_source: "youtube",
      youtube_category_id: "28",
      script_language: "en",
      alert_email: "",
      alert_webhook_url: "",
      cleanup_days: 7,
      history_max_entries: 365,
    };
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Settings</h1>
        <p className="text-sm text-gray-500 mt-0.5">
          Configure the pipeline schedule, topic source, and alerts.
        </p>
      </div>
      <SettingsForm initial={settings} />
    </div>
  );
}
