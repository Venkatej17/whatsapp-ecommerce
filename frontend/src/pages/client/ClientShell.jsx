import { useCallback, useEffect, useState } from "react";
import { BarChart3, Boxes, ClipboardList, LayoutDashboard, LogOut, Map, MessageCircle, Package, Settings2, ShieldCheck, Truck, Users, Zap } from "lucide-react";
import { toast } from "sonner";
import { api } from "../../api";
import Topbar from "../../components/shared/Topbar";
import Overview from "./Overview";
import Products from "./Products";
import Inventory from "./Inventory";
import Orders from "./Orders";
import Fulfilment from "./Fulfilment";
import DeliveryRoute from "./DeliveryRoute";
import Customers from "./Customers";
import Conversations from "./Conversations";
import Analytics from "./Analytics";
import Settings from "./Settings";

const NAV = [
  ["Overview", LayoutDashboard],
  ["Orders", ClipboardList],
  ["Fulfilment", Truck],
  ["Route", Map],
  ["Products", Package],
  ["Inventory", Boxes],
  ["Customers", Users],
  ["Conversations", MessageCircle],
  ["Analytics", BarChart3],
];

export default function ClientShell({ user, onLogout, onUserUpdate }) {
  const [page, setPage] = useState("Overview");
  const [data, setData] = useState({ tenant: {}, orders: [], products: [], metrics: {} });

  const load = useCallback(() => {
    api.get("/workspace/overview")
      .then((r) => setData(r.data))
      .catch(() => toast.error("Could not load workspace"));
  }, []);

  useEffect(() => { load(); }, [load]);

  const tenant = data.tenant || {};

  return (
    <div className="shell">
      <aside className="sidebar" data-testid="client-sidebar">
        <div className="brand">
          <div className="brand-mark"><Zap size={18} fill="currentColor" /></div>
          <div><b>agent<span>Opscom</span></b><small>CLIENT WORKSPACE</small></div>
        </div>
        <div className="workspace-label">YOUR BUSINESS</div>
        <div className="tenant-switch locked-workspace" data-testid="client-workspace-identity">
          <span className="tenant-avatar">{tenant.name?.slice(0, 1) || user.name?.slice(0, 1)}</span>
          <span><b>{tenant.name || user.name}</b><small>Owner access only</small></span>
          <ShieldCheck size={16} />
        </div>
        <nav>
          {NAV.map(([name, Icon]) => (
            <button key={name} data-testid={`client-nav-${name.toLowerCase()}`} className={page === name ? "active" : ""} onClick={() => setPage(name)}>
              <Icon size={17} /><span>{name}</span>
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <button data-testid="client-settings-button" onClick={() => setPage("Settings")}><Settings2 size={17} />Settings</button>
          <button className="sidebar-logout" data-testid="client-logout-button" onClick={onLogout}><LogOut size={17} />Sign out</button>
        </div>
      </aside>
      <main className="main">
        <Topbar user={user} onLogout={onLogout} label={page} onUserUpdate={onUserUpdate} />
        {page === "Overview" && <Overview data={data} setPage={setPage} refresh={load} />}
        {page === "Products" && <Products refresh={load} />}
        {page === "Inventory" && <Inventory refresh={load} />}
        {page === "Orders" && <Orders refresh={load} />}
        {page === "Fulfilment" && <Fulfilment refresh={load} />}
        {page === "Route" && <DeliveryRoute />}
        {page === "Customers" && <Customers />}
        {page === "Conversations" && <Conversations />}
        {page === "Analytics" && <Analytics />}
        {page === "Settings" && <Settings />}
      </main>
    </div>
  );
}
