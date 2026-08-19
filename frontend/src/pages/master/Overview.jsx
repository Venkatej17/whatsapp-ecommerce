import { BarChart3, Building2, CheckCircle2, ChevronRight, Cloud, Package, Plus } from "lucide-react";
import Metric from "../../components/shared/Metric";
import Status from "../../components/shared/Status";
import { money } from "../../api";

export default function Overview({ data, setPage, user }) {
  const m = data.metrics || {};
  const firstName = user?.name?.split(" ")[0] || "there";
  return (
    <section className="content">
      <div className="page-heading">
        <div>
          <div className="eyebrow"><span className="pulse" /> PLATFORM CONTROL PLANE</div>
          <h1>Good morning, {firstName}.</h1>
          <p>Configure, monitor, and activate client workspaces from one place.</p>
        </div>
        <button className="primary-button" data-testid="new-client-button" onClick={() => setPage("Clients")}>
          <Plus size={17} /> New client
        </button>
      </div>
      <div className="metrics">
        <Metric label="Total clients" value={m.total_tenants} detail={`${m.active_tenants} active · ${m.onboarding_tenants} onboarding`} icon={Building2} />
        <Metric label="Platform revenue" value={money(m.platform_revenue)} detail="Across active clients" icon={BarChart3} tone="blue" />
        <Metric label="Integration health" value={`${m.integration_health}%`} detail="WhatsApp · Payments · Catalog" icon={Cloud} tone="green" />
      </div>
      <div className="admin-grid">
        <section className="panel">
          <div className="panel-head">
            <div>
              <h2>Client workspaces</h2>
              <p>Manage setup status and platform configuration — not their operations.</p>
            </div>
            <button className="text-button" data-testid="view-clients-button" onClick={() => setPage("Clients")}>Manage clients →</button>
          </div>
          <div className="admin-client-list">
            {(data.tenants || []).map((t) => (
              <div className="admin-client-row" key={t.id} data-testid={`admin-client-${t.id}`}>
                <div className="tenant-avatar">{t.name.slice(0, 1)}</div>
                <div><b>{t.name}</b><small>{t.category} · {t.status === "Active" ? "Live workspace" : "Onboarding"}</small></div>
                <div className="client-health"><small>Readiness</small><strong>{t.onboarding_progress}%</strong></div>
                <Status tone={t.status === "Active" ? "green" : t.status === "Suspended" ? "red" : "orange"}>{t.status}</Status>
                <button className="row-action" data-testid={`configure-client-${t.id}`} onClick={() => setPage("Clients")}>Configure</button>
              </div>
            ))}
          </div>
        </section>
        <section className="panel admin-setup">
          <div className="panel-head">
            <div><h2>Platform setup</h2><p>Keep the control plane ready for handover.</p></div>
          </div>
          {[
            ["Client onboarding", "Create tenant and owner access", "Clients"],
            ["Integrations", "WhatsApp, payments, catalog connections", "Integrations"],
            ["Templates", "Reusable messages and catalog structures", "Templates"],
            ["Automations", "Event-driven client workflows", "Automations"],
            ["Platform analytics", "Cross-tenant KPIs", "Analytics"],
          ].map(([title, desc, target], i) => (
            <button className="setup-row" key={title} data-testid={`admin-setup-${i}`} onClick={() => setPage(target)}>
              <span className="setup-number">0{i + 1}</span>
              <span><b>{title}</b><small>{desc}</small></span>
              <ChevronRight size={16} />
            </button>
          ))}
        </section>
      </div>
      <div className="admin-callout">
        <div className="callout-icon"><CheckCircle2 size={20} /></div>
        <div>
          <b>Master Admin never opens client operational data</b>
          <p>Orders, inventory, and customer records stay inside the client workspace. This control plane manages configuration, access, and platform readiness only.</p>
        </div>
      </div>
    </section>
  );
}
