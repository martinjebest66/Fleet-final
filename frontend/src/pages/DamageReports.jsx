import { useState, useEffect } from "react";
import axios from "axios";
import { API } from "../App";
import { Warning, Plus, Eye, Check, X } from "@phosphor-icons/react";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Textarea } from "../components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "../components/ui/dialog";
import { toast } from "sonner";

export default function DamageReports() {
  const [reports, setReports] = useState([]);
  const [vehicles, setVehicles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [showViewModal, setShowViewModal] = useState(false);
  const [selectedReport, setSelectedReport] = useState(null);
  const [filters, setFilters] = useState({ vehicle_id: "", status: "" });
  const [formData, setFormData] = useState({ vehicle_id: "", description: "", severity: "střední", location_on_vehicle: "", photos: [], reported_by: "", notes: "" });

  useEffect(() => { fetchData(); }, [filters]);

  const fetchData = async () => {
    try {
      const params = new URLSearchParams();
      if (filters.vehicle_id) params.append("vehicle_id", filters.vehicle_id);
      if (filters.status) params.append("status", filters.status);
      const [reportsRes, vehiclesRes] = await Promise.all([
        axios.get(`${API}/damages?${params}`, { withCredentials: true }),
        axios.get(`${API}/vehicles`, { withCredentials: true })
      ]);
      setReports(reportsRes.data);
      setVehicles(vehiclesRes.data);
    } catch (error) { toast.error("Nepodařilo se načíst hlášení"); } 
    finally { setLoading(false); }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      await axios.post(`${API}/damages`, formData, { withCredentials: true });
      toast.success("Poškození nahlášeno");
      setShowModal(false); resetForm(); fetchData();
    } catch (error) { toast.error("Nepodařilo se nahlásit"); }
  };

  const handleStatusChange = async (damageId, newStatus) => {
    try {
      await axios.put(`${API}/damages/${damageId}/status?status=${newStatus}`, {}, { withCredentials: true });
      toast.success("Status aktualizován"); fetchData();
    } catch (error) { toast.error("Nepodařilo se aktualizovat"); }
  };

  const resetForm = () => {
    setFormData({ vehicle_id: vehicles[0]?.vehicle_id || "", description: "", severity: "střední", location_on_vehicle: "", photos: [], reported_by: "", notes: "" });
  };

  const handlePhotoUpload = async (e) => {
    const files = Array.from(e.target.files);
    for (const file of files) {
      const fd = new FormData(); fd.append("file", file);
      try {
        const res = await axios.post(`${API}/upload`, fd, { withCredentials: true, headers: { "Content-Type": "multipart/form-data" } });
        setFormData(prev => ({ ...prev, photos: [...prev.photos, res.data.url] }));
      } catch (error) { toast.error(`Nepodařilo se nahrát ${file.name}`); }
    }
  };

  const getSeverityBadge = (s) => ({ nízká: "badge-success", střední: "badge-warning", vysoká: "badge-danger" }[s] || "badge-info");
  const getStatusBadge = (s) => ({ otevřeno: "badge-danger", "v řešení": "badge-warning", vyřešeno: "badge-success" }[s] || "badge-info");
  const openDamages = reports.filter(r => r.status !== "vyřešeno").length;

  if (loading) return <div className="flex items-center justify-center h-64"><div className="loading-spinner"></div></div>;

  return (
    <div className="space-y-6" data-testid="damages-page">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="font-['Manrope'] text-2xl lg:text-3xl font-bold text-[#18181B] tracking-tight">Hlášení poškození</h1>
          <p className="text-[#52525B] mt-1">Evidence poškození vozidel</p>
        </div>
        <Button onClick={() => { resetForm(); setShowModal(true); }} className="bg-[#002FA7] hover:bg-[#002480]" data-testid="add-damage-btn"><Plus size={20} className="mr-2" />Nahlásit poškození</Button>
      </div>

      <div className="bg-white border border-[#E4E4E7] rounded-md p-4">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div><Label>Vozidlo</Label><Select value={filters.vehicle_id} onValueChange={(v) => setFilters({ ...filters, vehicle_id: v })}><SelectTrigger><SelectValue placeholder="Všechna" /></SelectTrigger><SelectContent><SelectItem value="">Všechna</SelectItem>{vehicles.map(v => <SelectItem key={v.vehicle_id} value={v.vehicle_id}>{v.brand} {v.model}</SelectItem>)}</SelectContent></Select></div>
          <div><Label>Status</Label><Select value={filters.status} onValueChange={(v) => setFilters({ ...filters, status: v })}><SelectTrigger><SelectValue placeholder="Všechny" /></SelectTrigger><SelectContent><SelectItem value="">Všechny</SelectItem><SelectItem value="otevřeno">Otevřeno</SelectItem><SelectItem value="v řešení">V řešení</SelectItem><SelectItem value="vyřešeno">Vyřešeno</SelectItem></SelectContent></Select></div>
          <div className="flex items-end"><Button variant="outline" onClick={() => setFilters({ vehicle_id: "", status: "" })} className="w-full">Vymazat</Button></div>
        </div>
      </div>

      {openDamages > 0 && (
        <div className="bg-[#FF2400] text-white rounded-md p-4 flex items-center gap-4">
          <Warning size={32} weight="fill" />
          <div><p className="text-sm opacity-80">Nevyřešená poškození</p><p className="text-2xl font-bold">{openDamages}</p></div>
        </div>
      )}

      {reports.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {reports.map(r => (
            <div key={r.damage_id} className="bg-white border border-[#E4E4E7] rounded-md p-6 card-hover">
              <div className="flex items-start justify-between mb-4">
                <div><p className="text-sm text-[#52525B]">{r.vehicle_info}</p><h3 className="font-semibold text-[#18181B] mt-1 line-clamp-2">{r.description}</h3></div>
                <span className={`badge ${getSeverityBadge(r.severity)}`}>{r.severity}</span>
              </div>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between"><span className="text-[#52525B]">Umístění</span><span className="font-medium">{r.location_on_vehicle}</span></div>
                <div className="flex justify-between"><span className="text-[#52525B]">Nahlášeno</span><span className="font-medium">{new Date(r.created_at).toLocaleDateString("cs-CZ")}</span></div>
                <div className="flex justify-between items-center"><span className="text-[#52525B]">Status</span><span className={`badge ${getStatusBadge(r.status)}`}>{r.status}</span></div>
              </div>
              {r.photos?.length > 0 && (
                <div className="mt-4 flex gap-2">
                  {r.photos.slice(0, 3).map((p, i) => <img key={i} src={p} alt="" className="w-16 h-16 object-cover rounded-md border" />)}
                  {r.photos.length > 3 && <div className="w-16 h-16 bg-[#F4F4F5] rounded-md flex items-center justify-center text-sm">+{r.photos.length - 3}</div>}
                </div>
              )}
              <div className="flex gap-2 mt-4 pt-4 border-t border-[#E4E4E7]">
                <Button variant="outline" size="sm" onClick={() => { setSelectedReport(r); setShowViewModal(true); }} className="flex-1"><Eye size={16} className="mr-1" />Detail</Button>
                {r.status === "otevřeno" && <Button variant="outline" size="sm" onClick={() => handleStatusChange(r.damage_id, "v řešení")} className="flex-1">V řešení</Button>}
                {r.status === "v řešení" && <Button size="sm" onClick={() => handleStatusChange(r.damage_id, "vyřešeno")} className="flex-1 bg-[#16A34A] hover:bg-[#15803D]"><Check size={16} className="mr-1" />Vyřešit</Button>}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="bg-white border border-[#E4E4E7] rounded-md p-12 text-center">
          <Warning size={48} weight="duotone" className="mx-auto text-[#A1A1AA] mb-4" />
          <h3 className="font-semibold text-[#18181B] mb-2">Žádná hlášení</h3>
        </div>
      )}

      <Dialog open={showModal} onOpenChange={setShowModal}>
        <DialogContent className="max-w-md max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Nahlásit poškození</DialogTitle></DialogHeader>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div><Label>Vozidlo *</Label><Select value={formData.vehicle_id} onValueChange={(v) => setFormData({ ...formData, vehicle_id: v })}><SelectTrigger><SelectValue placeholder="Vyberte" /></SelectTrigger><SelectContent>{vehicles.map(v => <SelectItem key={v.vehicle_id} value={v.vehicle_id}>{v.brand} {v.model}</SelectItem>)}</SelectContent></Select></div>
            <div><Label>Popis *</Label><Textarea value={formData.description} onChange={(e) => setFormData({ ...formData, description: e.target.value })} required rows={3} /></div>
            <div><Label>Závažnost *</Label><Select value={formData.severity} onValueChange={(v) => setFormData({ ...formData, severity: v })}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="nízká">Nízká</SelectItem><SelectItem value="střední">Střední</SelectItem><SelectItem value="vysoká">Vysoká</SelectItem></SelectContent></Select></div>
            <div><Label>Umístění *</Label><Input value={formData.location_on_vehicle} onChange={(e) => setFormData({ ...formData, location_on_vehicle: e.target.value })} required /></div>
            <div><Label>Fotografie</Label><Input type="file" accept="image/*" multiple onChange={handlePhotoUpload} />
              {formData.photos.length > 0 && <div className="flex gap-2 mt-2 flex-wrap">{formData.photos.map((p, i) => <div key={i} className="relative"><img src={p} alt="" className="w-16 h-16 object-cover rounded-md border" /><button type="button" onClick={() => setFormData({ ...formData, photos: formData.photos.filter((_, idx) => idx !== i) })} className="absolute -top-2 -right-2 w-5 h-5 bg-[#FF2400] text-white rounded-full flex items-center justify-center text-xs"><X size={12} /></button></div>)}</div>}
            </div>
            <div><Label>Nahlásil</Label><Input value={formData.reported_by} onChange={(e) => setFormData({ ...formData, reported_by: e.target.value })} /></div>
            <DialogFooter><Button type="button" variant="outline" onClick={() => setShowModal(false)}>Zrušit</Button><Button type="submit" className="bg-[#002FA7] hover:bg-[#002480]" disabled={!formData.vehicle_id || !formData.description}>Nahlásit</Button></DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={showViewModal} onOpenChange={setShowViewModal}>
        <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Detail poškození</DialogTitle></DialogHeader>
          {selectedReport && (
            <div className="space-y-4">
              <div className="flex justify-between items-start"><div><p className="text-sm text-[#52525B]">{selectedReport.vehicle_info}</p><p className="font-semibold">{selectedReport.description}</p></div><span className={`badge ${getSeverityBadge(selectedReport.severity)}`}>{selectedReport.severity}</span></div>
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div><p className="text-[#52525B]">Umístění</p><p className="font-medium">{selectedReport.location_on_vehicle}</p></div>
                <div><p className="text-[#52525B]">Status</p><span className={`badge ${getStatusBadge(selectedReport.status)}`}>{selectedReport.status}</span></div>
                <div><p className="text-[#52525B]">Nahlášeno</p><p className="font-medium">{new Date(selectedReport.created_at).toLocaleString("cs-CZ")}</p></div>
                {selectedReport.reported_by && <div><p className="text-[#52525B]">Nahlásil</p><p className="font-medium">{selectedReport.reported_by}</p></div>}
              </div>
              {selectedReport.photos?.length > 0 && <div><p className="text-sm text-[#52525B] mb-2">Fotografie</p><div className="grid grid-cols-2 gap-2">{selectedReport.photos.map((p, i) => <img key={i} src={p} alt="" className="w-full h-40 object-cover rounded-md border" />)}</div></div>}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
