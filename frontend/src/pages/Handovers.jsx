import { useState, useEffect } from "react";
import axios from "axios";
import { API } from "../App";
import { Handshake, Plus, Eye, Camera, Car } from "@phosphor-icons/react";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Textarea } from "../components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "../components/ui/dialog";
import { toast } from "sonner";

export default function Handovers() {
  const [protocols, setProtocols] = useState([]);
  const [vehicles, setVehicles] = useState([]);
  const [instructors, setInstructors] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [showViewModal, setShowViewModal] = useState(false);
  const [selectedProtocol, setSelectedProtocol] = useState(null);
  const [filters, setFilters] = useState({ vehicle_id: "all", instructor_id: "all" });
  const [formData, setFormData] = useState({
    vehicle_id: "", instructor_id: "", type: "převzetí", odometer: 0, fuel_level: 100,
    exterior_condition: "", interior_condition: "", damages_noted: [], photos: [], notes: ""
  });

  useEffect(() => { fetchData(); }, [filters]);

  const fetchData = async () => {
    try {
      const params = new URLSearchParams();
      if (filters.vehicle_id && filters.vehicle_id !== "all") params.append("vehicle_id", filters.vehicle_id);
      if (filters.instructor_id && filters.instructor_id !== "all") params.append("instructor_id", filters.instructor_id);
      const [protocolsRes, vehiclesRes, instructorsRes] = await Promise.all([
        axios.get(`${API}/handovers?${params}`, { withCredentials: true }),
        axios.get(`${API}/vehicles`, { withCredentials: true }),
        axios.get(`${API}/instructors`, { withCredentials: true })
      ]);
      setProtocols(protocolsRes.data);
      setVehicles(vehiclesRes.data);
      setInstructors(instructorsRes.data);
    } catch (error) { toast.error("Nepodařilo se načíst protokoly"); } 
    finally { setLoading(false); }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      await axios.post(`${API}/handovers`, formData, { withCredentials: true });
      toast.success("Protokol vytvořen");
      setShowModal(false); resetForm(); fetchData();
    } catch (error) { toast.error("Nepodařilo se vytvořit protokol"); }
  };

  const resetForm = () => {
    const v = vehicles[0];
    setFormData({
      vehicle_id: v?.vehicle_id || "", instructor_id: instructors[0]?.instructor_id || "", type: "převzetí",
      odometer: v?.odometer || 0, fuel_level: 100, exterior_condition: "", interior_condition: "",
      damages_noted: [], photos: [], notes: ""
    });
  };

  const handleVehicleChange = (vehicleId) => {
    const v = vehicles.find(x => x.vehicle_id === vehicleId);
    setFormData({ ...formData, vehicle_id: vehicleId, odometer: v?.odometer || 0, instructor_id: v?.assigned_instructor_id || formData.instructor_id });
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

  if (loading) return <div className="flex items-center justify-center h-64"><div className="loading-spinner"></div></div>;

  return (
    <div className="space-y-6" data-testid="handovers-page">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="font-['Manrope'] text-2xl lg:text-3xl font-bold text-[#18181B] tracking-tight">Předávací protokoly</h1>
          <p className="text-[#52525B] mt-1">Evidence převzetí a předání vozidel</p>
        </div>
        <Button onClick={() => { resetForm(); setShowModal(true); }} className="bg-[#002FA7] hover:bg-[#002480]" data-testid="add-handover-btn"><Plus size={20} className="mr-2" />Nový protokol</Button>
      </div>

      <div className="bg-white border border-[#E4E4E7] rounded-md p-4">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div><Label>Vozidlo</Label><Select value={filters.vehicle_id} onValueChange={(v) => setFilters({ ...filters, vehicle_id: v })}><SelectTrigger><SelectValue placeholder="Všechna" /></SelectTrigger><SelectContent><SelectItem value="all">Všechna</SelectItem>{vehicles.map(v => <SelectItem key={v.vehicle_id} value={v.vehicle_id}>{v.brand} {v.model}</SelectItem>)}</SelectContent></Select></div>
          <div><Label>Instruktor</Label><Select value={filters.instructor_id} onValueChange={(v) => setFilters({ ...filters, instructor_id: v })}><SelectTrigger><SelectValue placeholder="Všichni" /></SelectTrigger><SelectContent><SelectItem value="all">Všichni</SelectItem>{instructors.map(i => <SelectItem key={i.instructor_id} value={i.instructor_id}>{i.name}</SelectItem>)}</SelectContent></Select></div>
          <div className="flex items-end"><Button variant="outline" onClick={() => setFilters({ vehicle_id: "all", instructor_id: "all" })} className="w-full">Vymazat</Button></div>
        </div>
      </div>

      {protocols.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {protocols.map(p => (
            <div key={p.handover_id} className="bg-white border border-[#E4E4E7] rounded-md p-6 card-hover">
              <div className="flex items-start justify-between mb-4">
                <div className="flex items-center gap-3">
                  <div className={`w-10 h-10 rounded-full flex items-center justify-center ${p.type === "převzetí" ? "bg-[#DCFCE7]" : "bg-[#FEF3C7]"}`}>
                    <Handshake size={20} weight="duotone" className={p.type === "převzetí" ? "text-[#16A34A]" : "text-[#92400E]"} />
                  </div>
                  <div>
                    <h3 className="font-semibold text-[#18181B] capitalize">{p.type}</h3>
                    <p className="text-sm text-[#52525B]">{new Date(p.created_at).toLocaleDateString("cs-CZ")}</p>
                  </div>
                </div>
              </div>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between"><span className="text-[#52525B]">Vozidlo</span><span className="font-medium">{p.vehicle_info}</span></div>
                <div className="flex justify-between"><span className="text-[#52525B]">Instruktor</span><span className="font-medium">{p.instructor_name}</span></div>
                <div className="flex justify-between"><span className="text-[#52525B]">Tachometr</span><span className="font-medium">{p.odometer?.toLocaleString("cs-CZ")} km</span></div>
                <div className="flex justify-between"><span className="text-[#52525B]">Palivo</span><span className="font-medium">{p.fuel_level}%</span></div>
              </div>
              {p.photos?.length > 0 && (
                <div className="mt-4 flex gap-2">
                  {p.photos.slice(0, 3).map((photo, i) => <img key={i} src={photo} alt="" className="w-16 h-16 object-cover rounded-md border" />)}
                  {p.photos.length > 3 && <div className="w-16 h-16 bg-[#F4F4F5] rounded-md flex items-center justify-center text-sm">+{p.photos.length - 3}</div>}
                </div>
              )}
              <div className="mt-4 pt-4 border-t border-[#E4E4E7]">
                <Button variant="outline" size="sm" onClick={() => { setSelectedProtocol(p); setShowViewModal(true); }} className="w-full"><Eye size={16} className="mr-1" />Detail</Button>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="bg-white border border-[#E4E4E7] rounded-md p-12 text-center">
          <Handshake size={48} weight="duotone" className="mx-auto text-[#A1A1AA] mb-4" />
          <h3 className="font-semibold text-[#18181B] mb-2">Žádné protokoly</h3>
          <Button onClick={() => { resetForm(); setShowModal(true); }} className="bg-[#002FA7] hover:bg-[#002480]"><Plus size={20} className="mr-2" />Nový protokol</Button>
        </div>
      )}

      <Dialog open={showModal} onOpenChange={setShowModal}>
        <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Nový předávací protokol</DialogTitle></DialogHeader>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div><Label>Vozidlo *</Label><Select value={formData.vehicle_id} onValueChange={handleVehicleChange}><SelectTrigger><SelectValue placeholder="Vyberte" /></SelectTrigger><SelectContent>{vehicles.map(v => <SelectItem key={v.vehicle_id} value={v.vehicle_id}>{v.brand} {v.model}</SelectItem>)}</SelectContent></Select></div>
              <div><Label>Instruktor *</Label><Select value={formData.instructor_id} onValueChange={(v) => setFormData({ ...formData, instructor_id: v })}><SelectTrigger><SelectValue placeholder="Vyberte" /></SelectTrigger><SelectContent>{instructors.map(i => <SelectItem key={i.instructor_id} value={i.instructor_id}>{i.name}</SelectItem>)}</SelectContent></Select></div>
            </div>
            <div><Label>Typ *</Label><Select value={formData.type} onValueChange={(v) => setFormData({ ...formData, type: v })}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="převzetí">Převzetí</SelectItem><SelectItem value="předání">Předání</SelectItem></SelectContent></Select></div>
            <div className="grid grid-cols-2 gap-4">
              <div><Label>Tachometr (km) *</Label><Input type="number" min="0" value={formData.odometer} onChange={(e) => setFormData({ ...formData, odometer: parseInt(e.target.value) || 0 })} required /></div>
              <div><Label>Palivo (%) *</Label><Input type="number" min="0" max="100" value={formData.fuel_level} onChange={(e) => setFormData({ ...formData, fuel_level: parseInt(e.target.value) || 0 })} required /></div>
            </div>
            <div><Label>Stav exteriéru *</Label><Textarea value={formData.exterior_condition} onChange={(e) => setFormData({ ...formData, exterior_condition: e.target.value })} required rows={2} placeholder="Popište stav karoserie..." /></div>
            <div><Label>Stav interiéru *</Label><Textarea value={formData.interior_condition} onChange={(e) => setFormData({ ...formData, interior_condition: e.target.value })} required rows={2} placeholder="Popište stav interiéru..." /></div>
            <div><Label>Fotografie</Label><Input type="file" accept="image/*" multiple onChange={handlePhotoUpload} />
              {formData.photos.length > 0 && <div className="flex gap-2 mt-2 flex-wrap">{formData.photos.map((p, i) => <img key={i} src={p} alt="" className="w-16 h-16 object-cover rounded-md border" />)}</div>}
            </div>
            <div><Label>Poznámky</Label><Textarea value={formData.notes} onChange={(e) => setFormData({ ...formData, notes: e.target.value })} rows={2} /></div>
            <DialogFooter><Button type="button" variant="outline" onClick={() => setShowModal(false)}>Zrušit</Button><Button type="submit" className="bg-[#002FA7] hover:bg-[#002480]" disabled={!formData.vehicle_id || !formData.instructor_id}>Vytvořit</Button></DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={showViewModal} onOpenChange={setShowViewModal}>
        <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Detail protokolu</DialogTitle></DialogHeader>
          {selectedProtocol && (
            <div className="space-y-4">
              <div className="flex items-center gap-3">
                <div className={`w-10 h-10 rounded-full flex items-center justify-center ${selectedProtocol.type === "převzetí" ? "bg-[#DCFCE7]" : "bg-[#FEF3C7]"}`}>
                  <Handshake size={20} weight="duotone" className={selectedProtocol.type === "převzetí" ? "text-[#16A34A]" : "text-[#92400E]"} />
                </div>
                <div><h3 className="font-semibold capitalize">{selectedProtocol.type}</h3><p className="text-sm text-[#52525B]">{new Date(selectedProtocol.created_at).toLocaleString("cs-CZ")}</p></div>
              </div>
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div><p className="text-[#52525B]">Vozidlo</p><p className="font-medium">{selectedProtocol.vehicle_info}</p></div>
                <div><p className="text-[#52525B]">Instruktor</p><p className="font-medium">{selectedProtocol.instructor_name}</p></div>
                <div><p className="text-[#52525B]">Tachometr</p><p className="font-medium">{selectedProtocol.odometer?.toLocaleString("cs-CZ")} km</p></div>
                <div><p className="text-[#52525B]">Palivo</p><p className="font-medium">{selectedProtocol.fuel_level}%</p></div>
              </div>
              <div><p className="text-sm text-[#52525B]">Stav exteriéru</p><p className="font-medium">{selectedProtocol.exterior_condition}</p></div>
              <div><p className="text-sm text-[#52525B]">Stav interiéru</p><p className="font-medium">{selectedProtocol.interior_condition}</p></div>
              {selectedProtocol.notes && <div><p className="text-sm text-[#52525B]">Poznámky</p><p className="font-medium">{selectedProtocol.notes}</p></div>}
              {selectedProtocol.photos?.length > 0 && <div><p className="text-sm text-[#52525B] mb-2">Fotografie</p><div className="grid grid-cols-2 gap-2">{selectedProtocol.photos.map((p, i) => <img key={i} src={p} alt="" className="w-full h-40 object-cover rounded-md border" />)}</div></div>}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
