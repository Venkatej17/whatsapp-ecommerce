import { useCallback, useEffect, useState } from "react";
import { Plus, X } from "lucide-react";
import { toast } from "sonner";
import { api } from "../../api";

export default function Templates() {
  const [list, setList] = useState([]);
  const [show, setShow] = useState(false);

  const load = useCallback(() => api.get("/admin/templates").then((r) => setList(r.data)).catch(() => {}), []);
  useEffect(() => { load(); }, [load]);

  const submit = async (e) => {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    try {
      await api.post("/admin/templates", { name: f.get("name"), category: f.get("category"), trigger: f.get("trigger"), body: f.get("body") });
      toast.success("Template added to library");
      setShow(false);
      load();
    } catch (err) { toast.error(err.response?.data?.detail || "Could not save"); }
  };

  return (
    <section className="content">
      <div className="page-heading">
        <div>
          <div className="eyebrow">MESSAGE LIBRARY</div>
          <h1>Templates</h1>
          <p>Reusable WhatsApp templates that every client workspace inherits.</p>
        </div>
        <button className="primary-button" data-testid="new-template-button" onClick={() => setShow(true)}><Plus size={17} /> New template</button>
      </div>
      <div className="template-grid">
        {list.map((t) => (
          <div key={t.id} className="template-card" data-testid={`template-${t.id}`}>
            <div className="template-tag">{t.category}</div>
            <h3>{t.name}</h3>
            <p>{t.body}</p>
            <small>Trigger · <span className="mono">{t.trigger}</span></small>
          </div>
        ))}
      </div>
      {show && (
        <div className="modal-backdrop" onClick={() => setShow(false)}>
          <form className="modal" onSubmit={submit} onClick={(e) => e.stopPropagation()} data-testid="new-template-modal">
            <div className="modal-head">
              <div><h2>Add template</h2><p>Available to every client workspace after applying.</p></div>
              <button type="button" className="icon-button" onClick={() => setShow(false)}><X size={16} /></button>
            </div>
            <label>Name<input name="name" required data-testid="template-name-input" /></label>
            <div className="form-row">
              <label>Category
                <select name="category" defaultValue="order" data-testid="template-category-input">
                  <option value="welcome">welcome</option><option value="order">order</option>
                  <option value="pickup">pickup</option><option value="delivery">delivery</option>
                  <option value="cart">cart</option><option value="support">support</option>
                </select>
              </label>
              <label>Trigger<input name="trigger" defaultValue="manual" data-testid="template-trigger-input" /></label>
            </div>
            <label>Body<textarea name="body" required rows="3" data-testid="template-body-input" /></label>
            <button className="primary-button full" data-testid="save-template-button"><Plus size={17} /> Add to library</button>
          </form>
        </div>
      )}
    </section>
  );
}
