import { Link, NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

function navigationLinks(role) {
  if (role === "doctor") {
    return [{ to: "/doctor", label: "My day" }];
  }
  if (role === "admin") {
    return [{ to: "/admin", label: "Dashboard" }];
  }
  if (role === "patient") {
    return [
      { to: "/", label: "Find a doctor" },
      { to: "/appointments", label: "My appointments" },
    ];
  }
  return [{ to: "/", label: "Find a doctor" }];
}

export default function Layout() {
  const { user, logOut } = useAuth();
  const links = navigationLinks(user?.role);

  return (
    <div className="min-h-screen">
      <header className="border-b border-line bg-white">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-3 px-4 py-3">
          <Link to="/" className="flex items-center gap-2 text-lg font-bold">
            <img src="/favicon.svg" alt="" className="h-7 w-7" />
            MediSlot
          </Link>
          <nav className="flex flex-wrap items-center gap-1 text-sm">
            {links.map((link) => (
              <NavLink
                key={link.to}
                to={link.to}
                end
                className={({ isActive }) =>
                  `rounded-md px-3 py-2 font-medium ${isActive ? "bg-brand-soft text-brand-dark" : "text-muted hover:text-ink"}`
                }
              >
                {link.label}
              </NavLink>
            ))}
            {user ? (
              <button type="button" onClick={logOut} className="rounded-md px-3 py-2 font-medium text-muted hover:text-ink">
                Log out
              </button>
            ) : (
              <NavLink to="/login" className="rounded-md px-3 py-2 font-medium text-muted hover:text-ink">
                Log in
              </NavLink>
            )}
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-4 py-8">
        <Outlet />
      </main>
    </div>
  );
}
