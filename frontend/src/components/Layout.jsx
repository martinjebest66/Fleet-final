import { Car, Users, BookOpen, GasPump, Warning, MapPin, ChartBar, Handshake, SignOut, List, Drop, Cpu, Engine, Wrench, CalendarCheck, FileArrowUp } from "@phosphor-icons/react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../App";
import { useState, useMemo } from "react";

const ADMIN_NAV = [
  { name: "Přehled", href: "/dashboard", icon: ChartBar },
  { name: "Vozidla", href: "/vehicles", icon: Car },
  { name: "Instruktoři", href: "/instructors", icon: Users },
  { name: "Kniha jízd", href: "/logbook", icon: BookOpen },
  { name: "Tankování", href: "/fuel", icon: GasPump },
  { name: "Spotřeba", href: "/fuel-analytics", icon: Drop },
  { name: "Poškození", href: "/damages", icon: Warning },
  { name: "Předávky", href: "/handovers", icon: Handshake },
  { name: "Údržba", href: "/maintenance", icon: CalendarCheck },
  { name: "GPS sledování", href: "/gps", icon: MapPin },
  { name: "Import Ruhavik", href: "/ruhavik-import", icon: FileArrowUp },
  { name: "OBD Diagnostika", href: "/obd", icon: Engine },
  { name: "Nastavení trackeru", href: "/tracker-setup", icon: Wrench },
  { name: "Reporty", href: "/reports", icon: ChartBar },
];

const INSTRUCTOR_NAV = [
  { name: "Přehled", href: "/dashboard", icon: ChartBar },
  { name: "Kniha jízd", href: "/logbook", icon: BookOpen },
  { name: "Tankování", href: "/fuel", icon: GasPump },
  { name: "Poškození", href: "/damages", icon: Warning },
  { name: "GPS sledování", href: "/gps", icon: MapPin },
];

export default function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const navigation = useMemo(() => {
    return user?.role === "instructor" ? INSTRUCTOR_NAV : ADMIN_NAV;
  }, [user?.role]);

  const roleBadge = user?.role === "instructor" ? "Instruktor" : "Admin";

  const handleLogout = async () => {
    await logout();
    navigate("/login");
  };

  return (
    <div className="flex min-h-screen bg-[#F4F4F5]">
      {/* Desktop Sidebar */}
      <aside className="hidden lg:flex lg:flex-col sidebar" data-testid="desktop-sidebar">
        <div className="p-6 border-b border-[#E4E4E7]">
          <h1 className="font-['Manrope'] text-xl font-bold text-[#18181B] tracking-tight">Fleet Manager</h1>
          <div className="flex items-center gap-2 mt-1">
            <p className="text-sm text-[#52525B]">Autoškola</p>
            <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${user?.role === "instructor" ? "bg-blue-100 text-blue-700" : "bg-[#002FA7]/10 text-[#002FA7]"}`} data-testid="role-badge">
              {roleBadge}
            </span>
          </div>
        </div>

        <nav className="flex-1 py-4">
          {navigation.map((item) => (
            <NavLink
              key={item.name}
              to={item.href}
              className={({ isActive }) => `sidebar-link ${isActive ? "active" : ""}`}
              data-testid={`nav-${item.href.slice(1)}`}
            >
              <item.icon size={20} weight="duotone" />
              <span>{item.name}</span>
            </NavLink>
          ))}
        </nav>

        <div className="p-4 border-t border-[#E4E4E7]">
          <div className="flex items-center gap-3 px-3 py-2">
            {user?.picture ? (
              <img src={user.picture} alt={user.name} className="w-8 h-8 rounded-full" />
            ) : (
              <div className="w-8 h-8 rounded-full bg-[#002FA7] text-white flex items-center justify-center text-sm font-bold">
                {user?.name?.charAt(0)?.toUpperCase() || "?"}
              </div>
            )}
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-[#18181B] truncate">{user?.name}</p>
              <p className="text-xs text-[#52525B] truncate">{user?.email || roleBadge}</p>
            </div>
          </div>
          <button onClick={handleLogout} className="sidebar-link w-full mt-2 text-[#991B1B] hover:bg-red-50" data-testid="logout-btn">
            <SignOut size={20} weight="duotone" />
            <span>Odhlásit se</span>
          </button>
        </div>
      </aside>

      {/* Mobile Header */}
      <div className="lg:hidden fixed top-0 left-0 right-0 z-40 bg-white border-b border-[#E4E4E7]">
        <div className="flex items-center justify-between px-4 py-3">
          <div className="flex items-center gap-2">
            <h1 className="font-['Manrope'] text-lg font-bold text-[#18181B]">Fleet Manager</h1>
            <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${user?.role === "instructor" ? "bg-blue-100 text-blue-700" : "bg-[#002FA7]/10 text-[#002FA7]"}`}>{roleBadge}</span>
          </div>
          <button onClick={() => setMobileMenuOpen(!mobileMenuOpen)} className="p-2 text-[#52525B]" data-testid="mobile-menu-toggle">
            <List size={24} />
          </button>
        </div>

        {mobileMenuOpen && (
          <div className="absolute top-full left-0 right-0 bg-white border-b border-[#E4E4E7] shadow-lg animate-fade-in">
            <nav className="py-2">
              {navigation.map((item) => (
                <NavLink
                  key={item.name}
                  to={item.href}
                  onClick={() => setMobileMenuOpen(false)}
                  className={({ isActive }) =>
                    `flex items-center gap-3 px-4 py-3 text-sm ${isActive ? "bg-[#002FA7] text-white" : "text-[#52525B] hover:bg-[#F4F4F5]"}`
                  }
                >
                  <item.icon size={20} weight="duotone" />
                  <span>{item.name}</span>
                </NavLink>
              ))}
              <button onClick={handleLogout} className="flex items-center gap-3 px-4 py-3 text-sm text-[#991B1B] hover:bg-red-50 w-full">
                <SignOut size={20} weight="duotone" />
                <span>Odhlásit se</span>
              </button>
            </nav>
          </div>
        )}
      </div>

      {/* Main Content */}
      <main className="flex-1 lg:ml-0 pt-14 lg:pt-0">
        <div className="p-4 lg:p-8">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
