/**
 * Global page header — placed inside each surface page's content area.
 *
 * Renders an H1 with the surface name and an optional "data as of <time>"
 * stamp showing the most-recent mtime of artifacts the page read. The caller
 * supplies the timestamp; surfaces whose view-models do not yet expose
 * artifact mtimes pass `null`, which omits the stamp.
 *
 * Intentionally not "use client" — static markup only. No timer, no polling.
 * The "· live ⟳" suffix is a visual cue shown only when the page passes `live`;
 * those are the pages that mount a LiveRefresh of their own (Workshops and
 * Overview), so reference pages never claim to refresh.
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
  /** The page mounts a LiveRefresh; only then does the header say it is live. */
  live?: boolean;
  title: string;
};

const pad2 = (value: number): string => String(value).padStart(2, "0");

/** `YYYY-MM-DD` in the viewer's calendar — the same zone that decides "today". */
function localDateLabel(date: Date): string {
  return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}`;
}

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
  return localDateLabel(date);
}

function toIsoString(raw: Date | string): string {
  const date = typeof raw === "string" ? new Date(raw) : raw;
  return isNaN(date.getTime()) ? "" : date.toISOString();
}

export function AppHeader({ title, dataAsOf, live = false, breadcrumb = [] }: AppHeaderProps) {
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
            {live && (
              <>
                {" · "}
                <span className="app-header__live" aria-hidden="true">
                  live ⟳
                </span>
              </>
            )}
          </span>
        )}
      </div>
    </header>
  );
}
