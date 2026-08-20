import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { API } from "../App";
import { errorMessage } from "@/lib/api";
import { GasPump, Plus, Download } from "@phosphor-icons/react";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "../components/ui/dialog";
import { format } from "date-fns";
import { toast } from "sonner";

export default function FuelEntries() {
  const [entries, setEntries] = useState([]);
  const [vehicles, setVehicles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [filters, setFilters] = useState({ vehicle_id: "all", date_from: "", date_to: "" });
  const [formData, setFormData] = useState({
    vehicle_id: "", date: format(new Date(), "yyyy-MM-dd"), odometer: 0, liters: 0, price_per_liter: 38.90, total_price: 0, fuel_station: "", notes: ""
  });

  const fetchData = useCallback(async () => {
    try {
      const params = new URLSearchParams();
      if (filters.vehicle_id) params.append("vehicle_id", filters.vehicle_id);
      if (filters.date_from) params.append("date_from", filters.date_from);
      if (filters.date_to) params.append("date_to", filters.date_to);
      const [entriesRes, vehiclesRes] = await Promise.all([
        axios.get(`${API}/fuel?${params}`, { withCredentials: true }),
        axios.get(`${API}/vehicles`, { withCredentials: true })
      ]);
      setEntries(entriesRes.data);
      setVehicles(vehiclesRes.data);
    } catch (error) { toast.error(errorMessage(error, "Nepodařilo se načíst záznamy")); } 
    finally { setLoading(false); }
  }, [filters]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      await axios.post(`${API}/fuel`, formData, { withCredentials: true });
      toast.success("Tankování zaznamenáno");
      setShowModal(false); resetForm(); fetchData();
    } catch (error) { toast.error(errorMessage(error, "Nepodařilo se uložit")); }
  };

  const resetForm = () => {
    const v = vehicles[0];
    setFormData({ vehicle_id: v?.vehicle_id || "", date: format(new Date(), "yyyy-MM-dd"), odometer: v?.odometer || 0, liters: 0, price_per_liter: 38.90, total_price: 0, fuel_station: "", notes: "" });
  };

  const handleVehicleChange = (vehicleId) => {
    const v = vehicles.find(x => x.vehicle_id === vehicleId);
    setFormData({ ...formData, vehicle_id: vehicleId, odometer: v?.odometer || 0 });
  };

  const handleLitersChange = (liters) => {
    setFormData({ ...formData, liters, total_price: Math.round(liters * formData.price_per_liter * 100) / 100 });
  };

  const handlePriceChange = (price) => {
    setFormData({ ...formData, price_per_liter: price, total_price: Math.round(formData.liters * price * 100) / 100 });
  };

  const exportToCSV = () => {
    const headers = ["Datum", "Vozidlo", "Litry", "Cena/l", "Celkem", "Tachometr", "Stanice"];
    const rows = entries.map(e => [e.date, e.vehicle_info || "", `${e.liters} l`, `${e.price_per_liter} Kč`, `${e.total_price} Kč`, `${e.odometer} km`, e.fuel_station || ""]);
    const csv = [headers, ...rows].map(row => row.join(";")).join("\n");
    const blob = new Blob(["\uFEFF" + csv], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = `tankovani-${format(new Date(), "yyyy-MM-dd")}.csv`; a.click();
  };

  const totalLiters = entries.reduce((sum, e) => sum + (e.liters || 0), 0);
  const totalCost = entries.reduce((sum, e) => sum + (e.total_price || 0), 0);

  if (loading) return <div className="flex items-center justify-center h-64"><div className="loading-spinner"></div></div>;

  return (
    <div className="space-y-6" data-testid="fuel-page">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="font-['Manrope'] text-2xl lg:text-3xl font-bold text-[#18181B] tracking-tight">Tankování</h1>
          <p className="text-[#52525B] mt-1">Evidence tankování vozidel</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={exportToCSV} disabled={entries.length === 0}><Download size={20} className="mr-2" />Export</Button>
          <Button onClick={() => { resetForm(); setShowModal(true); }} className="bg-[#002FA7] hover:bg-[#002480]" data-testid="add-fuel-btn"><Plus size={20} className="mr-2" />Nové tankování</Button>
        </div>
      </div>

      <div className="bg-white border border-[#E4E4E7] rounded-md p-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <div><Label>Vozidlo</Label><Select value={filters.vehicle_id} onValueChange={(v) => setFilters({ ...filters, vehicle_id: v })}><SelectTrigger><SelectValue placeholder="Všechna" /></SelectTrigger><SelectContent><SelectItem value="all">Všechna</SelectItem>{vehicles.map(v => <SelectItem key={v.vehicle_id} value={v.vehicle_id}>{v.brand} {v.model}</SelectItem>)}</SelectContent></Select></div>
          <div><Label>Od</Label><Input type="date" value={filters.date_from} onChange={(e) => setFilters({ ...filters, date_from: e.target.value })} /></div>
          <div><Label>Do</Label><Input type="date" value={filters.date_to} onChange={(e) => setFilters({ ...filters, date_to: e.target.value })} /></div>
          <div className="flex items-end"><Button variant="outline" onClick={() => setFilters({ vehicle_id: "all", date_from: "", date_to: "" })} className="w-full">Vymazat</Button></div>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div className="bg-[#FFC000] text-[#18181B] rounded-md p-4"><p className="text-sm opacity-80">Celkem natankováno</p><p className="text-2xl font-bold">{totalLiters.toLocaleString("cs-CZ")} l</p></div>
        <div className="bg-[#002FA7] text-white rounded-md p-4"><p className="text-sm opacity-80">Celkové náklady</p><p className="text-2xl font-bold">{totalCost.toLocaleString("cs-CZ")} Kč</p></div>
      </div>

      {entries.length > 0 ? (
        <div className="bg-white border border-[#E4E4E7] rounded-md overflow-hidden">
          <div className="overflow-x-auto">
            <table className="data-table">
              <thead><tr><th>Datum</th><th>Vozidlo</th><th>Litry</th><th>Cena/l</th><th>Celkem</th><th>Tachometr</th><th>Stanice</th></tr></thead>
              <tbody>
                {entries.map(e => (
                  <tr key={e.fuel_id}>
                    <td className="font-medium">{e.date}</td>
                    <td>{e.vehicle_info || "-"}</td>
                    <td>{e.liters.toLocaleString("cs-CZ")} l</td>
                    <td>{e.price_per_liter.toLocaleString("cs-CZ")} Kč</td>
                    <td className="font-semibold">{e.total_price.toLocaleString("cs-CZ")} Kč</td>
                    <td>{e.odometer.toLocaleString("cs-CZ")} km</td>
                    <td>{e.fuel_station || "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <div className="bg-white border border-[#E4E4E7] rounded-md p-12 text-center">
          <GasPump size={48} weight="duotone" className="mx-auto text-[#A1A1AA] mb-4" />
          <h3 className="font-semibold text-[#18181B] mb-2">Žádné záznamy</h3>
          <Button onClick={() => { resetForm(); setShowModal(true); }} className="bg-[#002FA7] hover:bg-[#002480]"><Plus size={20} className="mr-2" />Nové tankování</Button>
        </div>
      )}

      <Dialog open={showModal} onOpenChange={setShowModal}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Nové tankování</DialogTitle></DialogHeader>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div><Label>Vozidlo *</Label><Select value={formData.vehicle_id} onValueChange={handleVehicleChange}><SelectTrigger><SelectValue placeholder="Vyberte" /></SelectTrigger><SelectContent>{vehicles.map(v => <SelectItem key={v.vehicle_id} value={v.vehicle_id}>{v.brand} {v.model} ({v.registration_plate})</SelectItem>)}</SelectContent></Select></div>
            <div><Label>Datum *</Label><Input type="date" value={formData.date} onChange={(e) => setFormData({ ...formData, date: e.target.value })} required /></div>
            <div><Label>Tachometr (km) *</Label><Input type="number" min="0" value={formData.odometer} onChange={(e) => setFormData({ ...formData, odometer: parseInt(e.target.value) || 0 })} required /></div>
            <div className="grid grid-cols-2 gap-4">
              <div><Label>Litry *</Label><Input type="number" min="0" step="0.01" value={formData.liters} onChange={(e) => handleLitersChange(parseFloat(e.target.value) || 0)} required /></div>
              <div><Label>Cena/l (Kč) *</Label><Input type="number" min="0" step="0.01" value={formData.price_per_liter} onChange={(e) => handlePriceChange(parseFloat(e.target.value) || 0)} required /></div>
            </div>
            <div className="bg-[#FFC000] p-3 rounded-md text-center"><span className="text-sm">Celkem: </span><span className="font-bold text-lg">{formData.total_price.toLocaleString("cs-CZ")} Kč</span></div>
            <div><Label>Čerpací stanice</Label><Input value={formData.fuel_station} onChange={(e) => setFormData({ ...formData, fuel_station: e.target.value })} /></div>
            <DialogFooter><Button type="button" variant="outline" onClick={() => setShowModal(false)}>Zrušit</Button><Button type="submit" className="bg-[#002FA7] hover:bg-[#002480]" disabled={!formData.vehicle_id}>Uložit</Button></DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
