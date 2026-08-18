export default function Status({ children, tone = "neutral" }) {
  const testid = `status-${String(children).toLowerCase().replaceAll(" ", "-")}`;
  return <span data-testid={testid} className={`status ${tone}`}>{children}</span>;
}
