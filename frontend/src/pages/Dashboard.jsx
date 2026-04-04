import { useState, useEffect, useCallback, useMemo } from "react";
import axios from "axios";
import { API } from "../App";
import { Car, Users, RoadHorizon, GasPump, Warning, TrendUp } from "@phosphor-icons/react";
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import { toast } from "sonner";

// Memoized chart styles
const axisTick = { fill: '#52525B', fontSize: 12 };
const tooltipStyle = {
  background: '#FFFFFF',
  border: '1px solid #E4E4E7',
  borderRadius: '6px',
  fontSize: '14px'
};

// Helper function for purpose badge
const getPurposeBadgeClass = (purpose) => {
  if (purpose === "výcvik") return "badge-info";
  if (purpose === "služební") return "badge-warning";
  return "badge-success";
};

export default function Dashboard() {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [recentTrips, setRecentTrips] = useState([]);

  const fetchDashboardData = useCallback(async () => {
    try {
      const [statsRes, tripsRes] = await Promise.all([
        axios.get(`${API}/reports/dashboard`, { withCredentials: true }),
        axios.get(`${API}/logbook?limit=5`, { withCredentials: true })
      ]);
      setStats(statsRes.data);
      setRecentTrips(tripsRes.data.slice(0, 5));
    } catch {
      toast.error("Nepodařilo se načíst data");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchDashboardData();
  }, [fetchDashboardData]);

  const kpiCards = useMemo(() => [
    {
      label: "Vozidla",
      value: stats?.total_vehicles || 0,
      icon: Car,
      color: "#002FA7"
    },
    {
      label: "Instruktoři",
      value: stats?.total_instructors || 0,
      icon: Users,
      color: "#16A34A"
    },
    {
      label: "Km tento měsíc",
      value: `${stats?.total_km_month?.toLocaleString("cs-CZ") || 0}`,
      icon: RoadHorizon,
      color: "#002FA7"
    },
    {
      label: "Náklady na palivo",
      value: `${stats?.total_fuel_cost_month?.toLocaleString("cs-CZ") || 0} Kč`,
      icon: GasPump,
      color: "#FFC000"
    },
    {
      label: "Otevřená poškození",
      value: stats?.open_damages || 0,
      icon: Warning,
      color: stats?.open_damages > 0 ? "#FF2400" : "#16A34A"
    },
    {
      label: "Jízd tento týden",
      value: stats?.recent_trips || 0,
      icon: TrendUp,
      color: "#002FA7"
    }
  ], [stats]);

  // Mock chart data for km trends
  const chartData = [
    { date: "Po", km: 45 },
    { date: "Út", km: 62 },
    { date: "St", km: 38 },
    { date: "Čt", km: 71 },
    { date: "Pá", km: 55 },
    { date: "So", km: 28 },
    { date: "Ne", km: 15 }
  ];

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="loading-spinner"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6" data-testid="dashboard">
      {/* Header */}
      <div>
        <h1 className="font-['Manrope'] text-2xl lg:text-3xl font-bold text-[#18181B] tracking-tight">
          Přehled
        </h1>
        <p className="text-[#52525B] mt-1">
          Aktuální stav vozového parku
        </p>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-4">
        {kpiCards.map((kpi) => (
          <div
            key={kpi.label}
            className="kpi-card card-hover rounded-md"
            data-testid={`kpi-${kpi.label.toLowerCase().replace(/\s/g, '-')}`}
          >
            <div className="flex items-start justify-between">
              <kpi.icon size={24} weight="duotone" style={{ color: kpi.color }} />
            </div>
            <div className="mt-4">
              <div className="kpi-value">{kpi.value}</div>
              <div className="kpi-label">{kpi.label}</div>
            </div>
          </div>
        ))}
      </div>

      {/* Charts & Tables Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Km Trend Chart */}
        <div className="chart-container">
          <h3 className="font-['Manrope'] text-lg font-semibold text-[#18181B] mb-4">
            Kilometry tento týden
          </h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData}>
                <defs>
                  <linearGradient id="kmGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#002FA7" stopOpacity={0.2} />
                    <stop offset="95%" stopColor="#002FA7" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <XAxis 
                  dataKey="date" 
                  axisLine={false}
                  tickLine={false}
                  tick={axisTick}
                />
                <YAxis 
                  axisLine={false}
                  tickLine={false}
                  tick={axisTick}
                />
                <Tooltip
                  contentStyle={tooltipStyle}
                  formatter={(value) => [`${value} km`, 'Kilometry']}
                />
                <Area
                  type="monotone"
                  dataKey="km"
                  stroke="#002FA7"
                  strokeWidth={2}
                  fill="url(#kmGradient)"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Vehicle Status */}
        <div className="chart-container">
          <h3 className="font-['Manrope'] text-lg font-semibold text-[#18181B] mb-4">
            Stav vozidel
          </h3>
          {stats?.vehicles?.length > 0 ? (
            <div className="space-y-3">
              {stats.vehicles.slice(0, 5).map((vehicle) => (
                <div
                  key={vehicle.vehicle_id}
                  className="flex items-center justify-between p-3 border border-[#E4E4E7] rounded-md hover:border-[#A1A1AA] transition-colors"
                >
                  <div className="flex items-center gap-3">
                    <Car size={20} weight="duotone" className="text-[#002FA7]" />
                    <div>
                      <p className="font-medium text-[#18181B]">
                        {vehicle.brand} {vehicle.model}
                      </p>
                      <p className="text-sm text-[#52525B]">
                        {vehicle.registration_plate}
                      </p>
                    </div>
                  </div>
                  <div className="text-right">
                    <p className="font-semibold text-[#18181B]">
                      {vehicle.odometer?.toLocaleString("cs-CZ")} km
                    </p>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="empty-state">
              <Car size={48} weight="duotone" className="mx-auto text-[#A1A1AA] mb-4" />
              <p>Zatím žádná vozidla</p>
            </div>
          )}
        </div>
      </div>

      {/* Recent Trips Table */}
      <div className="chart-container">
        <h3 className="font-['Manrope'] text-lg font-semibold text-[#18181B] mb-4">
          Poslední jízdy
        </h3>
        {recentTrips.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Datum</th>
                  <th>Vozidlo</th>
                  <th>Trasa</th>
                  <th>Vzdálenost</th>
                  <th>Účel</th>
                </tr>
              </thead>
              <tbody>
                {recentTrips.map((trip) => (
                  <tr key={trip.entry_id}>
                    <td>{trip.date}</td>
                    <td>{trip.vehicle_info || "-"}</td>
                    <td className="max-w-xs truncate">
                      {trip.start_location} → {trip.end_location}
                    </td>
                    <td>{trip.distance} km</td>
                    <td>
                      <span className={`badge ${getPurposeBadgeClass(trip.purpose)}`}>
                        {trip.purpose}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="empty-state">
            <RoadHorizon size={48} weight="duotone" className="mx-auto text-[#A1A1AA] mb-4" />
            <p>Zatím žádné jízdy</p>
          </div>
        )}
      </div>
    </div>
  );
}
