import { useState, useEffect } from "react";
import axios from "axios";
import { API } from "../App";
import { ChartBar, Calendar, Download } from "@phosphor-icons/react";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, LineChart, Line } from "recharts";
import { format, subDays, subMonths, startOfMonth, endOfMonth } from "date-fns";
import { toast } from "sonner";

export default function Reports() {
  const [vehicles, setVehicles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState(null);
  const [filters, setFilters] = useState({
    vehicle_id: "",
    date_from: format(subDays(new Date(), 30), "yyyy-MM-dd"),
    date_to: format(new Date(), "yyyy-MM-dd"),
    preset: "month"
  });

  useEffect(() => {
    fetchVehicles();
  }, []);

  useEffect(() => {
    if (filters.date_from && filters.date_to) fetchStats();
  }, [filters]);

  const fetchVehicles = async () => {
    try {
      const res = await axios.get(`${API}/vehicles`, { withCredentials: true });
      setVehicles(res.data);
    } catch (error) { console.error(error); } 
    finally { setLoading(false); }
  };

  const fetchStats = async () => {
    try {
      const params = new URLSearchParams();
      params.append("date_from", filters.date_from);
      params.append("date_to", filters.date_to);
      if (filters.vehicle_id) params.append("vehicle_id", filters.vehicle_id);
      const res = await axios.get(`${API}/reports/km-stats?${params}`, { withCredentials: true });
      setStats(res.data);
    } catch (error) { toast.error("Nepodařilo se načíst statistiky"); }
  };

  const handlePresetChange = (preset) => {
    const now = new Date();
    let from, to;
    switch (preset) {
      case "week": from = subDays(now, 7); to = now; break;
      case "month": from = startOfMonth(now); to = endOfMonth(now); break;
      case "quarter": from = subMonths(now, 3); to = now; break;
      case "year": from = subMonths(now, 12); to = now; break;
      default: return;
    }
    setFilters({ ...filters, preset, date_from: format(from, "yyyy-MM-dd"), date_to: format(to, "yyyy-MM-dd") });
  };

  const exportToCSV = () => {
    if (!stats) return;
    const headers = ["Datum", "Kilometry"];
    const rows = stats.daily_stats.map(d => [d.date, d.km]);
    const csv = [headers, ...rows].map(row => row.join(";")).join("\n");
    const blob = new Blob(["\uFEFF" + csv], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = `report-km-${format(new Date(), "yyyy-MM-dd")}.csv`; a.click();
  };

  if (loading) return <div className="flex items-center justify-center h-64"><div className="loading-spinner"></div></div>;

  return (
    <div className="space-y-6" data-testid="reports-page">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="font-['Manrope'] text-2xl lg:text-3xl font-bold text-[#18181B] tracking-tight">Reporty</h1>
          <p className="text-[#52525B] mt-1">Statistiky a přehledy kilometrů</p>
        </div>
        <Button variant="outline" onClick={exportToCSV} disabled={!stats}><Download size={20} className="mr-2" />Export CSV</Button>
      </div>

      <div className="bg-white border border-[#E4E4E7] rounded-md p-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
          <div><Label>Období</Label>
            <Select value={filters.preset} onValueChange={handlePresetChange}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="week">Týden</SelectItem>
                <SelectItem value="month">Měsíc</SelectItem>
                <SelectItem value="quarter">Čtvrtletí</SelectItem>
                <SelectItem value="year">Rok</SelectItem>
                <SelectItem value="custom">Vlastní</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div><Label>Od</Label><Input type="date" value={filters.date_from} onChange={(e) => setFilters({ ...filters, date_from: e.target.value, preset: "custom" })} /></div>
          <div><Label>Do</Label><Input type="date" value={filters.date_to} onChange={(e) => setFilters({ ...filters, date_to: e.target.value, preset: "custom" })} /></div>
          <div><Label>Vozidlo</Label>
            <Select value={filters.vehicle_id} onValueChange={(v) => setFilters({ ...filters, vehicle_id: v })}>
              <SelectTrigger><SelectValue placeholder="Všechna" /></SelectTrigger>
              <SelectContent><SelectItem value="">Všechna</SelectItem>{vehicles.map(v => <SelectItem key={v.vehicle_id} value={v.vehicle_id}>{v.brand} {v.model}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div className="flex items-end"><Button variant="outline" onClick={() => { setFilters({ vehicle_id: "", date_from: format(subDays(new Date(), 30), "yyyy-MM-dd"), date_to: format(new Date(), "yyyy-MM-dd"), preset: "month" }); }} className="w-full">Reset</Button></div>
        </div>
      </div>

      {stats && (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div className="bg-[#002FA7] text-white rounded-md p-6">
              <p className="text-sm opacity-80">Celkem km</p>
              <p className="text-3xl font-bold">{stats.total_km?.toLocaleString("cs-CZ")}</p>
            </div>
            <div className="bg-white border border-[#E4E4E7] rounded-md p-6">
              <p className="text-sm text-[#52525B]">Průměr/den</p>
              <p className="text-3xl font-bold text-[#18181B]">{stats.avg_km_per_day?.toLocaleString("cs-CZ")} km</p>
            </div>
            <div className="bg-white border border-[#E4E4E7] rounded-md p-6">
              <p className="text-sm text-[#52525B]">Počet dní</p>
              <p className="text-3xl font-bold text-[#18181B]">{stats.daily_stats?.length || 0}</p>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="bg-white border border-[#E4E4E7] rounded-md p-6">
              <h3 className="font-semibold text-[#18181B] mb-4">Kilometry po dnech</h3>
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={stats.daily_stats}>
                    <XAxis dataKey="date" tick={{ fontSize: 10 }} tickFormatter={(v) => v.slice(5)} />
                    <YAxis tick={{ fontSize: 12 }} />
                    <Tooltip formatter={(v) => [`${v} km`, "Km"]} labelFormatter={(l) => `Datum: ${l}`} />
                    <Bar dataKey="km" fill="#002FA7" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div className="bg-white border border-[#E4E4E7] rounded-md p-6">
              <h3 className="font-semibold text-[#18181B] mb-4">Trend</h3>
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={stats.daily_stats}>
                    <XAxis dataKey="date" tick={{ fontSize: 10 }} tickFormatter={(v) => v.slice(5)} />
                    <YAxis tick={{ fontSize: 12 }} />
                    <Tooltip formatter={(v) => [`${v} km`, "Km"]} />
                    <Line type="monotone" dataKey="km" stroke="#002FA7" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>

          {stats.vehicle_stats && Object.keys(stats.vehicle_stats).length > 0 && (
            <div className="bg-white border border-[#E4E4E7] rounded-md p-6">
              <h3 className="font-semibold text-[#18181B] mb-4">Statistiky podle vozidel</h3>
              <div className="overflow-x-auto">
                <table className="data-table">
                  <thead><tr><th>Vozidlo</th><th>Celkem km</th><th>Počet jízd</th><th>Průměr/jízda</th></tr></thead>
                  <tbody>
                    {Object.entries(stats.vehicle_stats).map(([id, data]) => (
                      <tr key={id}>
                        <td className="font-medium">{data.name || id}</td>
                        <td>{data.total_km?.toLocaleString("cs-CZ")} km</td>
                        <td>{data.trips}</td>
                        <td>{data.trips > 0 ? Math.round(data.total_km / data.trips) : 0} km</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}

      {!stats && (
        <div className="bg-white border border-[#E4E4E7] rounded-md p-12 text-center">
          <ChartBar size={48} weight="duotone" className="mx-auto text-[#A1A1AA] mb-4" />
          <h3 className="font-semibold text-[#18181B] mb-2">Žádná data</h3>
          <p className="text-[#52525B]">Vyberte období pro zobrazení statistik</p>
        </div>
      )}
    </div>
  );
}
