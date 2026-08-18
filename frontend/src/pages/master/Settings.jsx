import { Settings2 } from "lucide-react";

export default function Settings() {
  return (
    <section className="content">
      <div className="empty-state">
        <div className="empty-icon"><Settings2 size={24} /></div>
        <div className="eyebrow">PLATFORM SETTINGS</div>
        <h1>System defaults</h1>
        <p>Plans, permissions, and defaults for the whole Commerce OS. Client workspaces cannot see this area.</p>
        <div className="settings-list">
          <div><b>Roles &amp; permissions</b><small>Master, tenant owner, packer, delivery, pickup staff.</small></div>
          <div><b>Plans</b><small>Starter · Growth · Enterprise — usage-based limits.</small></div>
          <div><b>Data residency</b><small>India (Mumbai) · Europe (Frankfurt).</small></div>
          <div><b>Support access</b><small>Master admin can enter a client workspace in read-only support mode.</small></div>
        </div>
      </div>
    </section>
  );
}
