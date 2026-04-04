import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { API } from "../App";
import { User, Plus, Pencil, Trash, Phone, Envelope } from "@phosphor-icons/react";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "../components/ui/dialog";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "../components/ui/alert-dialog";
import { toast } from "sonner";

export default function Instructors() {
  const [instructors, setInstructors] = useState([]);
  const [vehicles, setVehicles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [selectedInstructor, setSelectedInstructor] = useState(null);
  const [formData, setFormData] = useState({
    name: "", email: "", phone: "", license_number: "", assigned_vehicle_ids: []
  });

  const fetchData = useCallback(async () => {
    try {
      const [instructorsRes, vehiclesRes] = await Promise.all([
        axios.get(`${API}/instructors`, { withCredentials: true }),
        axios.get(`${API}/vehicles`, { withCredentials: true })
      ]);
      setInstructors(instructorsRes.data);
      setVehicles(vehiclesRes.data);
    } catch (error) {
      toast.error("Nepodařilo se načíst instruktory");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      if (selectedInstructor) {
        await axios.put(`${API}/instructors/${selectedInstructor.instructor_id}`, formData, { withCredentials: true });
        toast.success("Instruktor aktualizován");
      } else {
        await axios.post(`${API}/instructors`, formData, { withCredentials: true });
        toast.success("Instruktor přidán");
      }
      setShowModal(false); resetForm(); fetchData();
    } catch (error) { toast.error("Nepodařilo se uložit instruktora"); }
  };

  const handleDelete = async () => {
    try {
      await axios.delete(`${API}/instructors/${selectedInstructor.instructor_id}`, { withCredentials: true });
      toast.success("Instruktor smazán");
      setShowDeleteDialog(false); setSelectedInstructor(null); fetchData();
    } catch (error) { toast.error("Nepodařilo se smazat instruktora"); }
  };

  const openEditModal = (instructor) => {
    setSelectedInstructor(instructor);
    setFormData({ name: instructor.name, email: instructor.email, phone: instructor.phone, license_number: instructor.license_number, assigned_vehicle_ids: instructor.assigned_vehicle_ids || [] });
    setShowModal(true);
  };

  const resetForm = () => {
    setSelectedInstructor(null);
    setFormData({ name: "", email: "", phone: "", license_number: "", assigned_vehicle_ids: [] });
  };

  const getAssignedVehicles = (instructor) => {
    const assignedVehicles = vehicles.filter(v => v.assigned_instructor_id === instructor.instructor_id);
    return assignedVehicles.map(v => `${v.brand} ${v.model}`).join(", ") || "-";
  };

  if (loading) return <div className="flex items-center justify-center h-64"><div className="loading-spinner"></div></div>;

  return (
    <div className="space-y-6" data-testid="instructors-page">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="font-['Manrope'] text-2xl lg:text-3xl font-bold text-[#18181B] tracking-tight">Instruktoři</h1>
          <p className="text-[#52525B] mt-1">Správa instruktorů autoškoly</p>
        </div>
        <Button onClick={() => { resetForm(); setShowModal(true); }} className="bg-[#002FA7] hover:bg-[#002480]" data-testid="add-instructor-btn">
          <Plus size={20} className="mr-2" />Přidat instruktora
        </Button>
      </div>

      {instructors.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {instructors.map((instructor) => (
            <div key={instructor.instructor_id} className="bg-white border border-[#E4E4E7] rounded-md p-6 card-hover">
              <div className="flex items-center gap-3 mb-4">
                <div className="w-12 h-12 bg-[#F4F4F5] rounded-full flex items-center justify-center">
                  <User size={24} weight="duotone" className="text-[#002FA7]" />
                </div>
                <div>
                  <h3 className="font-semibold text-[#18181B]">{instructor.name}</h3>
                  <p className="text-sm text-[#52525B]">{instructor.license_number}</p>
                </div>
              </div>
              <div className="space-y-2 text-sm">
                <div className="flex items-center gap-2 text-[#52525B]"><Envelope size={16} /><span className="truncate">{instructor.email}</span></div>
                <div className="flex items-center gap-2 text-[#52525B]"><Phone size={16} /><span>{instructor.phone}</span></div>
              </div>
              <div className="mt-4 pt-4 border-t border-[#E4E4E7]">
                <p className="text-xs uppercase tracking-wider text-[#52525B] mb-1">Přiřazená vozidla</p>
                <p className="text-sm font-medium text-[#18181B]">{getAssignedVehicles(instructor)}</p>
              </div>
              <div className="flex gap-2 mt-4">
                <Button variant="outline" size="sm" onClick={() => openEditModal(instructor)} className="flex-1"><Pencil size={16} className="mr-1" />Upravit</Button>
                <Button variant="outline" size="sm" onClick={() => { setSelectedInstructor(instructor); setShowDeleteDialog(true); }} className="text-[#991B1B] hover:bg-red-50"><Trash size={16} /></Button>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="bg-white border border-[#E4E4E7] rounded-md p-12 text-center">
          <User size={48} weight="duotone" className="mx-auto text-[#A1A1AA] mb-4" />
          <h3 className="font-semibold text-[#18181B] mb-2">Žádní instruktoři</h3>
          <p className="text-[#52525B] mb-4">Začněte přidáním prvního instruktora</p>
          <Button onClick={() => { resetForm(); setShowModal(true); }} className="bg-[#002FA7] hover:bg-[#002480]"><Plus size={20} className="mr-2" />Přidat instruktora</Button>
        </div>
      )}

      <Dialog open={showModal} onOpenChange={setShowModal}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>{selectedInstructor ? "Upravit instruktora" : "Nový instruktor"}</DialogTitle></DialogHeader>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div><Label>Jméno *</Label><Input value={formData.name} onChange={(e) => setFormData({ ...formData, name: e.target.value })} required /></div>
            <div><Label>Email *</Label><Input type="email" value={formData.email} onChange={(e) => setFormData({ ...formData, email: e.target.value })} required /></div>
            <div><Label>Telefon *</Label><Input value={formData.phone} onChange={(e) => setFormData({ ...formData, phone: e.target.value })} required /></div>
            <div><Label>Číslo oprávnění *</Label><Input value={formData.license_number} onChange={(e) => setFormData({ ...formData, license_number: e.target.value })} required /></div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setShowModal(false)}>Zrušit</Button>
              <Button type="submit" className="bg-[#002FA7] hover:bg-[#002480]">{selectedInstructor ? "Uložit" : "Přidat"}</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <AlertDialog open={showDeleteDialog} onOpenChange={setShowDeleteDialog}>
        <AlertDialogContent>
          <AlertDialogHeader><AlertDialogTitle>Smazat instruktora?</AlertDialogTitle><AlertDialogDescription>Opravdu chcete smazat {selectedInstructor?.name}?</AlertDialogDescription></AlertDialogHeader>
          <AlertDialogFooter><AlertDialogCancel>Zrušit</AlertDialogCancel><AlertDialogAction onClick={handleDelete} className="bg-[#FF2400]">Smazat</AlertDialogAction></AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
