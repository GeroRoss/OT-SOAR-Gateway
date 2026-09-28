/** Consistent, section-local feedback for dashboard operations. */
export default function Notice({ notice, section }) {
  if (!notice?.text || (section && notice.section !== section)) return null;

  return (
    <div className={`notice notice-${notice.type || "info"}`} role="status">
      {notice.text}
    </div>
  );
}
