import { useState, useEffect } from "react";
import axios from "axios";
import { API } from "../App";
import { BookOpen, Plus, Trash, Download, Gps } from "@phosphor-icons/react";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "../components/ui/dialog";
import { format } from "date-fns";
import { toast } from "sonner";

export default function Logbook() {
  const [entries, setEntries] = useState([]);
  const [vehicles, setVehicles] = useState([]);
  const [instructors, setInstructors] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [filters, setFilters] = useState({ vehicle_id: "", instructor_id: "", date_from: "", date_to: "" });
  const [formData, setFormData] = useState({
    vehicle_id: "", instructor_id: "", date: format(new Date(), "yyyy-MM-dd"),
    start_time: "08:00", end_time: "09:00", start_location: "", end_location: "",
    route_description: "", start_odometer: 0, end_odometer: 0, purpose: "výcvik", notes: ""
  });

  useEffect(() => { fetchData(); }, [filters]);

  const fetchData = async () => {
    try {
      const params = new URLSearchParams();
      if (filters.vehicle_id) params.append("vehicle_id", filters.vehicle_id);
      if (filters.instructor_id) params.append("instructor_id", filters.instructor_id);
      if (filters.date_from) params.append("date_from", filters.date_from);
      if (filters.date_to) params.append("date_to", filters.date_to);

      const [entriesRes, vehiclesRes, instructorsRes] = await Promise.all([
        axios.get(`${API}/logbook?${params}`, { withCredentials: true }),
        axios.get(`${API}/vehicles`, { withCredentials: true }),
        axios.get(`${API}/instructors`, { withCredentials: true })
      ]);
      setEntries(entriesRes.data);
      setVehicles(vehiclesRes.data);
      setInstructors(instructorsRes.data);
    } catch (error) { toast.error("Nepodařilo se načíst knihu jízd"); } 
    finally { setLoading(false); }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (formData.end_odometer < formData.start_odometer) {
      toast.error("Koncový stav tachometru nesmí být menší než počáteční"); return;
    }
    try {
      await axios.post(`${API}/logbook`, { ...formData, instructor_id: formData.instructor_id || null }, { withCredentials: true });
      toast.success("Záznam přidán");
      setShowModal(false); resetForm(); fetchData();
    } catch (error) { toast.error("Nepodařilo se přidat záznam"); }
  };

  const handleDelete = async (entryId) => {
    if (!window.confirm("Smazat záznam?")) return;
    try {
      await axios.delete(`${API}/logbook/${entryId}`, { withCredentials: true });
      toast.success("Záznam smazán"); fetchData();
    } catch (error) { toast.error("Nepodařilo se smazat záznam"); }
  };

  const resetForm = () => {
    const v = vehicles[0];
    setFormData({
      vehicle_id: v?.vehicle_id || "", instructor_id: "", date: format(new Date(), "yyyy-MM-dd"),
      start_time: "08:00", end_time: "09:00", start_location: "", end_location: "",
      route_description: "", start_odometer: v?.odometer || 0, end_odometer: v?.odometer || 0, purpose: "výcvik", notes: ""
    });
  };

  const handleVehicleChange = (vehicleId) => {
    const v = vehicles.find(x => x.vehicle_id === vehicleId);
    setFormData({ ...formData, vehicle_id: vehicleId, start_odometer: v?.odometer || 0, end_odometer: v?.odometer || 0, instructor_id: v?.assigned_instructor_id || "" });
  };

  const exportToCSV = () => {
    const headers = ["Datum", "Vozidlo", "Instruktor", "Začátek", "Konec", "Odkud", "Kam", "Vzdálenost", "Účel"];
    const rows = entries.map(e => [e.date, e.vehicle_info || "", e.instructor_name || "", e.start_time, e.end_time, e.start_location, e.end_location, `${e.distance} km`, e.purpose]);
    const csv = [headers, ...rows].map(row => row.join(";")).join("\n");
    const blob = new Blob(["\uFEFF" + csv], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = `kniha-jizd-${format(new Date(), "yyyy-MM-dd")}.csv`; a.click();
  };

  const totalDistance = entries.reduce((sum, e) => sum + (e.distance || 0), 0);

  if (loading) return <div className="flex items-center justify-center h-64"><div className="loading-spinner"></div></div>;

  return (
    <div className="space-y-6" data-testid="logbook-page">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="font-['Manrope'] text-2xl lg:text-3xl font-bold text-[#18181B] tracking-tight">Kniha jízd</h1>
          <p className="text-[#52525B] mt-1">Záznamy o jízdách vozidel</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={exportToCSV} disabled={entries.length === 0}><Download size={20} className="mr-2" />Export CSV</Button>
          <Button onClick={() => { resetForm(); setShowModal(true); }} className="bg-[#002FA7] hover:bg-[#002480]" data-testid="add-entry-btn"><Plus size={20} className="mr-2" />Nový záznam</Button>
        </div>
      </div>

      <div className="bg-white border border-[#E4E4E7] rounded-md p-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
          <div>
            <Label>Vozidlo</Label>
            <Select value={filters.vehicle_id} onValueChange={(v) => setFilters({ ...filters, vehicle_id: v })}>
              <SelectTrigger><SelectValue placeholder="Všechna vozidla" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="">Všechna</SelectItem>
                {vehicles.map(v => <SelectItem key={v.vehicle_id} value={v.vehicle_id}>{v.brand} {v.model}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label>Instruktor</Label>
            <Select value={filters.instructor_id} onValueChange={(v) => setFilters({ ...filters, instructor_id: v })}>
              <SelectTrigger><SelectValue placeholder="Všichni" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="">Všichni</SelectItem>
                {instructors.map(i => <SelectItem key={i.instructor_id} value={i.instructor_id}>{i.name}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div><Label>Od</Label><Input type="date" value={filters.date_from} onChange={(e) => setFilters({ ...filters, date_from: e.target.value })} /></div>
          <div><Label>Do</Label><Input type="date" value={filters.date_to} onChange={(e) => setFilters({ ...filters, date_to: e.target.value })} /></div>
          <div className="flex items-end"><Button variant="outline" onClick={() => setFilters({ vehicle_id: "", instructor_id: "", date_from: "", date_to: "" })} className="w-full">Vymazat</Button></div>
        </div>
      </div>

      <div className="bg-[#002FA7] text-white rounded-md p-4 flex items-center justify-between">
        <div><p className="text-sm opacity-80">Celková vzdálenost</p><p className="text-2xl font-bold">{totalDistance.toLocaleString("cs-CZ")} km</p></div>
        <div className="text-right"><p className="text-sm opacity-80">Počet záznamů</p><p className="text-2xl font-bold">{entries.length}</p></div>
      </div>

      {entries.length > 0 ? (
        <div className="bg-white border border-[#E4E4E7] rounded-md overflow-hidden">
          <div className="overflow-x-auto">
            <table className="data-table">
              <thead><tr><th>Datum</th><th>Čas</th><th>Vozidlo</th><th>Instruktor</th><th>Trasa</th><th>Vzdálenost</th><th>Účel</th><th>Zdroj</th><th></th></tr></thead>
              <tbody>
                {entries.map(e => (
                  <tr key={e.entry_id}>
                    <td className="font-medium">{e.date}</td>
                    <td>{e.start_time} - {e.end_time}</td>
                    <td>{e.vehicle_info || "-"}</td>
                    <td>{e.instructor_name || "-"}</td>
                    <td className="max-w-xs"><div className="truncate">{e.start_location}</div><div className="text-xs text-[#52525B]">→ {e.end_location}</div></td>
                    <td className="font-semibold">{e.distance} km</td>
                    <td><span className={`badge ${e.purpose === "výcvik" ? "badge-info" : e.purpose === "služební" ? "badge-warning" : "badge-success"}`}>{e.purpose}</span></td>
                    <td>{e.gps_source ? <span className="flex items-center gap-1 text-xs text-[#16A34A]"><Gps size={14} />GPS</span> : <span className="text-xs text-[#52525B]">Manuální</span>}</td>
                    <td><Button variant="ghost" size="sm" onClick={() => handleDelete(e.entry_id)} className="text-[#991B1B] hover:bg-red-50"><Trash size={16} /></Button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <div className="bg-white border border-[#E4E4E7] rounded-md p-12 text-center">
          <BookOpen size={48} weight="duotone" className="mx-auto text-[#A1A1AA] mb-4" />
          <h3 className="font-semibold text-[#18181B] mb-2">Žádné záznamy</h3>
          <Button onClick={() => { resetForm(); setShowModal(true); }} className="bg-[#002FA7] hover:bg-[#002480]"><Plus size={20} className="mr-2" />Nový záznam</Button>
        </div>
      )}

      <Dialog open={showModal} onOpenChange={setShowModal}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Nový záznam do knihy jízd</DialogTitle></DialogHeader>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div><Label>Vozidlo *</Label><Select value={formData.vehicle_id} onValueChange={handleVehicleChange}><SelectTrigger><SelectValue placeholder="Vyberte" /></SelectTrigger><SelectContent>{vehicles.map(v => <SelectItem key={v.vehicle_id} value={v.vehicle_id}>{v.brand} {v.model} ({v.registration_plate})</SelectItem>)}</SelectContent></Select></div>
              <div><Label>Instruktor</Label><Select value={formData.instructor_id} onValueChange={(v) => setFormData({ ...formData, instructor_id: v })}><SelectTrigger><SelectValue placeholder="Vyberte" /></SelectTrigger><SelectContent><SelectItem value="">Bez instruktora</SelectItem>{instructors.map(i => <SelectItem key={i.instructor_id} value={i.instructor_id}>{i.name}</SelectItem>)}</SelectContent></Select></div>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div><Label>Datum *</Label><Input type="date" value={formData.date} onChange={(e) => setFormData({ ...formData, date: e.target.value })} required /></div>
              <div><Label>Čas odjezdu *</Label><Input type="time" value={formData.start_time} onChange={(e) => setFormData({ ...formData, start_time: e.target.value })} required /></div>
              <div><Label>Čas příjezdu *</Label><Input type="time" value={formData.end_time} onChange={(e) => setFormData({ ...formData, end_time: e.target.value })} required /></div>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div><Label>Místo odjezdu *</Label><Input value={formData.start_location} onChange={(e) => setFormData({ ...formData, start_location: e.target.value })} required /></div>
              <div><Label>Místo příjezdu *</Label><Input value={formData.end_location} onChange={(e) => setFormData({ ...formData, end_location: e.target.value })} required /></div>
            </div>
            <div><Label>Popis trasy</Label><Input value={formData.route_description} onChange={(e) => setFormData({ ...formData, route_description: e.target.value })} /></div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div><Label>Tachometr - odjezd (km) *</Label><Input type="number" min="0" value={formData.start_odometer} onChange={(e) => setFormData({ ...formData, start_odometer: parseInt(e.target.value) || 0 })} required /></div>
              <div><Label>Tachometr - příjezd (km) *</Label><Input type="number" min="0" value={formData.end_odometer} onChange={(e) => setFormData({ ...formData, end_odometer: parseInt(e.target.value) || 0 })} required /></div>
            </div>
            <div className="bg-[#F4F4F5] p-3 rounded-md text-center"><span className="text-sm text-[#52525B]">Vzdálenost: </span><span className="font-bold text-[#18181B]">{Math.max(0, formData.end_odometer - formData.start_odometer)} km</span></div>
            <div><Label>Účel jízdy *</Label><Select value={formData.purpose} onValueChange={(v) => setFormData({ ...formData, purpose: v })}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="výcvik">Výcvik</SelectItem><SelectItem value="služební">Služební</SelectItem><SelectItem value="soukromá">Soukromá</SelectItem></SelectContent></Select></div>
            <div><Label>Poznámky</Label><Input value={formData.notes} onChange={(e) => setFormData({ ...formData, notes: e.target.value })} /></div>
            <DialogFooter><Button type="button" variant="outline" onClick={() => setShowModal(false)}>Zrušit</Button><Button type="submit" className="bg-[#002FA7] hover:bg-[#002480]" disabled={!formData.vehicle_id}>Přidat záznam</Button></DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
