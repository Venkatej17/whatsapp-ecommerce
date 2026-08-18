import { useEffect, useState } from "react";
import { Search, Users } from "lucide-react";
import { api, money } from "../../api";
import Status from "../../components/shared/Status";

export default function Customers() {
  const [list, setList] = useState([]);
  const [search, setSearch] = useState("");
  useEffect(() => { api.get("/workspace/customers").then((r) => setList(r.data)).catch(() => {}); }, []);
  const filtered = list.filter((c) => JSON.stringify(c).toLowerCase().includes(search.toLowerCase()));

  return (
    <section className="content">
      <div className="page-heading">
        <div>
          <div className="eyebrow">CUSTOMER CRM</div>
          <h1>Customers</h1>
          <p>Every WhatsApp buyer becomes a record — scoped to your workspace only.</p>
        </div>
      </div>
      <div className="toolbar">
        <div className="search"><Search size={17} /><input data-testid="customer-search-input" placeholder="Search customer or phone" value={search} onChange={(e) => setSearch(e.target.value)} /></div>
      </div>
      <div className="panel full-panel">
        <table>
          <thead><tr><th>CUSTOMER</th><th>PHONE</th><th>ORDERS</th><th>SPEND</th><th>POINTS</th><th>TAGS</th><th>LAST ORDER</th></tr></thead>
          <tbody>
            {filtered.map((c) => (
              <tr key={c.id} data-testid={`customer-row-${c.id}`}>
                <td><div className="product-cell"><div className="product-symbol"><Users size={14} /></div><span><b>{c.name}</b><small>{c.id}</small></span></div></td>
                <td>{c.phone}</td>
                <td><b>{c.orders_count}</b></td>
                <td><b>{money(c.total_spent)}</b></td>
                <td><b className="loyalty-pts">{c.loyalty_points || 0}</b> <small>pts</small></td>
                <td>{(c.tags || []).map((t) => <Status key={t} tone={t === "vip" ? "blue" : t === "new" ? "orange" : "green"}>{t}</Status>)}</td>
                <td><small>{c.last_order_at}</small></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
