import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { API } from "../App";
import { GasPump, TrendDown, TrendUp, Car } from "@phosphor-icons/react";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Label } from "../components/ui/label";
import { Input } from "../components/ui/input";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, LineChart, Line } from "recharts";
import { toast } from "sonner";

export default function FuelAnalytics() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [vehicles, setVehicles] = useState([]);
  const [filters, setFilters] = useState({ vehicle_id: "", date_from: "", date_to: "" });

  const fetchVehicles = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/vehicles`, { withCredentials: true });
      setVehicles(res.data);
    } catch { toast.error("Nepodařilo se načíst vozidla"); }
  }, []);

  const fetchAnalytics = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (filters.vehicle_id && filters.vehicle_id !== "all") params.append("vehicle_id", filters.vehicle_id);
      if (filters.date_from) params.append("date_from", filters.date_from);
      if (filters.date_to) params.append("date_to", filters.date_to);
      const res = await axios.get(`${API}/reports/fuel-analytics?${params}`, { withCredentials: true });
      setData(res.data);
    } catch { toast.error("Nepodařilo se načíst analytiku"); }
    finally { setLoading(false); }
  }, [filters]);

  useEffect(() => { fetchVehicles(); }, [fetchVehicles]);
  useEffect(() => { fetchAnalytics(); }, [fetchAnalytics]);

  if (loading && !data) return <div className="flex items-center justify-center h-64"><div className="loading-spinner"></div></div>;

  const summary = data?.summary || {};
  const vehicleStats = data?.vehicle_stats || [];

  const comparisonData = vehicleStats.map(v => ({
    name: v.vehicle_info?.split("(")[0]?.trim() || v.vehicle_id,
    consumption: v.consumption_per_100km,
    cost_per_km: v.cost_per_km,
    total_liters: v.total_liters,
  }));

  const allMonthly = {};
  for (const vs of vehicleStats) {
    for (const m of vs.monthly_trend || []) {
      if (!allMonthly[m.month]) allMonthly[m.month] = { month: m.month, liters: 0, cost: 0 };
      allMonthly[m.month].liters += m.liters;
      allMonthly[m.month].cost += m.cost;
    }
  }
  const monthlyTrend = Object.values(allMonthly).sort((a, b) => a.month.localeCompare(b.month));

  return (
    <div className="space-y-6" data-testid="fuel-analytics-page">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="font-['Manrope'] text-2xl lg:text-3xl font-bold text-[#18181B] tracking-tight">Spotřeba paliva</h1>
          <p className="text-[#52525B] mt-1">Analytika nákladů a spotřeby</p>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-4 items-end">
        <div>
          <Label className="text-xs">Vozidlo</Label>
          <Select value={filters.vehicle_id} onValueChange={(v) => setFilters({ ...filters, vehicle_id: v })}>
            <SelectTrigger className="w-48"><SelectValue placeholder="Všechna" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Všechna vozidla</SelectItem>
              {vehicles.map(v => <SelectItem key={v.vehicle_id} value={v.vehicle_id}>{v.brand} {v.model}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label className="text-xs">Od</Label>
          <Input type="date" value={filters.date_from} onChange={(e) => setFilters({ ...filters, date_from: e.target.value })} className="w-40" />
        </div>
        <div>
          <Label className="text-xs">Do</Label>
          <Input type="date" value={filters.date_to} onChange={(e) => setFilters({ ...filters, date_to: e.target.value })} className="w-40" />
        </div>
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-white border border-[#E4E4E7] rounded-md p-5">
          <div className="flex items-center gap-2 text-[#52525B] text-sm mb-2">
            <GasPump size={16} className="text-[#002FA7]" />
            Celkem litrů
          </div>
          <p className="text-2xl font-bold text-[#18181B]">{summary.total_liters?.toLocaleString("cs-CZ") || 0} l</p>
        </div>
        <div className="bg-white border border-[#E4E4E7] rounded-md p-5">
          <div className="flex items-center gap-2 text-[#52525B] text-sm mb-2">
            <TrendDown size={16} className="text-[#002FA7]" />
            Spotřeba
          </div>
          <p className="text-2xl font-bold text-[#18181B]">{summary.avg_consumption_per_100km || 0} l/100km</p>
        </div>
        <div className="bg-white border border-[#E4E4E7] rounded-md p-5">
          <div className="flex items-center gap-2 text-[#52525B] text-sm mb-2">
            <TrendUp size={16} className="text-[#002FA7]" />
            Celkem náklady
          </div>
          <p className="text-2xl font-bold text-[#18181B]">{summary.total_cost?.toLocaleString("cs-CZ") || 0} Kč</p>
        </div>
        <div className="bg-white border border-[#E4E4E7] rounded-md p-5">
          <div className="flex items-center gap-2 text-[#52525B] text-sm mb-2">
            <Car size={16} className="text-[#002FA7]" />
            Najeté km
          </div>
          <p className="text-2xl font-bold text-[#18181B]">{summary.total_km?.toLocaleString("cs-CZ") || 0} km</p>
        </div>
      </div>

      {/* Charts */}
      {comparisonData.length > 0 ? (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Consumption comparison */}
          <div className="bg-white border border-[#E4E4E7] rounded-md p-6">
            <h3 className="font-semibold text-[#18181B] mb-4">Spotřeba dle vozidla (l/100km)</h3>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={comparisonData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#E4E4E7" />
                <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip formatter={(val) => [`${val} l/100km`, "Spotřeba"]} />
                <Bar dataKey="consumption" fill="#002FA7" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* Monthly trend */}
          <div className="bg-white border border-[#E4E4E7] rounded-md p-6">
            <h3 className="font-semibold text-[#18181B] mb-4">Měsíční trend</h3>
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={monthlyTrend}>
                <CartesianGrid strokeDasharray="3 3" stroke="#E4E4E7" />
                <XAxis dataKey="month" tick={{ fontSize: 11 }} />
                <YAxis yAxisId="left" tick={{ fontSize: 11 }} />
                <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 11 }} />
                <Tooltip />
                <Legend />
                <Line yAxisId="left" type="monotone" dataKey="liters" stroke="#002FA7" name="Litry" strokeWidth={2} />
                <Line yAxisId="right" type="monotone" dataKey="cost" stroke="#16A34A" name="Náklady (Kč)" strokeWidth={2} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      ) : (
        <div className="bg-white border border-[#E4E4E7] rounded-md p-12 text-center">
          <GasPump size={48} weight="duotone" className="mx-auto text-[#A1A1AA] mb-4" />
          <h3 className="font-semibold text-[#18181B] mb-2">Žádná data o tankování</h3>
          <p className="text-[#52525B]">Přidejte záznamy o tankování pro zobrazení analytiky</p>
        </div>
      )}

      {/* Per-vehicle details */}
      {vehicleStats.length > 0 && (
        <div>
          <h3 className="font-semibold text-[#18181B] mb-4">Detail dle vozidla</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {vehicleStats.map(vs => (
              <div key={vs.vehicle_id} className="bg-white border border-[#E4E4E7] rounded-md p-5" data-testid={`fuel-stat-${vs.vehicle_id}`}>
                <div className="flex items-center gap-2 mb-3">
                  <Car size={20} className="text-[#002FA7]" />
                  <span className="font-semibold text-[#18181B] text-sm">{vs.vehicle_info}</span>
                </div>
                <div className="space-y-2 text-sm">
                  <div className="flex justify-between"><span className="text-[#52525B]">Spotřeba</span><span className="font-bold text-[#18181B]">{vs.consumption_per_100km} l/100km</span></div>
                  <div className="flex justify-between"><span className="text-[#52525B]">Celkem litrů</span><span className="font-medium">{vs.total_liters} l</span></div>
                  <div className="flex justify-between"><span className="text-[#52525B]">Celkem náklady</span><span className="font-medium">{vs.total_cost.toLocaleString("cs-CZ")} Kč</span></div>
                  <div className="flex justify-between"><span className="text-[#52525B]">Najeté km</span><span className="font-medium">{vs.km_driven.toLocaleString("cs-CZ")} km</span></div>
                  <div className="flex justify-between"><span className="text-[#52525B]">Cena/km</span><span className="font-medium">{vs.cost_per_km} Kč</span></div>
                  <div className="flex justify-between"><span className="text-[#52525B]">Tankování</span><span className="font-medium">{vs.fill_count}x</span></div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
