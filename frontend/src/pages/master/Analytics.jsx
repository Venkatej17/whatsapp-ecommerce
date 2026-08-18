import { useEffect, useState } from "react";
import { BarChart3, Building2, TrendingUp } from "lucide-react";
import { api, money } from "../../api";
import Metric from "../../components/shared/Metric";

export default function Analytics() {
  const [data, setData] = useState({ by_tenant: [], totals: {}, growth: {} });
  useEffect(() => { api.get("/admin/analytics").then((r) => setData(r.data)).catch(() => {}); }, []);
  const t = data.totals || {};
  return (
    <section className="content">
      <div className="page-heading">
        <div>
          <div className="eyebrow">PLATFORM ANALYTICS</div>
          <h1>Platform performance</h1>
          <p>Aggregate KPIs across every client workspace. Client-level operational data stays inside its workspace.</p>
        </div>
      </div>
      <div className="metrics">
        <Metric label="Total tenants" value={t.tenants} detail="Live and onboarding" icon={Building2} />
        <Metric label="Platform orders" value={t.orders} detail="Aggregated" icon={BarChart3} tone="blue" />
        <Metric label="Platform revenue" value={money(t.revenue)} detail="All clients" icon={TrendingUp} tone="green" />
        <Metric label="Revenue growth" value={`${data.growth?.revenue_growth ?? 0}%`} detail="Month over month" icon={TrendingUp} tone="orange" />
      </div>
      <div className="panel">
        <div className="panel-head"><div><h2>By client</h2><p>Configuration-level view — not operational drill-down.</p></div></div>
        <table>
          <thead><tr><th>CLIENT</th><th>ORDERS</th><th>REVENUE</th><th>SHARE</th></tr></thead>
          <tbody>
            {data.by_tenant.map((r) => (
              <tr key={r.name} data-testid={`analytics-row-${r.name}`}>
                <td><b>{r.name}</b></td>
                <td>{r.orders}</td>
                <td><b>{money(r.revenue)}</b></td>
                <td>
                  <div className="share-bar"><span style={{ width: `${Math.min(100, (r.revenue / Math.max(t.revenue, 1)) * 100)}%` }} /></div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
