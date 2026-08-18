import { useEffect, useState } from "react";
import { Toaster } from "sonner";
import { api } from "./api";
import Login from "./pages/Login";
import MasterShell from "./pages/master/MasterShell";
import ClientShell from "./pages/client/ClientShell";
import "@/App.css";

export default function App() {
  const [user, setUser] = useState(null);
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    let alive = true;
    api.get("/auth/me")
      .then((r) => { if (alive) setUser(r.data); })
      .catch(() => {})
      .finally(() => { if (alive) setChecking(false); });
    return () => { alive = false; };
  }, []);

  const logout = async () => {
    try { await api.post("/auth/logout"); } catch (_) {}
    setUser(null);
  };

  if (checking) {
    return (
      <div className="loading-screen" data-testid="loading-screen">
        <div className="loading-dot" /> Loading Commerce OS…
      </div>
    );
  }

  return (
    <>
      <Toaster position="top-right" richColors />
      {!user ? (
        <Login onLogin={setUser} />
      ) : user.role === "MASTER_ADMIN" ? (
        <MasterShell user={user} onLogout={logout} />
      ) : (
        <ClientShell user={user} onLogout={logout} />
      )}
    </>
  );
}
