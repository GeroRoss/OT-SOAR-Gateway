/** Provides normal management navigation and separated development tools. */

const mainPages = [
  ["overview", "Overview"],
  ["infrastructure", "Infrastructure"],
  ["personnel", "Personnel & Access"],
  ["security", "Security"],
];

const developmentPages = [
  ["simulation", "Simulation"],
  ["attack", "Attack"],
];

export default function Sidebar({ currentPage, onNavigate }) {
  const renderButton = ([id, label]) => (
    <button
      className={currentPage === id ? "nav-item active" : "nav-item"}
      key={id}
      onClick={() => onNavigate(id)}
      type="button"
    >
      {label}
    </button>
  );

  return (
    <aside className="sidebar">
      <div className="brand">
        <strong>OT-SOAR</strong>
        <span>Gateway</span>
      </div>
      <nav className="navigation">{mainPages.map(renderButton)}</nav>
      <div className="development-nav">
        <span>Development</span>
        {developmentPages.map(renderButton)}
      </div>
    </aside>
  );
}
