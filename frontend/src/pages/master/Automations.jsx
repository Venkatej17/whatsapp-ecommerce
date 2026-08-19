import { Zap } from "lucide-react";

const RULES = [
  { event: "order_created", action: "Send order confirmation to the customer" },
  { event: "status_ready_for_pickup", action: "Send pickup notification with store address" },
  { event: "status_out_for_delivery", action: "Send delivery-on-the-way notification" },
  { event: "status_delivered", action: "Send completion message + invoice" },
  { event: "cart_abandoned", action: "Send a reminder after 2h of inactivity (checked every 15 min)" },
];

export default function Automations() {
  return (
    <section className="content">
      <div className="page-heading">
        <div>
          <div className="eyebrow">EVENT ENGINE</div>
          <h1>Automations</h1>
          <p>Built into every client's WhatsApp flow automatically — not yet configurable per client.</p>
        </div>
      </div>
      <div className="automation-list">
        {RULES.map((r) => (
          <div key={r.event} className="automation-card" data-testid={`automation-${r.event}`}>
            <div className="automation-icon"><Zap size={18} /></div>
            <div>
              <b>WHEN <span className="mono">{r.event}</span></b>
              <small>THEN {r.action}</small>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
