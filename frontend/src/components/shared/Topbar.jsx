import { useState } from "react";
import { LogOut, X } from "lucide-react";
import { toast } from "sonner";
import { api } from "../../api";

export default function Topbar({ user, onLogout, label, onUserUpdate }) {
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    const f = new FormData(e.target);
    const name = f.get("name")?.trim();
    const currentPassword = f.get("current_password");
    const newPassword = f.get("new_password");
    if (!name && !newPassword) {
      toast.error("Nothing to update");
      return;
    }
    setBusy(true);
    try {
      const payload = {};
      if (name && name !== user.name) payload.name = name;
      if (newPassword) {
        payload.current_password = currentPassword;
        payload.new_password = newPassword;
      }
      if (Object.keys(payload).length === 0) {
        setShow(false);
        return;
      }
      const { data } = await api.patch("/auth/profile", payload);
      onUserUpdate?.((prev) => ({ ...prev, ...data }));
      toast.success("Profile updated");
      setShow(false);
    } catch (err) {
      toast.error(err.response?.data?.detail || "Could not update profile");
    } finally {
      setBusy(false);
    }
  };

  return (
    <header className="topbar">
      <div className="crumb">
        <span>Agent Opscom</span><b>/</b><strong data-testid="topbar-label">{label}</strong>
      </div>
      <div className="top-actions">
        <div className="live"><i />All systems operational</div>
        <button className="profile" data-testid="open-profile-button" onClick={() => setShow(true)} style={{ background: "none", border: "none", cursor: "pointer" }}>
          <div className="profile-avatar">{user.name?.slice(0, 2).toUpperCase()}</div>
          <span><b>{user.name}</b><small>{user.role === "MASTER_ADMIN" ? "Master Admin" : "Owner workspace"}</small></span>
        </button>
        <button className="icon-button" data-testid="logout-button" onClick={onLogout} aria-label="Logout"><LogOut size={16} /></button>
      </div>
      {show && (
        <div className="modal-backdrop" onClick={() => setShow(false)}>
          <form className="modal" onSubmit={submit} onClick={(e) => e.stopPropagation()} data-testid="profile-modal">
            <div className="modal-head">
              <div><h2>Edit profile</h2><p>Update your display name or password.</p></div>
              <button type="button" className="icon-button" data-testid="close-profile-modal" onClick={() => setShow(false)}><X size={16} /></button>
            </div>
            <label>Display name<input name="name" defaultValue={user.name} data-testid="profile-name-input" /></label>
            <label>Current password<input name="current_password" type="password" placeholder="Only needed if changing password" data-testid="profile-current-password-input" /></label>
            <label>New password<input name="new_password" type="password" placeholder="Leave blank to keep current password" data-testid="profile-new-password-input" /></label>
            <button className="primary-button full" disabled={busy} data-testid="save-profile-button">{busy ? "Saving…" : "Save changes"}</button>
          </form>
        </div>
      )}
    </header>
  );
}
