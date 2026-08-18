import { useEffect, useState } from "react";
import { MessageCircle } from "lucide-react";
import { api } from "../../api";

export default function Conversations() {
  const [list, setList] = useState([]);
  const [active, setActive] = useState(null);
  useEffect(() => {
    api.get("/workspace/conversations").then((r) => {
      setList(r.data);
      if (r.data[0]) setActive(r.data[0]);
    }).catch(() => {});
  }, []);

  return (
    <section className="content">
      <div className="page-heading">
        <div>
          <div className="eyebrow">WHATSAPP THREADS</div>
          <h1>Conversations</h1>
          <p>Every thread is linked to its order — no more scrolling through chats.</p>
        </div>
      </div>
      <div className="conv-grid">
        <div className="conv-list panel">
          {list.map((c) => (
            <button key={c.id} className={`conv-list-item ${active?.id === c.id ? "active" : ""}`} onClick={() => setActive(c)} data-testid={`conv-${c.id}`}>
              <div className="product-symbol"><MessageCircle size={14} /></div>
              <div><b>{c.customer}</b><small>{c.phone} · Order {c.linked_order_id}</small></div>
              <small className="conv-time">{c.last_at}</small>
            </button>
          ))}
          {list.length === 0 && <div className="empty-inline">No conversations yet.</div>}
        </div>
        <div className="conv-thread panel">
          {active ? (
            <>
              <div className="conv-thread-head">
                <div><b>{active.customer}</b><small>{active.phone}</small></div>
                <span className="mono">Order · {active.linked_order_id}</span>
              </div>
              <div className="conv-messages" data-testid="conv-messages">
                {active.messages.map((m, i) => (
                  <div key={i} className={`conv-bubble ${m.from}`}>{m.body}<small>{m.at}</small></div>
                ))}
              </div>
            </>
          ) : <div className="empty-inline">Pick a conversation.</div>}
        </div>
      </div>
    </section>
  );
}
