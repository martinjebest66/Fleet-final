import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { API } from "../App";
import { Wrench, Plus, Trash, PencilSimple, CalendarCheck, Warning, CheckCircle, Clock } from "@phosphor-icons/react";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Textarea } from "../components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "../components/ui/dialog";
import { toast } from "sonner";

const MAINTENANCE_TYPES = [
  { value: "STK", label: "STK (Technická kontrola)" },
  { value: "olej", label: "Výměna oleje" },
  { value: "pneumatiky", label: "Pneumatiky" },
  { value: "brzdy", label: "Brzdové destičky" },
  { value: "rozvodový řemen", label: "Rozvodový řemen" },
  { value: "vlastní", label: "Vlastní položka" },
];

const STATUS_CONFIG = {
  "ok": { label: "V pořádku", color: "bg-emerald-100 text-emerald-700", icon: CheckCircle },
  "blíží se": { label: "Blíží se", color: "bg-amber-100 text-amber-700", icon: Clock },
  "po termínu": { label: "Po termínu", color: "bg-red-100 text-red-700", icon: Warning },
};

const emptyForm = {
  vehicle_id: "", type: "STK", custom_label: "", last_done_date: "", last_done_odometer: "",
  interval_months: "", interval_km: "", next_due_date: "", next_due_odometer: "", notes: ""
};

export default function Maintenance() {
  const [items, setItems] = useState([]);
  const [vehicles, setVehicles] = useState([]);
  const [summary, setSummary] = useState({ total: 0, overdue: 0, upcoming: 0, ok: 0 });
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [filterVehicle, setFilterVehicle] = useState("");
  const [filterStatus, setFilterStatus] = useState("");
  const [formData, setFormData] = useState(emptyForm);

  const fetchData = useCallback(async () => {
    try {
      const params = new URLSearchParams();
      if (filterVehicle && filterVehicle !== "all") params.append("vehicle_id", filterVehicle);
      if (filterStatus && filterStatus !== "all") params.append("status", filterStatus);
      const [itemsRes, vehiclesRes, summaryRes] = await Promise.all([
        axios.get(`${API}/maintenance?${params}`, { withCredentials: true }),
        axios.get(`${API}/vehicles`, { withCredentials: true }),
        axios.get(`${API}/maintenance/summary`, { withCredentials: true })
      ]);
      setItems(itemsRes.data);
      setVehicles(vehiclesRes.data);
      setSummary(summaryRes.data);
    } catch { toast.error("Nepodařilo se načíst údržbu"); }
    finally { setLoading(false); }
  }, [filterVehicle, filterStatus]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const openNew = () => { setEditingId(null); setFormData(emptyForm); setShowModal(true); };
  const openEdit = (item) => {
    setEditingId(item.maintenance_id);
    setFormData({
      vehicle_id: item.vehicle_id, type: item.type, custom_label: item.custom_label || "",
      last_done_date: item.last_done_date || "", last_done_odometer: item.last_done_odometer || "",
      interval_months: item.interval_months || "", interval_km: item.interval_km || "",
      next_due_date: item.next_due_date || "", next_due_odometer: item.next_due_odometer || "", notes: item.notes || ""
    });
    setShowModal(true);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    const payload = {
      ...formData,
      last_done_odometer: formData.last_done_odometer ? parseInt(formData.last_done_odometer) : null,
      interval_months: formData.interval_months ? parseInt(formData.interval_months) : null,
      interval_km: formData.interval_km ? parseInt(formData.interval_km) : null,
      next_due_odometer: formData.next_due_odometer ? parseInt(formData.next_due_odometer) : null,
      last_done_date: formData.last_done_date || null,
      next_due_date: formData.next_due_date || null,
      custom_label: formData.custom_label || null,
      notes: formData.notes || null,
    };
    try {
      if (editingId) {
        await axios.put(`${API}/maintenance/${editingId}`, payload, { withCredentials: true });
        toast.success("Údržba aktualizována");
      } else {
        await axios.post(`${API}/maintenance`, payload, { withCredentials: true });
        toast.success("Údržba vytvořena");
      }
      setShowModal(false); fetchData();
    } catch { toast.error("Nepodařilo se uložit"); }
  };

  const handleDelete = async (id) => {
    if (!window.confirm("Opravdu smazat tento záznam údržby?")) return;
    try {
      await axios.delete(`${API}/maintenance/${id}`, { withCredentials: true });
      toast.success("Smazáno"); fetchData();
    } catch { toast.error("Nepodařilo se smazat"); }
  };

  const getTypeLabel = (type, customLabel) => {
    if (type === "vlastní" && customLabel) return customLabel;
    return MAINTENANCE_TYPES.find(t => t.value === type)?.label || type;
  };

  if (loading) return <div className="flex items-center justify-center h-64"><div className="loading-spinner"></div></div>;

  return (
    <div className="space-y-6" data-testid="maintenance-page">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="font-['Manrope'] text-2xl lg:text-3xl font-bold text-[#18181B] tracking-tight">Údržba vozidel</h1>
          <p className="text-[#52525B] mt-1">Plánování servisních intervalů a kontrol</p>
        </div>
        <Button onClick={openNew} className="bg-[#002FA7] hover:bg-[#002480]" data-testid="add-maintenance-btn">
          <Plus size={20} className="mr-2" />Přidat údržbu
        </Button>
      </div>

      {/* Summary KPIs */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          { label: "Celkem", value: summary.total, icon: Wrench, color: "#002FA7" },
          { label: "V pořádku", value: summary.ok, icon: CheckCircle, color: "#16A34A" },
          { label: "Blíží se", value: summary.upcoming, icon: Clock, color: "#D97706" },
          { label: "Po termínu", value: summary.overdue, icon: Warning, color: "#FF2400" },
        ].map(k => (
          <div key={k.label} className="kpi-card card-hover rounded-md" data-testid={`maintenance-kpi-${k.label.toLowerCase()}`}>
            <k.icon size={24} weight="duotone" style={{ color: k.color }} />
            <div className="mt-3">
              <div className="kpi-value">{k.value}</div>
              <div className="kpi-label">{k.label}</div>
            </div>
          </div>
        ))}
      </div>

      {/* Filters */}
      <div className="bg-white border border-[#E4E4E7] rounded-md p-4">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div>
            <Label>Vozidlo</Label>
            <Select value={filterVehicle} onValueChange={setFilterVehicle}>
              <SelectTrigger><SelectValue placeholder="Všechna" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Všechna</SelectItem>
                {vehicles.map(v => <SelectItem key={v.vehicle_id} value={v.vehicle_id}>{v.brand} {v.model} ({v.registration_plate})</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label>Stav</Label>
            <Select value={filterStatus} onValueChange={setFilterStatus}>
              <SelectTrigger><SelectValue placeholder="Všechny" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Všechny</SelectItem>
                <SelectItem value="ok">V pořádku</SelectItem>
                <SelectItem value="blíží se">Blíží se</SelectItem>
                <SelectItem value="po termínu">Po termínu</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="flex items-end">
            <Button variant="outline" onClick={() => { setFilterVehicle("all"); setFilterStatus("all"); }} className="w-full">Vymazat</Button>
          </div>
        </div>
      </div>

      {/* Maintenance list */}
      {items.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {items.map(item => {
            const sc = STATUS_CONFIG[item.status] || STATUS_CONFIG["ok"];
            const StatusIcon = sc.icon;
            return (
              <div key={item.maintenance_id} className="bg-white border border-[#E4E4E7] rounded-md p-6 card-hover" data-testid={`maintenance-item-${item.maintenance_id}`}>
                <div className="flex items-start justify-between mb-3">
                  <div>
                    <p className="text-sm text-[#52525B]">{item.vehicle_info}</p>
                    <h3 className="font-semibold text-[#18181B] mt-1">{getTypeLabel(item.type, item.custom_label)}</h3>
                  </div>
                  <span className={`inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-1 rounded-full ${sc.color}`}>
                    <StatusIcon size={14} weight="bold" />{sc.label}
                  </span>
                </div>
                <div className="space-y-2 text-sm">
                  {item.next_due_date && (
                    <div className="flex justify-between">
                      <span className="text-[#52525B]">Další termín</span>
                      <span className="font-medium">{new Date(item.next_due_date).toLocaleDateString("cs-CZ")}</span>
                    </div>
                  )}
                  {item.next_due_odometer && (
                    <div className="flex justify-between">
                      <span className="text-[#52525B]">Další km</span>
                      <span className="font-medium">{item.next_due_odometer.toLocaleString("cs-CZ")} km</span>
                    </div>
                  )}
                  {item.last_done_date && (
                    <div className="flex justify-between">
                      <span className="text-[#52525B]">Poslední</span>
                      <span className="font-medium">{new Date(item.last_done_date).toLocaleDateString("cs-CZ")}</span>
                    </div>
                  )}
                  {item.interval_months && (
                    <div className="flex justify-between">
                      <span className="text-[#52525B]">Interval</span>
                      <span className="font-medium">{item.interval_months} měs. / {item.interval_km ? `${item.interval_km.toLocaleString("cs-CZ")} km` : "-"}</span>
                    </div>
                  )}
                </div>
                {item.notes && <p className="text-xs text-[#52525B] mt-3 italic">{item.notes}</p>}
                <div className="flex gap-2 mt-4 pt-4 border-t border-[#E4E4E7]">
                  <Button variant="outline" size="sm" onClick={() => openEdit(item)} className="flex-1" data-testid={`edit-maintenance-${item.maintenance_id}`}>
                    <PencilSimple size={16} className="mr-1" />Upravit
                  </Button>
                  <Button variant="outline" size="sm" onClick={() => handleDelete(item.maintenance_id)} className="text-red-600 hover:bg-red-50" data-testid={`delete-maintenance-${item.maintenance_id}`}>
                    <Trash size={16} />
                  </Button>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="bg-white border border-[#E4E4E7] rounded-md p-12 text-center">
          <CalendarCheck size={48} weight="duotone" className="mx-auto text-[#A1A1AA] mb-4" />
          <h3 className="font-semibold text-[#18181B] mb-2">Žádné záznamy údržby</h3>
          <p className="text-sm text-[#52525B]">Přidejte první záznam pro sledování servisních intervalů.</p>
        </div>
      )}

      {/* Create/Edit Modal */}
      <Dialog open={showModal} onOpenChange={setShowModal}>
        <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle>{editingId ? "Upravit údržbu" : "Přidat údržbu"}</DialogTitle></DialogHeader>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <Label>Vozidlo *</Label>
              <Select value={formData.vehicle_id} onValueChange={v => setFormData({ ...formData, vehicle_id: v })}>
                <SelectTrigger data-testid="maintenance-vehicle-select"><SelectValue placeholder="Vyberte vozidlo" /></SelectTrigger>
                <SelectContent>{vehicles.map(v => <SelectItem key={v.vehicle_id} value={v.vehicle_id}>{v.brand} {v.model} ({v.registration_plate})</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div>
              <Label>Typ údržby *</Label>
              <Select value={formData.type} onValueChange={v => setFormData({ ...formData, type: v })}>
                <SelectTrigger data-testid="maintenance-type-select"><SelectValue /></SelectTrigger>
                <SelectContent>{MAINTENANCE_TYPES.map(t => <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            {formData.type === "vlastní" && (
              <div>
                <Label>Název položky *</Label>
                <Input value={formData.custom_label} onChange={e => setFormData({ ...formData, custom_label: e.target.value })} placeholder="Např. Výměna filtru" data-testid="maintenance-custom-label" />
              </div>
            )}
            <div className="grid grid-cols-2 gap-4">
              <div><Label>Poslední provedeno</Label><Input type="date" value={formData.last_done_date} onChange={e => setFormData({ ...formData, last_done_date: e.target.value })} data-testid="maintenance-last-done-date" /></div>
              <div><Label>Km při posledním</Label><Input type="number" value={formData.last_done_odometer} onChange={e => setFormData({ ...formData, last_done_odometer: e.target.value })} placeholder="km" data-testid="maintenance-last-done-km" /></div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div><Label>Interval (měsíce)</Label><Input type="number" value={formData.interval_months} onChange={e => setFormData({ ...formData, interval_months: e.target.value })} placeholder="12" data-testid="maintenance-interval-months" /></div>
              <div><Label>Interval (km)</Label><Input type="number" value={formData.interval_km} onChange={e => setFormData({ ...formData, interval_km: e.target.value })} placeholder="15000" data-testid="maintenance-interval-km" /></div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div><Label>Další termín</Label><Input type="date" value={formData.next_due_date} onChange={e => setFormData({ ...formData, next_due_date: e.target.value })} data-testid="maintenance-next-due-date" /></div>
              <div><Label>Další km</Label><Input type="number" value={formData.next_due_odometer} onChange={e => setFormData({ ...formData, next_due_odometer: e.target.value })} placeholder="km" data-testid="maintenance-next-due-km" /></div>
            </div>
            <div><Label>Poznámky</Label><Textarea value={formData.notes} onChange={e => setFormData({ ...formData, notes: e.target.value })} rows={2} data-testid="maintenance-notes" /></div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setShowModal(false)}>Zrušit</Button>
              <Button type="submit" className="bg-[#002FA7] hover:bg-[#002480]" disabled={!formData.vehicle_id} data-testid="maintenance-submit-btn">{editingId ? "Uložit" : "Vytvořit"}</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
