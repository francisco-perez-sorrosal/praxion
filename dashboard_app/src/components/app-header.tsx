/**
 * Global page header — placed inside each surface page's content area.
 *
 * Renders an H1 with the surface name and an optional "data as of <time>"
 * stamp showing the most-recent mtime of artifacts the page read. The caller
 * supplies the timestamp; surfaces whose view-models do not yet expose
 * artifact mtimes pass `null`, which omits the stamp.
 *
 * Intentionally not "use client" — static markup only. No timer, no polling.
 * The "· live ⟳" suffix is a visual cue; the actual refresh animation lives
 * in LiveRefresh inside the sidebar footer.
 *
 * Breadcrumb renders only when breadcrumb.length > 1, which on the 7 top-
 * level surfaces degenerates to an empty list (no crumb rendered).
 */

type BreadcrumbItem = {
  href: string;
  label: string;
};

type AppHeaderProps = {
  breadcrumb?: BreadcrumbItem[];
  dataAsOf?: Date | string | null;
  title: string;
};

const TODAY_DATE_LABEL_CHARS = 10; // YYYY-MM-DD

function formatDataAsOf(raw: Date | string): string {
  const date = typeof raw === "string" ? new Date(raw) : raw;
  if (isNaN(date.getTime())) {
    return "unknown";
  }
  // Show HH:MM if the date is today; otherwise YYYY-MM-DD.
  const now = new Date();
  const isToday =
    date.getFullYear() === now.getFullYear() &&
    date.getMonth() === now.getMonth() &&
    date.getDate() === now.getDate();

  if (isToday) {
    return date.toLocaleTimeString("en-US", {
      hour: "2-digit",
      hour12: false,
      minute: "2-digit"
    });
  }
  return date.toISOString().slice(0, TODAY_DATE_LABEL_CHARS);
}

function toIsoString(raw: Date | string): string {
  const date = typeof raw === "string" ? new Date(raw) : raw;
  return isNaN(date.getTime()) ? "" : date.toISOString();
}

export function AppHeader({ title, dataAsOf, breadcrumb = [] }: AppHeaderProps) {
  const showCrumbs = breadcrumb.length > 1;

  return (
    <header className="app-header">
      {showCrumbs && (
        <nav className="app-header__crumbs" aria-label="breadcrumb">
          <ol className="app-header__crumbs-list">
            {breadcrumb.map((item, index) => (
              <li key={item.href} className="app-header__crumbs-item">
                {index < breadcrumb.length - 1 ? (
                  <>
                    <a href={item.href} className="app-header__crumb-link">
                      {item.label}
                    </a>
                    <span className="app-header__crumb-sep" aria-hidden="true">
                      ›
                    </span>
                  </>
                ) : (
                  <span className="app-header__crumb-current" aria-current="page">
                    {item.label}
                  </span>
                )}
              </li>
            ))}
          </ol>
        </nav>
      )}
      <div className="app-header__bar">
        <h1 className="app-header__title">{title}</h1>
        {dataAsOf != null && (
          <span className="app-header__stamp">
            data as of{" "}
            <time dateTime={toIsoString(dataAsOf)}>{formatDataAsOf(dataAsOf)}</time>
            {" · "}
            <span className="app-header__live" aria-hidden="true">
              live ⟳
            </span>
          </span>
        )}
      </div>
    </header>
  );
}
