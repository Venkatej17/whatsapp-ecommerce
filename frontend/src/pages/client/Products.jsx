import { useCallback, useEffect, useState } from "react";
import { Filter, Package, Plus, Search, X } from "lucide-react";
import { toast } from "sonner";
import { api, money } from "../../api";
import Status from "../../components/shared/Status";

export default function Products({ refresh }) {
  const [list, setList] = useState([]);
  const [search, setSearch] = useState("");
  const [show, setShow] = useState(false);
  const [editing, setEditing] = useState(null);

  const load = useCallback(() => api.get("/workspace/products").then((r) => setList(r.data)).catch(() => toast.error("Could not load products")), []);
  useEffect(() => { load(); }, [load]);

  const submit = async (e) => {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const payload = { name: f.get("name"), category: f.get("category"), price: Number(f.get("price")), stock: Number(f.get("stock")), sku: f.get("sku"), unit: f.get("unit"), description: f.get("description"), is_offer: f.get("is_offer") === "on", offer_text: f.get("offer_text") || "", image_url: f.get("image_url") || "" };
    try {
      if (editing) {
        await api.patch(`/workspace/products/${editing.id}`, payload);
        toast.success("Product updated");
      } else {
        await api.post("/workspace/products", payload);
        toast.success("Product added");
      }
      setShow(false); setEditing(null); load(); refresh && refresh();
    } catch (err) { toast.error(err.response?.data?.detail || "Could not save"); }
  };

  const del = async (id) => {
    if (!window.confirm("Delete this product?")) return;
    try { await api.delete(`/workspace/products/${id}`); toast.success("Product deleted"); load(); refresh && refresh(); }
    catch (err) { toast.error(err.response?.data?.detail || "Could not delete"); }
  };

  const filtered = list.filter((p) => JSON.stringify(p).toLowerCase().includes(search.toLowerCase()));

  return (
    <section className="content">
      <div className="page-heading">
        <div>
          <div className="eyebrow">CATALOG OPERATIONS</div>
          <h1>Products</h1>
          <p>Keep the catalog fresh — every change is scoped to this workspace.</p>
        </div>
        <button className="primary-button" data-testid="new-product-button" onClick={() => { setEditing(null); setShow(true); }}><Plus size={17} /> New product</button>
      </div>
      <div className="toolbar">
        <div className="search"><Search size={17} /><input data-testid="catalog-search-input" placeholder="Search products or SKU" value={search} onChange={(e) => setSearch(e.target.value)} /></div>
        <button className="secondary-button" data-testid="catalog-filter-button"><Filter size={16} /> Filter</button>
      </div>
      <div className="panel full-panel">
        <table>
          <thead><tr><th>PRODUCT</th><th>CATEGORY</th><th>PRICE</th><th>STOCK</th><th>STATUS</th><th>ACTION</th></tr></thead>
          <tbody>
            {filtered.map((p) => (
              <tr key={p.id} data-testid={`product-row-${p.id}`}>
                <td><div className="product-cell">{p.image_url ? <img src={p.image_url} alt={p.name} className="product-thumb" width={32} height={32} style={{ borderRadius: 6, objectFit: "cover" }} /> : <div className="product-symbol"><Package size={16} /></div>}<span><b>{p.name} {p.is_offer && <span className="chip-offer" data-testid={`offer-chip-${p.id}`}>OFFER</span>}</b><small>{p.sku} · {p.unit}{p.is_offer && p.offer_text ? ` · ${p.offer_text}` : ""}</small></span></div></td>
                <td>{p.category}</td>
                <td><b>{money(p.price)}</b></td>
                <td><b>{p.stock}</b> <small style={{ display: "inline" }}>units</small></td>
                <td><Status tone={p.stock === 0 ? "red" : p.stock < 20 ? "orange" : "green"}>{p.status}</Status></td>
                <td>
                  <button className="row-action" data-testid={`edit-product-${p.id}`} onClick={() => { setEditing(p); setShow(true); }}>Edit</button>
                  <button className="row-action danger" data-testid={`delete-product-${p.id}`} onClick={() => del(p.id)}>Delete</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {show && (
        <div className="modal-backdrop" onClick={() => { setShow(false); setEditing(null); }}>
          <form className="modal" onSubmit={submit} onClick={(e) => e.stopPropagation()} data-testid="add-product-modal">
            <div className="modal-head">
              <div><h2>{editing ? "Edit product" : "Add product"}</h2><p>Only visible inside your workspace.</p></div>
              <button type="button" className="icon-button" data-testid="close-product-modal" onClick={() => { setShow(false); setEditing(null); }}><X size={16} /></button>
            </div>
            <label>Product name<input name="name" required defaultValue={editing?.name} data-testid="product-name-input" /></label>
            <div className="form-row">
              <label>Category<input name="category" required defaultValue={editing?.category} data-testid="product-category-input" /></label>
              <label>SKU<input name="sku" defaultValue={editing?.sku} data-testid="product-sku-input" /></label>
            </div>
            <div className="form-row">
              <label>Price<input name="price" type="number" step="0.01" required defaultValue={editing?.price} data-testid="product-price-input" /></label>
              <label>Stock<input name="stock" type="number" required defaultValue={editing?.stock ?? 0} data-testid="product-stock-input" /></label>
              <label>Unit<input name="unit" defaultValue={editing?.unit ?? "each"} data-testid="product-unit-input" /></label>
            </div>
            <label>Description<input name="description" defaultValue={editing?.description} data-testid="product-desc-input" /></label>
            <label>Photo URL<input name="image_url" placeholder="https://... (paste a Cloudinary/image link)" defaultValue={editing?.image_url} data-testid="product-image-input" /></label>
            {(editing?.image_url) && <img src={editing.image_url} alt="preview" style={{ width: 64, height: 64, objectFit: "cover", borderRadius: 8, marginBottom: 8 }} />}
            <div className="offer-row">
              <label className="offer-toggle"><input type="checkbox" name="is_offer" defaultChecked={editing?.is_offer} data-testid="product-offer-input" /> Feature as today's offer</label>
              <input name="offer_text" defaultValue={editing?.offer_text || ""} placeholder="e.g. 20% off — season special" data-testid="product-offer-text" />
            </div>
            <button className="primary-button full" data-testid="save-product-button"><Plus size={17} /> {editing ? "Save changes" : "Add to catalog"}</button>
          </form>
        </div>
      )}
    </section>
  );
}
