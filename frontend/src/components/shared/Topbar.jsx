import { LogOut } from "lucide-react";

export default function Topbar({ user, onLogout, label }) {
  return (
    <header className="topbar">
      <div className="crumb">
        <span>Commerce OS</span><b>/</b><strong data-testid="topbar-label">{label}</strong>
      </div>
      <div className="top-actions">
        <div className="live"><i />All systems operational</div>
        <div className="profile">
          <div className="profile-avatar">{user.name?.slice(0, 2).toUpperCase()}</div>
          <span><b>{user.name}</b><small>{user.role === "MASTER_ADMIN" ? "Master Admin" : "Owner workspace"}</small></span>
        </div>
        <button className="icon-button" data-testid="logout-button" onClick={onLogout} aria-label="Logout"><LogOut size={16} /></button>
      </div>
    </header>
  );
}
