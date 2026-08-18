import { useCallback, useEffect, useState } from "react";
import { Boxes, Package } from "lucide-react";
import { toast } from "sonner";
import { api } from "../../api";
import Status from "../../components/shared/Status";

export default function Inventory({ refresh }) {
  const [list, setList] = useState([]);
  const load = useCallback(() => api.get("/workspace/products").then((r) => setList(r.data)).catch(() => {}), []);
  useEffect(() => { load(); }, [load]);

  const save = async (id, stock) => {
    try {
      await api.patch(`/workspace/products/${id}`, { stock: Number(stock) });
      toast.success("Stock updated");
      load(); refresh && refresh();
    } catch (err) { toast.error(err.response?.data?.detail || "Could not update"); }
  };

  const low = list.filter((p) => p.stock < 20 && p.stock > 0).length;
  const out = list.filter((p) => p.stock === 0).length;

  return (
    <section className="content">
      <div className="page-heading">
        <div>
          <div className="eyebrow">STOCK OPERATIONS</div>
          <h1>Inventory</h1>
          <p>{low} items low · {out} out of stock · Adjust daily to prevent overselling.</p>
        </div>
      </div>
      <div className="panel full-panel">
        <table>
          <thead><tr><th>PRODUCT</th><th>CATEGORY</th><th>UNIT</th><th>CURRENT</th><th>ADJUST</th><th>STATUS</th></tr></thead>
          <tbody>
            {list.map((p) => (
              <tr key={p.id} data-testid={`inventory-row-${p.id}`}>
                <td><div className="product-cell"><div className="product-symbol"><Package size={16} /></div><span><b>{p.name}</b><small>{p.sku}</small></span></div></td>
                <td>{p.category}</td>
                <td>{p.unit}</td>
                <td><b>{p.stock}</b></td>
                <td>
                  <form onSubmit={(e) => { e.preventDefault(); save(p.id, e.currentTarget.stock.value); }} className="inline-form">
                    <input type="number" name="stock" defaultValue={p.stock} data-testid={`stock-input-${p.id}`} />
                    <button className="outline-button" type="submit" data-testid={`save-stock-${p.id}`}><Boxes size={13} /> Save</button>
                  </form>
                </td>
                <td><Status tone={p.stock === 0 ? "red" : p.stock < 20 ? "orange" : "green"}>{p.status}</Status></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
