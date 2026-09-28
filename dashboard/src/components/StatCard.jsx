/**
 * Displays one high-level operational metric on the dashboard.
 */

export default function StatCard({ label, value, detail, state }) {
  return (
    <article className={`stat-card ${state || ""}`}>
      <span className="stat-label">{label}</span>

      <strong className="stat-value">{value}</strong>

      {detail && <span className="stat-detail">{detail}</span>}
    </article>
  );
}
