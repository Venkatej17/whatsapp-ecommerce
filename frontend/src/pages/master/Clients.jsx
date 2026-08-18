import { useCallback, useEffect, useState } from "react";
import { BookOpen, CheckCircle2, ChevronRight, Circle, Copy, Filter, KeyRound, MessageCircle, Package, Plus, Search, Send, ShieldCheck, Sparkles, X } from "lucide-react";
import { toast } from "sonner";
import { api } from "../../api";
import Status from "../../components/shared/Status";

const STEPS = [
  ["business_created", "Business created"],
  ["owner_login_created", "Owner login created"],
  ["whatsapp_connected", "WhatsApp connected"],
  ["catalog_connected", "Catalog connected"],
  ["templates_configured", "Templates configured"],
  ["automations_configured", "Automations configured"],
  ["payment_configured", "Payment configured"],
  ["fulfilment_configured", "Fulfilment configured"],
  ["test_order_completed", "Test order completed"],
  ["ready_to_go_live", "Ready to go live"],
];

export default function Clients({ onChange }) {
  const [tenants, setTenants] = useState([]);
  const [search, setSearch] = useState("");
  const [wizard, setWizard] = useState(false);
  const [selected, setSelected] = useState(null);

  const load = useCallback(async () => {
    const { data } = await api.get("/admin/tenants");
    setTenants(data);
  }, []);

  useEffect(() => { load().catch(() => toast.error("Could not load clients")); }, [load]);

  const list = tenants.filter((t) => t.name.toLowerCase().includes(search.toLowerCase()));

  return (
    <section className="content">
      <div className="page-heading">
        <div>
          <div className="eyebrow">CLIENT LIFECYCLE</div>
          <h1>Client workspaces</h1>
          <p>Create and configure businesses without entering their operational data.</p>
        </div>
        <button className="primary-button" data-testid="create-client-button" onClick={() => setWizard(true)}>
          <Plus size={17} /> Create new client
        </button>
      </div>
      <div className="toolbar">
        <div className="search">
          <Search size={17} />
          <input data-testid="client-search-input" placeholder="Search clients" value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
        <button className="secondary-button" data-testid="client-filter-button"><Filter size={16} /> Filter</button>
      </div>
      <div className="panel full-panel">
        <table>
          <thead><tr><th>CLIENT WORKSPACE</th><th>TYPE</th><th>OWNER ACCESS</th><th>READINESS</th><th>STATUS</th><th>ACTION</th></tr></thead>
          <tbody>
            {list.map((t) => (
              <tr key={t.id} data-testid={`client-row-${t.id}`}>
                <td>
                  <div className="product-cell">
                    <div className="tenant-avatar">{t.name.slice(0, 1)}</div>
                    <span><b>{t.name}</b><small>{t.id}</small></span>
                  </div>
                </td>
                <td>{t.category}</td>
                <td><span className="owner-access"><KeyRound size={13} /> One owner login</span></td>
                <td><b>{t.onboarding_progress}%</b></td>
                <td><Status tone={t.status === "Active" ? "green" : t.status === "Suspended" ? "red" : "orange"}>{t.status}</Status></td>
                <td><button className="row-action" data-testid={`open-client-config-${t.id}`} onClick={() => setSelected(t.id)}>Open setup</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {wizard && <CreateWizard onClose={() => setWizard(false)} onCreated={() => { setWizard(false); load(); onChange && onChange(); toast.success("Client workspace created"); }} />}
      {selected && <ConfigDrawer tenantId={selected} onClose={() => setSelected(null)} onSaved={() => { load(); onChange && onChange(); }} />}
    </section>
  );
}

function CreateWizard({ onClose, onCreated }) {
  const [step, setStep] = useState(1);
  const [busy, setBusy] = useState(false);
  const [packs, setPacks] = useState([]);
  const [chosenPack, setChosenPack] = useState("");
  const [f, setF] = useState({
    business_name: "", category: "Grocery", description: "", phone: "", email: "",
    city: "", state: "", pincode: "", currency: "INR", timezone: "Asia/Kolkata",
    owner_name: "", owner_email: "", owner_password: "Owner123!",
  });
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  useEffect(() => { api.get("/admin/template-packs").then((r) => setPacks(r.data)).catch(() => {}); }, []);

  const canNext = step === 1 ? f.business_name && f.category && f.email : step === 2 ? f.owner_name && f.owner_email : true;

  const submit = async () => {
    setBusy(true);
    try {
      const { data } = await api.post("/admin/tenants", f);
      if (chosenPack) {
        try { await api.post(`/admin/tenants/${data.tenant_id}/apply-pack`, { pack: chosenPack }); }
        catch (e) { toast.error("Client created but pack failed to apply"); }
      }
      onCreated();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Could not create client");
    } finally { setBusy(false); }
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal wide" onClick={(e) => e.stopPropagation()} data-testid="create-client-wizard">
        <div className="modal-head">
          <div>
            <div className="eyebrow">STEP {step} OF 3</div>
            <h2>{step === 1 ? "Business information" : step === 2 ? "Client owner login" : "Industry template pack"}</h2>
            <p>{step === 1 ? "Create the tenant workspace." : step === 2 ? "One owner login opens only this workspace." : "Seed products, categories, welcome message and fulfilment defaults."}</p>
          </div>
          <button type="button" className="icon-button" onClick={onClose} data-testid="wizard-close"><X size={16} /></button>
        </div>
        {step === 1 ? (
          <div>
            <div className="form-row">
              <label>Business name <input value={f.business_name} onChange={set("business_name")} data-testid="wizard-business-name" required /></label>
              <label>Category
                <select value={f.category} onChange={set("category")} data-testid="wizard-business-category">
                  <option>Grocery</option><option>Pharmacy</option><option>Beauty</option><option>Bakery</option><option>Fashion</option><option>Electronics</option><option>Retail</option><option>Specialty</option>
                </select>
              </label>
            </div>
            <label>Description <input value={f.description} onChange={set("description")} data-testid="wizard-business-desc" /></label>
            <div className="form-row">
              <label>Business email <input type="email" value={f.email} onChange={set("email")} data-testid="wizard-business-email" required /></label>
              <label>Phone <input value={f.phone} onChange={set("phone")} data-testid="wizard-business-phone" /></label>
            </div>
            <div className="form-row">
              <label>City <input value={f.city} onChange={set("city")} data-testid="wizard-city" /></label>
              <label>State <input value={f.state} onChange={set("state")} data-testid="wizard-state" /></label>
              <label>Pincode <input value={f.pincode} onChange={set("pincode")} data-testid="wizard-pincode" /></label>
            </div>
          </div>
        ) : step === 2 ? (
          <div>
            <label>Owner name <input value={f.owner_name} onChange={set("owner_name")} data-testid="wizard-owner-name" required /></label>
            <div className="form-row">
              <label>Owner email <input type="email" value={f.owner_email} onChange={set("owner_email")} data-testid="wizard-owner-email" required /></label>
              <label>Temporary password <input value={f.owner_password} onChange={set("owner_password")} data-testid="wizard-owner-password" /></label>
            </div>
            <div className="feature-placeholder"><ShieldCheck size={16} /> One owner login is created. It only unlocks this workspace.</div>
          </div>
        ) : (
          <div className="pack-grid" data-testid="wizard-pack-grid">
            <button type="button" className={`pack-card ${chosenPack === "" ? "active" : ""}`} onClick={() => setChosenPack("")} data-testid="pack-none">
              <div className="pack-icon"><Package size={18} /></div>
              <b>Empty workspace</b><small>Start blank. Add products manually later.</small>
            </button>
            {packs.map((p) => (
              <button type="button" key={p.name} className={`pack-card ${chosenPack === p.name ? "active" : ""}`} onClick={() => setChosenPack(p.name)} data-testid={`pack-${p.name}`}>
                <div className="pack-icon"><Sparkles size={18} /></div>
                <b>{p.name} pack</b>
                <small>{p.products} sample products · {p.categories.slice(0, 3).join(", ")}…</small>
              </button>
            ))}
          </div>
        )}
        <div className="wizard-footer">
          {step > 1 && <button className="secondary-button" onClick={() => setStep(step - 1)} data-testid="wizard-back">Back</button>}
          {step < 3 ? (
            <button className="primary-button" disabled={!canNext} onClick={() => setStep(step + 1)} data-testid="wizard-next">Continue <ChevronRight size={16} /></button>
          ) : (
            <button className="primary-button" disabled={busy} onClick={submit} data-testid="wizard-create">{busy ? "Creating…" : chosenPack ? `Create with ${chosenPack} pack` : "Create client workspace"}</button>
          )}
        </div>
      </div>
    </div>
  );
}

function ConfigDrawer({ tenantId, onClose, onSaved }) {
  const [tenant, setTenant] = useState(null);
  const [busy, setBusy] = useState("");
  const [showWaModal, setShowWaModal] = useState(false);
  const [showDoc, setShowDoc] = useState(false);

  const load = useCallback(() => {
    api.get(`/admin/tenants/${tenantId}`).then((r) => setTenant(r.data)).catch(() => toast.error("Could not load client"));
  }, [tenantId]);

  useEffect(() => { load(); }, [load]);

  const call = async (key, url, body = {}, msg) => {
    setBusy(key);
    try { await api.post(url, body); toast.success(msg); load(); onSaved && onSaved(); }
    catch (err) { toast.error(err.response?.data?.detail || "Could not save"); }
    finally { setBusy(""); }
  };

  if (!tenant) return <div className="modal-backdrop" onClick={onClose}><div className="modal">Loading…</div></div>;
  const onb = tenant.onboarding || {};
  const wa = tenant.integrations?.whatsapp || {};
  const cat = tenant.integrations?.catalog || {};
  const pay = tenant.integrations?.payment || {};
  const ful = tenant.fulfilment || {};

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="drawer" onClick={(e) => e.stopPropagation()} data-testid="config-drawer">
        <div className="drawer-head">
          <div>
            <div className="eyebrow">CLIENT SETUP</div>
            <h2>{tenant.name}</h2>
            <p>{tenant.category} · {tenant.business?.city} · Owner: {tenant.owner?.email}</p>
          </div>
          <button className="icon-button" onClick={onClose} data-testid="drawer-close"><X size={16} /></button>
        </div>
        <div className="drawer-body">
          <div className="checklist-block">
            <b>Onboarding checklist</b>
            <div className="checklist-grid">
              {STEPS.map(([k, label]) => (
                <div key={k} className={`checklist-line ${onb[k] ? "done" : ""}`} data-testid={`onboarding-${k}`}>
                  {onb[k] ? <CheckCircle2 size={15} color="#25a65a" /> : <Circle size={15} color="#94a3b8" />}
                  <b>{label}</b><small>{onb[k] ? "Configured" : "Pending"}</small>
                </div>
              ))}
            </div>
          </div>

          <ConfigSection title="WhatsApp / Meta"
            status={wa.connected ? "Connected" : "Not connected"}
            statusTone={wa.connected ? "green" : "orange"}
            detail={wa.connected ? `${wa.phone_number_id || wa.phone_number} · ${wa.provider}` : "Save real Meta Cloud API credentials"}
            actionLabel={wa.connected ? "Update credentials" : "Connect WhatsApp"}
            testId="config-whatsapp"
            busy={busy === "wa"}
            onAction={() => setShowWaModal(true)}
          />
          <ConfigSection title="Catalog"
            status={cat.connected ? "Synced" : "Not connected"}
            statusTone={cat.connected ? "green" : "orange"}
            detail={cat.connected ? `Source: ${cat.source}` : "Connect an internal or external catalog"}
            actionLabel={cat.connected ? "Resync" : "Connect catalog"}
            testId="config-catalog"
            busy={busy === "cat"}
            onAction={() => call("cat", `/admin/tenants/${tenantId}/catalog`, { source: "Internal" }, "Catalog connected")}
          />
          <ConfigSection title="Templates"
            status={onb.templates_configured ? "Applied" : "Not applied"}
            statusTone={onb.templates_configured ? "green" : "orange"}
            detail="Reusable WhatsApp templates for orders, pickup, delivery, cart."
            actionLabel="Apply default templates"
            testId="config-templates"
            busy={busy === "tpl"}
            onAction={() => call("tpl", `/admin/tenants/${tenantId}/templates/apply`, {}, "Templates applied")}
          />
          <ConfigSection title="Automations"
            status={onb.automations_configured ? "Active" : "Not active"}
            statusTone={onb.automations_configured ? "green" : "orange"}
            detail="Event-driven WhatsApp notifications for order status transitions."
            actionLabel="Enable default automations"
            testId="config-automations"
            busy={busy === "aut"}
            onAction={() => call("aut", `/admin/tenants/${tenantId}/automations/apply`, {}, "Automations enabled")}
          />
          <ConfigSection title="Payment"
            status={pay.configured ? "Configured" : "Not configured"}
            statusTone={pay.configured ? "green" : "orange"}
            detail={pay.configured ? `${pay.provider} · ${pay.mode || "test"}` : "Enable online / COD / UPI"}
            actionLabel={pay.configured ? "Update" : "Configure payment"}
            testId="config-payment"
            busy={busy === "pay"}
            onAction={() => call("pay", `/admin/tenants/${tenantId}/payment`, {}, "Payment configured")}
          />
          <ConfigSection title="Fulfilment (delivery + pickup)"
            status={onb.fulfilment_configured ? "Configured" : "Not configured"}
            statusTone={onb.fulfilment_configured ? "green" : "orange"}
            detail={`Delivery ₹${ful.home_delivery?.base_charge ?? 0} · Pickup ${ful.store_pickup?.location?.name || "no store"}`}
            actionLabel="Apply default fulfilment"
            testId="config-fulfilment"
            busy={busy === "ful"}
            onAction={() => call("ful", `/admin/tenants/${tenantId}/fulfilment`, { delivery_enabled: true, delivery_charge: 20, delivery_free_above: 500, pickup_enabled: true, pickup_location_name: `${tenant.name} Main Store`, pickup_address: `${tenant.business?.city || "City"}` }, "Fulfilment configured")}
          />

          <WhatsAppSimulator tenantId={tenantId} tenantName={tenant.name} />

          <div className="drawer-actions">
            <button className="secondary-button" data-testid="view-onboarding-doc" onClick={() => setShowDoc(true)}><BookOpen size={14} /> Onboarding playbook</button>
            {tenant.status === "Active" ? (
              <button className="secondary-button" data-testid="deactivate-client" onClick={() => call("act", `/admin/tenants/${tenantId}/deactivate`, {}, "Client suspended")}>Suspend workspace</button>
            ) : (
              <button className="primary-button" data-testid="activate-client" disabled={busy === "act"} onClick={() => call("act", `/admin/tenants/${tenantId}/activate`, {}, "Client activated")}>Activate workspace</button>
            )}
          </div>
        </div>
      </div>
      {showWaModal && <MetaCredsModal tenantId={tenantId} existing={wa} onClose={() => setShowWaModal(false)} onSaved={() => { setShowWaModal(false); load(); onSaved && onSaved(); toast.success("WhatsApp credentials saved"); }} />}
      {showDoc && <OnboardingDocModal tenantId={tenantId} onClose={() => setShowDoc(false)} />}
    </div>
  );
}

function ConfigSection({ title, status, statusTone, detail, actionLabel, testId, busy, onAction }) {
  return (
    <div className="config-section" data-testid={testId}>
      <div>
        <div className="config-head">
          <b>{title}</b>
          <Status tone={statusTone}>{status}</Status>
        </div>
        <small>{detail}</small>
      </div>
      <button className="outline-button" disabled={busy} onClick={onAction} data-testid={`${testId}-action`}>
        {busy ? "Saving…" : actionLabel}
      </button>
    </div>
  );
}

function WhatsAppSimulator({ tenantId, tenantName }) {
  const [phone, setPhone] = useState("+919000012345");
  const [name, setName] = useState("Test Customer");
  const [msg, setMsg] = useState("hi");
  const [thread, setThread] = useState([]);
  const [busy, setBusy] = useState(false);

  const send = async () => {
    if (!msg.trim()) return;
    setBusy(true);
    const outbound = msg;
    setThread((t) => [...t, { from: "customer", body: outbound }]);
    setMsg("");
    try {
      const { data } = await api.post("/admin/whatsapp/simulate", { tenant_id: tenantId, from_phone: phone, from_name: name, body: outbound });
      setThread((t) => [...t, { from: "bot", body: data.reply }]);
    } catch (err) {
      toast.error(err.response?.data?.detail || "Simulator failed");
    } finally { setBusy(false); }
  };

  const quick = ["hi", "shop", `add FM-TOM-01`, "cart", "pickup", "confirm"];

  return (
    <div className="config-section simulator" data-testid="whatsapp-simulator">
      <div style={{ width: "100%" }}>
        <div className="config-head">
          <b><MessageCircle size={14} style={{ verticalAlign: "text-bottom" }} /> WhatsApp simulator</b>
          <Status tone="blue">SCAFFOLD</Status>
        </div>
        <small>Send test messages as a customer. Real webhook works when Meta credentials are saved.</small>
        <div className="sim-controls">
          <input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="Customer phone" data-testid="sim-phone" />
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Customer name" data-testid="sim-name" />
        </div>
        <div className="sim-thread" data-testid="sim-thread">
          {thread.length === 0 && <div className="empty-inline">Type a message below to start.</div>}
          {thread.map((m, i) => (
            <div key={i} className={`conv-bubble ${m.from}`}>{m.body}</div>
          ))}
        </div>
        <div className="sim-quick">
          {quick.map((q) => (
            <button key={q} type="button" onClick={() => setMsg(q)} data-testid={`sim-quick-${q.replaceAll(" ", "-")}`}>{q}</button>
          ))}
        </div>
        <div className="inline-form">
          <input value={msg} onChange={(e) => setMsg(e.target.value)} onKeyDown={(e) => e.key === "Enter" && send()} placeholder={`Message ${tenantName} as customer`} data-testid="sim-input" />
          <button className="primary-button" disabled={busy || !msg.trim()} onClick={send} data-testid="sim-send"><Send size={14} /> Send</button>
        </div>
      </div>
    </div>
  );
}


function MetaCredsModal({ tenantId, existing = {}, onClose, onSaved }) {
  const [phoneId, setPhoneId] = useState(existing.phone_number_id || "");
  const [wabaId, setWabaId] = useState(existing.waba_id || "");
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState(false);

  const save = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.post(`/admin/tenants/${tenantId}/whatsapp-creds`, { phone_number_id: phoneId, waba_id: wabaId, access_token: token });
      onSaved();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Could not save");
    } finally { setBusy(false); }
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <form className="modal" onSubmit={save} onClick={(e) => e.stopPropagation()} data-testid="meta-creds-modal">
        <div className="modal-head">
          <div>
            <div className="eyebrow">META CLOUD API</div>
            <h2>WhatsApp credentials</h2>
            <p>These are stored encrypted per tenant. Access token is never returned to the browser after saving.</p>
          </div>
          <button type="button" className="icon-button" onClick={onClose} data-testid="meta-creds-close"><X size={16} /></button>
        </div>
        <label>Phone number ID<input value={phoneId} onChange={(e) => setPhoneId(e.target.value)} required data-testid="meta-phone-id" placeholder="e.g. 108023...4567" /></label>
        <label>WhatsApp Business Account ID<input value={wabaId} onChange={(e) => setWabaId(e.target.value)} data-testid="meta-waba-id" placeholder="Optional" /></label>
        <label>Permanent access token<input value={token} onChange={(e) => setToken(e.target.value)} required data-testid="meta-token" type="password" placeholder="EAAG…" /></label>
        <div className="feature-placeholder"><ShieldCheck size={16} /> Test with a Meta test number first. Real customers work after the number is verified in WhatsApp Manager.</div>
        <button className="primary-button full" disabled={busy || !phoneId || !token} data-testid="meta-save">{busy ? "Saving…" : "Save credentials"}</button>
      </form>
    </div>
  );
}

function OnboardingDocModal({ tenantId, onClose }) {
  const [doc, setDoc] = useState(null);
  useEffect(() => { api.get(`/admin/tenants/${tenantId}/onboarding-doc`).then((r) => setDoc(r.data)).catch(() => toast.error("Could not load doc")); }, [tenantId]);

  const copy = () => {
    navigator.clipboard.writeText(doc?.markdown || "");
    toast.success("Playbook copied to clipboard");
  };

  const download = () => {
    const blob = new Blob([doc?.markdown || ""], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = `${doc?.tenant_name || "onboarding"}-playbook.md`;
    a.click(); URL.revokeObjectURL(url);
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="drawer" onClick={(e) => e.stopPropagation()} data-testid="onboarding-doc-modal">
        <div className="drawer-head">
          <div>
            <div className="eyebrow">CLIENT HANDOVER</div>
            <h2>Onboarding playbook</h2>
            <p>Auto-generated welcome document you can send to {doc?.tenant_name || "your client"}.</p>
          </div>
          <button className="icon-button" onClick={onClose} data-testid="onboarding-doc-close"><X size={16} /></button>
        </div>
        <div className="drawer-body">
          <pre className="playbook" data-testid="onboarding-doc-body">{doc?.markdown || "Generating…"}</pre>
          <div className="drawer-actions">
            <button className="secondary-button" onClick={copy} data-testid="onboarding-doc-copy"><Copy size={14} /> Copy markdown</button>
            <button className="primary-button" onClick={download} data-testid="onboarding-doc-download">Download .md</button>
          </div>
        </div>
      </div>
    </div>
  );
}
