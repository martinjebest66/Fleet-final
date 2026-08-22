import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { API } from "../App";
import { Car, Plus } from "@phosphor-icons/react";
import { Button } from "../components/ui/button";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "../components/ui/alert-dialog";
import { toast } from "sonner";
import { VehicleCard } from "./vehicles/VehicleCard";
import { VehicleFormModal } from "./vehicles/VehicleFormModal";
import { VehicleQRModal } from "./vehicles/VehicleQRModal";
import { VehicleStateModal } from "./vehicles/VehicleStateModal";

const INITIAL_FORM = {
  registration_plate: "",
  brand: "",
  model: "",
  year: new Date().getFullYear(),
  vin: "",
  odometer: 0,
  fuel_type: "benzín",
  assigned_instructor_id: "",
  reservation_alias: ""
};

export default function Vehicles() {
  const [vehicles, setVehicles] = useState([]);
  const [instructors, setInstructors] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [showQRModal, setShowQRModal] = useState(false);
  const [showStateModal, setShowStateModal] = useState(false);
  const [selectedVehicle, setSelectedVehicle] = useState(null);
  const [qrType, setQrType] = useState("fuel");
  const [formData, setFormData] = useState(INITIAL_FORM);

  const fetchData = useCallback(async () => {
    try {
      const [vehiclesRes, instructorsRes] = await Promise.all([
        axios.get(`${API}/vehicles`, { withCredentials: true }),
        axios.get(`${API}/instructors`, { withCredentials: true })
      ]);
      setVehicles(vehiclesRes.data);
      setInstructors(instructorsRes.data);
    } catch {
      toast.error("Nepodařilo se načíst vozidla");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const resetForm = () => {
    setSelectedVehicle(null);
    setFormData(INITIAL_FORM);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    const submitData = { ...formData, assigned_instructor_id: formData.assigned_instructor_id || null };
    try {
      if (selectedVehicle) {
        await axios.put(`${API}/vehicles/${selectedVehicle.vehicle_id}`, submitData, { withCredentials: true });
        toast.success("Vozidlo aktualizováno");
      } else {
        await axios.post(`${API}/vehicles`, submitData, { withCredentials: true });
        toast.success("Vozidlo přidáno");
      }
      setShowModal(false);
      resetForm();
      fetchData();
    } catch {
      toast.error("Nepodařilo se uložit vozidlo");
    }
  };

  const handleDelete = async () => {
    try {
      await axios.delete(`${API}/vehicles/${selectedVehicle.vehicle_id}`, { withCredentials: true });
      toast.success("Vozidlo smazáno");
      setShowDeleteDialog(false);
      setSelectedVehicle(null);
      fetchData();
    } catch {
      toast.error("Nepodařilo se smazat vozidlo");
    }
  };

  const openEditModal = (vehicle) => {
    setSelectedVehicle(vehicle);
    setFormData({
      registration_plate: vehicle.registration_plate,
      brand: vehicle.brand,
      model: vehicle.model,
      year: vehicle.year,
      vin: vehicle.vin || "",
      odometer: vehicle.odometer,
      fuel_type: vehicle.fuel_type,
      assigned_instructor_id: vehicle.assigned_instructor_id || "",
      reservation_alias: vehicle.reservation_alias || ""
    });
    setShowModal(true);
  };

  const openDeleteDialog = (vehicle) => {
    setSelectedVehicle(vehicle);
    setShowDeleteDialog(true);
  };

  const openStateModal = (vehicle) => {
    setSelectedVehicle(vehicle);
    setShowStateModal(true);
  };

  const openQRModal = (vehicle, type) => {
    setSelectedVehicle(vehicle);
    setQrType(type);
    setShowQRModal(true);
  };

  const getInstructorName = (id) => {
    const instructor = instructors.find(i => i.instructor_id === id);
    return instructor ? instructor.name : "-";
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="loading-spinner"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6" data-testid="vehicles-page">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="font-['Manrope'] text-2xl lg:text-3xl font-bold text-[#18181B] tracking-tight">Vozidla</h1>
          <p className="text-[#52525B] mt-1">Správa vozového parku</p>
        </div>
        <Button onClick={() => { resetForm(); setShowModal(true); }} className="bg-[#002FA7] hover:bg-[#002480]" data-testid="add-vehicle-btn">
          <Plus size={20} className="mr-2" />
          Přidat vozidlo
        </Button>
      </div>

      {/* Vehicles Grid */}
      {vehicles.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {vehicles.map((vehicle) => (
            <VehicleCard
              key={vehicle.vehicle_id}
              vehicle={vehicle}
              getInstructorName={getInstructorName}
              onEdit={openEditModal}
              onDelete={openDeleteDialog}
              onQR={openQRModal}
              onState={openStateModal}
            />
          ))}
        </div>
      ) : (
        <div className="bg-white border border-[#E4E4E7] rounded-md p-12 text-center">
          <Car size={48} weight="duotone" className="mx-auto text-[#A1A1AA] mb-4" />
          <h3 className="font-semibold text-[#18181B] mb-2">Žádná vozidla</h3>
          <p className="text-[#52525B] mb-4">Začněte přidáním prvního vozidla</p>
          <Button onClick={() => { resetForm(); setShowModal(true); }} className="bg-[#002FA7] hover:bg-[#002480]">
            <Plus size={20} className="mr-2" />
            Přidat vozidlo
          </Button>
        </div>
      )}

      {/* Modals */}
      <VehicleFormModal
        open={showModal}
        onOpenChange={setShowModal}
        formData={formData}
        setFormData={setFormData}
        instructors={instructors}
        isEditing={!!selectedVehicle}
        onSubmit={handleSubmit}
      />

      <VehicleQRModal
        open={showQRModal}
        onOpenChange={setShowQRModal}
        vehicle={selectedVehicle}
        qrType={qrType}
      />

      <VehicleStateModal
        open={showStateModal}
        onOpenChange={setShowStateModal}
        vehicle={selectedVehicle}
      />

      {/* Delete Confirmation */}
      <AlertDialog open={showDeleteDialog} onOpenChange={setShowDeleteDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Smazat vozidlo?</AlertDialogTitle>
            <AlertDialogDescription>
              Opravdu chcete smazat vozidlo {selectedVehicle?.brand} {selectedVehicle?.model} ({selectedVehicle?.registration_plate})? Tato akce je nevratná.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Zrušit</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete} className="bg-[#FF2400] hover:bg-[#CC1D00]" data-testid="confirm-delete-btn">
              Smazat
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
