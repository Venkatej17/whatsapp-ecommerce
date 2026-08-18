import { useEffect, useState } from "react";
import { Cloud, CreditCard, Package } from "lucide-react";
import { api } from "../../api";

export default function Integrations() {
  const [data, setData] = useState({});
  useEffect(() => { api.get("/admin/integrations").then((r) => setData(r.data)).catch(() => {}); }, []);
  const cards = [
    ["WhatsApp", "whatsapp", Cloud, "green", "Meta Cloud API"],
    ["Catalog", "catalog", Package, "blue", "Internal storefront"],
    ["Payment", "payment", CreditCard, "orange", "Razorpay (test mode)"],
  ];
  return (
    <section className="content">
      <div className="page-heading">
        <div>
          <div className="eyebrow">PLATFORM INTEGRATIONS</div>
          <h1>Integration health</h1>
          <p>Cross-tenant status of the connectors that power every workspace.</p>
        </div>
      </div>
      <div className="metrics">
        {cards.map(([label, key, Icon, tone, sub]) => {
          const d = data[key] || {};
          return (
            <div key={key} className="metric" data-testid={`integration-${key}`}>
              <div className={`metric-icon ${tone}`}><Icon size={18} /></div>
              <div>
                <p>{label}</p>
                <strong>{d.connected ?? 0} / {d.total ?? 0}</strong>
                <small>{sub}</small>
              </div>
            </div>
          );
        })}
      </div>
      <div className="panel">
        <div className="panel-head">
          <div><h2>What master admin controls</h2><p>Integration lifecycle stays here — client workspaces only consume it.</p></div>
        </div>
        <ul className="platform-list">
          <li><b>WhatsApp / Meta</b><small>Business account, phone number, webhook, template registration.</small></li>
          <li><b>Catalog connectors</b><small>Choose internal, Shopify, or WooCommerce sync per client.</small></li>
          <li><b>Payments</b><small>Provider selection, mode, COD toggle, UPI, refunds.</small></li>
          <li><b>Automation engine</b><small>Enable/disable event flows for each tenant.</small></li>
          <li><b>Templates</b><small>Master library, per-tenant customization, approval workflow.</small></li>
        </ul>
      </div>
    </section>
  );
}
