import { Zap } from "lucide-react";

const RULES = [
  { event: "order_created", action: "Send order confirmation template" },
  { event: "status_ready_for_pickup", action: "Send pickup notification with store address" },
  { event: "status_out_for_delivery", action: "Send delivery-on-the-way template" },
  { event: "status_delivered", action: "Send completion message" },
  { event: "cart_abandoned", action: "Send abandoned-cart reminder after 2h" },
  { event: "payment_captured", action: "Send payment confirmation template" },
];

export default function Automations() {
  return (
    <section className="content">
      <div className="page-heading">
        <div>
          <div className="eyebrow">EVENT ENGINE</div>
          <h1>Automations</h1>
          <p>Rules the platform runs against every client workspace event.</p>
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
            <span className="badge-live">ACTIVE</span>
          </div>
        ))}
      </div>
    </section>
  );
}
