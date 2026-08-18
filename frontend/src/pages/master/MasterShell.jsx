import { useCallback, useEffect, useState } from "react";
import { BarChart3, Building2, ClipboardList, Cloud, LayoutDashboard, LogOut, Package, Settings2, ShieldCheck, ShoppingCart, Zap } from "lucide-react";
import { toast } from "sonner";
import { api } from "../../api";
import Topbar from "../../components/shared/Topbar";
import Overview from "./Overview";
import Clients from "./Clients";
import Integrations from "./Integrations";
import Templates from "./Templates";
import Automations from "./Automations";
import Analytics from "./Analytics";
import Settings from "./Settings";
import AbandonedCarts from "./AbandonedCarts";

const NAV = [
  ["Overview", LayoutDashboard],
  ["Clients", Building2],
  ["Integrations", Cloud],
  ["Templates", Package],
  ["Automations", Zap],
  ["Carts", ShoppingCart],
  ["Analytics", BarChart3],
  ["Audit", ClipboardList],
];

export default function MasterShell({ user, onLogout }) {
  const [page, setPage] = useState("Overview");
  const [overview, setOverview] = useState({ tenants: [], metrics: {} });

  const load = useCallback(() => {
    api.get("/admin/overview")
      .then((r) => setOverview(r.data))
      .catch(() => toast.error("Could not load control plane"));
  }, []);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="shell">
      <aside className="sidebar" data-testid="master-sidebar">
        <div className="brand">
          <div className="brand-mark"><Zap size={18} fill="currentColor" /></div>
          <div><b>commerce<span>OS</span></b><small>CONTROL PLANE</small></div>
        </div>
        <div className="workspace-label">MASTER ADMIN</div>
        <div className="admin-identity">
          <div className="admin-symbol"><ShieldCheck size={18} /></div>
          <span><b>Platform control</b><small>All client workspaces</small></span>
        </div>
        <nav>
          {NAV.map(([name, Icon]) => (
            <button key={name} data-testid={`master-nav-${name.toLowerCase()}`} className={page === name ? "active" : ""} onClick={() => setPage(name)}>
              <Icon size={17} /><span>{name}</span>
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <button data-testid="master-settings-button" onClick={() => setPage("Settings")}><Settings2 size={17} />Settings</button>
          <button className="sidebar-logout" data-testid="master-logout-button" onClick={onLogout}><LogOut size={17} />Sign out</button>
        </div>
      </aside>
      <main className="main">
        <Topbar user={user} onLogout={onLogout} label={page} />
        {page === "Overview" && <Overview data={overview} setPage={setPage} />}
        {page === "Clients" && <Clients onChange={load} />}
        {page === "Integrations" && <Integrations />}
        {page === "Templates" && <Templates />}
        {page === "Automations" && <Automations />}
        {page === "Carts" && <AbandonedCarts />}
        {page === "Analytics" && <Analytics />}
        {page === "Audit" && <AuditPage />}
        {page === "Settings" && <Settings />}
      </main>
    </div>
  );
}

function AuditPage() {
  const [logs, setLogs] = useState([]);
  useEffect(() => { api.get("/admin/audit").then((r) => setLogs(r.data)).catch(() => {}); }, []);
  return (
    <section className="content">
      <div className="page-heading">
        <div>
          <div className="eyebrow">PLATFORM AUDIT</div>
          <h1>Recent activity</h1>
          <p>Every configuration change and status transition across the platform.</p>
        </div>
      </div>
      <div className="panel full-panel">
        <table>
          <thead><tr><th>WHEN</th><th>ACTOR</th><th>ACTION</th><th>TARGET</th></tr></thead>
          <tbody>
            {logs.length === 0 ? (
              <tr><td colSpan="4" style={{ padding: 40, textAlign: "center", color: "#64748b" }}>No activity yet.</td></tr>
            ) : logs.map((l) => (
              <tr key={l.id} data-testid={`audit-row-${l.id}`}>
                <td><small className="mono">{new Date(l.at).toLocaleString()}</small></td>
                <td><b>{l.actor_name}</b><small>{l.actor_role}</small></td>
                <td className="mono">{l.action}</td>
                <td className="mono">{l.target}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
