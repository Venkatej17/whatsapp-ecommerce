import { Settings2 } from "lucide-react";

export default function Settings() {
  return (
    <section className="content">
      <div className="empty-state">
        <div className="empty-icon"><Settings2 size={24} /></div>
        <div className="eyebrow">PLATFORM SETTINGS</div>
        <h1>System defaults</h1>
        <p>Platform-wide configuration will live here as it's built out.</p>
      </div>
    </section>
  );
}
