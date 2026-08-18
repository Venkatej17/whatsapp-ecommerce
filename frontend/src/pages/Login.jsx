import { useState } from "react";
import { ChevronRight, KeyRound, ShieldCheck, Zap } from "lucide-react";
import { toast } from "sonner";
import { api } from "../api";

export default function Login({ onLogin }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const { data } = await api.post("/auth/login", { email, password });
      onLogin(data);
    } catch (err) {
      toast.error(err.response?.data?.detail || "Email or password is incorrect");
    } finally {
      setBusy(false);
    }
  };

  const fill = (e, p) => { setEmail(e); setPassword(p); };

  return (
    <div className="auth-shell">
      <aside className="auth-art">
        <div className="auth-brand">
          <span><Zap size={18} fill="currentColor" /></span>
          <b>commerce<span>OS</span></b>
        </div>
        <div className="auth-message">
          <div className="eyebrow"><span className="pulse" /> CONTROL PLANE + WORKSPACES</div>
          <h1>One operating system.<br /><em>Every client in control.</em></h1>
          <p>Configure the commerce engine centrally, then let each business run its day from one focused workspace.</p>
          <div className="auth-demo" data-testid="auth-demo-hints">
            <button type="button" onClick={() => fill("admin@commerceos.com", "Admin123!")}>Try Master Admin →</button>
            <button type="button" onClick={() => fill("owner@freshmart.com", "Owner123!")}>Try Fresh Mart owner →</button>
          </div>
        </div>
        <div className="auth-art-footer"><ShieldCheck size={16} /> Secure role-based access for your platform</div>
      </aside>
      <main className="auth-card">
        <div className="mobile-auth-brand"><Zap size={18} /> commerce<span>OS</span></div>
        <div className="auth-kicker">WELCOME BACK</div>
        <h2>Sign in to Commerce OS</h2>
        <p>Use your platform or client owner credentials to continue.</p>
        <form onSubmit={submit} data-testid="login-form">
          <label>Email address
            <input data-testid="login-email-input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@business.com" required />
          </label>
          <label>Password
            <input data-testid="login-password-input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Enter your password" required />
          </label>
          <button className="primary-button full" data-testid="login-submit-button" disabled={busy}>
            {busy ? "Signing in…" : "Sign in"}<ChevronRight size={16} />
          </button>
        </form>
        <div className="auth-note"><KeyRound size={15} /><span>One client owner login opens only that client's workspace.</span></div>
      </main>
    </div>
  );
}
