import { useEffect, useState } from "react";
import { CheckCircle2, ShieldCheck } from "lucide-react";
import { api } from "../../api";

export default function Settings() {
  const [s, setS] = useState(null);
  useEffect(() => { api.get("/workspace/settings").then((r) => setS(r.data)).catch(() => {}); }, []);
  if (!s) return <section className="content"><p>Loading…</p></section>;
  const b = s.business || {};
  const f = s.fulfilment || {};
  const i = s.integrations || {};

  return (
    <section className="content">
      <div className="page-heading">
        <div>
          <div className="eyebrow">WORKSPACE SETTINGS</div>
          <h1>Business profile &amp; policies</h1>
          <p>Configured by the platform team. Contact support to change delivery rules.</p>
        </div>
      </div>
      <div className="settings-grid">
        <div className="panel settings-card" data-testid="settings-business">
          <b>Business profile</b>
          <ul>
            <li><small>Phone</small><b>{b.phone || "—"}</b></li>
            <li><small>Email</small><b>{b.email || "—"}</b></li>
            <li><small>City</small><b>{b.city || "—"}</b></li>
            <li><small>State · Pincode</small><b>{b.state} {b.pincode}</b></li>
            <li><small>Currency · Timezone</small><b>{b.currency} · {b.timezone}</b></li>
          </ul>
        </div>
        <div className="panel settings-card" data-testid="settings-fulfilment">
          <b>Fulfilment</b>
          <ul>
            <li><small>Home delivery</small><b>{f.home_delivery?.enabled ? `Enabled · ₹${f.home_delivery?.base_charge} · Free above ₹${f.home_delivery?.free_above}` : "Disabled"}</b></li>
            <li><small>Store pickup</small><b>{f.store_pickup?.enabled ? `${(f.store_pickup?.locations || []).length || 1} location(s)` : "Disabled"}</b></li>
            {(f.store_pickup?.locations || []).map((loc) => (
              <li key={loc.id}><small>{loc.name}</small><b>{loc.address} · {loc.hours}</b></li>
            ))}
            <li><small>Prep time</small><b>{f.store_pickup?.preparation_minutes} minutes</b></li>
          </ul>
        </div>
        <div className="panel settings-card" data-testid="settings-integrations">
          <b>Integrations</b>
          <ul>
            <li><small>WhatsApp</small><b>{i.whatsapp?.connected ? `${i.whatsapp?.phone_number} · ${i.whatsapp?.provider}` : "Not connected"}</b></li>
            <li><small>Catalog</small><b>{i.catalog?.connected ? i.catalog?.source : "Not connected"}</b></li>
            <li><small>Payment</small><b>{i.payment?.configured ? `${i.payment?.provider} · ${i.payment?.mode}` : "Not configured"}</b></li>
            <li><small>Templates</small><b>{s.templates_count} applied</b></li>
            <li><small>Automations</small><b>{(s.automations || []).length} active</b></li>
          </ul>
        </div>
        <div className="panel settings-card">
          <b>Access</b>
          <ul>
            <li><CheckCircle2 size={14} color="#25a65a" /> <small>Owner login</small><b>One per workspace (MVP)</b></li>
            <li><ShieldCheck size={14} color="#2563eb" /> <small>Tenant isolation</small><b>Backend-enforced</b></li>
          </ul>
        </div>
      </div>
    </section>
  );
}
