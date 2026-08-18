import { useCallback, useEffect, useState } from "react";
import { Bell, RefreshCw, ShoppingCart } from "lucide-react";
import { toast } from "sonner";
import { api } from "../../api";
import Status from "../../components/shared/Status";

export default function AbandonedCarts() {
  const [list, setList] = useState([]);
  const [scanning, setScanning] = useState(false);

  const load = useCallback(() => api.get("/admin/carts/abandoned").then((r) => setList(r.data)).catch(() => toast.error("Could not load abandoned carts")), []);
  useEffect(() => { load(); }, [load]);

  const scan = async () => {
    setScanning(true);
    try {
      const { data } = await api.post("/admin/carts/abandoned/scan");
      toast.success(`Nudged ${data.nudged} of ${data.scanned} idle carts`);
      load();
    } catch (err) { toast.error("Scan failed"); }
    finally { setScanning(false); }
  };

  return (
    <section className="content">
      <div className="page-heading">
        <div>
          <div className="eyebrow">CART RECOVERY</div>
          <h1>Abandoned carts</h1>
          <p>Idle WhatsApp carts older than the configured threshold. Nudges are sent as real WhatsApp messages when Meta creds are configured.</p>
        </div>
        <button className="primary-button" disabled={scanning} onClick={scan} data-testid="scan-abandoned-button">
          <RefreshCw size={16} /> {scanning ? "Scanning…" : "Run recovery scan"}
        </button>
      </div>
      <div className="panel full-panel">
        <table>
          <thead><tr><th>CART</th><th>TENANT</th><th>CUSTOMER</th><th>ITEMS</th><th>IDLE SINCE</th><th>NUDGED</th></tr></thead>
          <tbody>
            {list.length === 0 && (
              <tr><td colSpan="6" style={{ padding: 40, textAlign: "center", color: "#64748b" }}>
                <ShoppingCart size={20} style={{ opacity: 0.4, marginBottom: 8 }} /><br />
                No abandoned carts — everything active.
              </td></tr>
            )}
            {list.map((c) => (
              <tr key={c.id} data-testid={`abandoned-row-${c.id}`}>
                <td><b className="mono">{c.id}</b></td>
                <td>{c.tenant}</td>
                <td><b>{c.customer}</b><small>{c.phone}</small></td>
                <td><b>{c.items}</b></td>
                <td><small>{c.updated_at}</small></td>
                <td>{c.nudged_at ? <Status tone="green"><Bell size={11} /> Nudged</Status> : <Status tone="orange">Pending</Status>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
