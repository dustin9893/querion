import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { loadConfig, saveOptions, getSession, setSession, type Config, type Session } from "../lib/storage";

function Options() {
  const [cfg, setCfg] = useState<Config | null>(null);
  const [apiBase, setApiBase] = useState("");
  const [session, setSess] = useState<Session | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => { (async () => { const c = await loadConfig(); setCfg(c); setApiBase(c.apiBase); setSess(await getSession()); })(); }, []);
  if (!cfg) return null;

  const save = async () => {
    await saveOptions({ apiBase: apiBase.trim().replace(/\/+$/, "") });
    setCfg(await loadConfig()); setSaved(true); setTimeout(() => setSaved(false), 1500);
  };

  return (
    <div style={{ padding: 20, maxWidth: 480, color: "#0f172a" }}>
      <p style={{ fontSize: 10, fontWeight: 700, letterSpacing: 1, textTransform: "uppercase", color: "#ee6d1f", margin: 0 }}>{cfg.brandName}</p>
      <h1 style={{ fontSize: 18, margin: "4px 0 16px" }}>Cấu hình extension</h1>

      <label style={{ display: "block", fontSize: 12, fontWeight: 600, marginBottom: 6 }}>Địa chỉ API</label>
      <input value={apiBase} onChange={(e) => setApiBase(e.target.value)} disabled={cfg.managed}
        style={{ width: "100%", boxSizing: "border-box", padding: "8px 10px", borderRadius: 8, border: "1px solid #cbd5e1", fontSize: 13 }} />
      <p style={{ fontSize: 11, color: "#64748b", margin: "6px 0 12px" }}>
        {cfg.managed
          ? "Do bộ phận IT cấu hình qua chính sách Chrome — không sửa được ở đây."
          : "Chỉ dùng khi thử nghiệm. Trên máy của ngân hàng, IT đẩy giá trị này xuống bằng chính sách nên không cần điền."}
      </p>
      {!cfg.managed && (
        <button onClick={save} style={{ padding: "8px 14px", borderRadius: 8, border: 0, background: "#ee6d1f", color: "#fff", fontWeight: 600, cursor: "pointer" }}>
          {saved ? "Đã lưu" : "Lưu"}
        </button>
      )}

      <hr style={{ margin: "20px 0", border: 0, borderTop: "1px solid #e2e8f0" }} />
      <p style={{ fontSize: 12, fontWeight: 600, marginBottom: 6 }}>Phiên đăng nhập</p>
      {session ? (
        <div style={{ fontSize: 13 }}>
          <p style={{ margin: "0 0 8px" }}>{session.employee.name} · {session.employee.employee_code}{session.employee.workspace_name ? ` · ${session.employee.workspace_name}` : ""}</p>
          <button onClick={async () => { await setSession(null); setSess(null); }}
            style={{ padding: "6px 12px", borderRadius: 8, border: "1px solid #cbd5e1", background: "#fff", cursor: "pointer" }}>Đăng xuất trên trình duyệt này</button>
        </div>
      ) : <p style={{ fontSize: 13, color: "#64748b" }}>Chưa đăng nhập — mở bong bóng trên một trang bất kỳ để đăng nhập.</p>}
      {cfg.disabledHosts.length > 0 && (
        <p style={{ fontSize: 11, color: "#64748b", marginTop: 16 }}>Không hiện bong bóng trên: {cfg.disabledHosts.join(", ")}</p>
      )}
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<React.StrictMode><Options /></React.StrictMode>);
