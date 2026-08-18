export default function Metric({ label, value, detail, icon: Icon, tone = "green" }) {
  const testid = `metric-${label.toLowerCase().replaceAll(" ", "-").replace("'", "")}`;
  return (
    <div className="metric" data-testid={testid}>
      <div className={`metric-icon ${tone}`}><Icon size={18} /></div>
      <div>
        <p>{label}</p>
        <strong>{value ?? "—"}</strong>
        <small>{detail}</small>
      </div>
    </div>
  );
}
