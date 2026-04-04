import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { API } from "../App";
import { Car, Plus, Pencil, Trash, QrCode, Handshake } from "@phosphor-icons/react";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "../components/ui/dialog";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "../components/ui/alert-dialog";
import { toast } from "sonner";
import { QRCodeSVG } from "qrcode.react";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;

export default function Vehicles() {
  const [vehicles, setVehicles] = useState([]);
  const [instructors, setInstructors] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [showQRModal, setShowQRModal] = useState(false);
  const [selectedVehicle, setSelectedVehicle] = useState(null);
  const [qrType, setQrType] = useState("fuel");
  const [formData, setFormData] = useState({
    registration_plate: "",
    brand: "",
    model: "",
    year: new Date().getFullYear(),
    vin: "",
    odometer: 0,
    fuel_type: "benzín",
    assigned_instructor_id: ""
  });

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


  const handleSubmit = async (e) => {
    e.preventDefault();
    
    const submitData = {
      ...formData,
      assigned_instructor_id: formData.assigned_instructor_id || null
    };

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
    } catch (error) {
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
    } catch (error) {
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
      assigned_instructor_id: vehicle.assigned_instructor_id || ""
    });
    setShowModal(true);
  };

  const openQRModal = (vehicle, type) => {
    setSelectedVehicle(vehicle);
    setQrType(type);
    setShowQRModal(true);
  };

  const resetForm = () => {
    setSelectedVehicle(null);
    setFormData({
      registration_plate: "",
      brand: "",
      model: "",
      year: new Date().getFullYear(),
      vin: "",
      odometer: 0,
      fuel_type: "benzín",
      assigned_instructor_id: ""
    });
  };

  const getInstructorName = (id) => {
    const instructor = instructors.find(i => i.instructor_id === id);
    return instructor ? instructor.name : "-";
  };

  const getQRUrl = (vehicle, type) => {
    let code;
    if (type === "fuel") code = vehicle.qr_code_fuel;
    else if (type === "damage") code = vehicle.qr_code_damage;
    else code = vehicle.qr_code_handover || `handover_${vehicle.vehicle_id}`;
    return `${BACKEND_URL}/${type}/${code}`;
  };

  const getQRTitle = (type) => {
    const titles = {
      fuel: "QR kód pro tankování",
      damage: "QR kód pro hlášení poškození",
      handover: "QR kód pro předávku vozidla"
    };
    return titles[type] || "QR kód";
  };

  const getQRDescription = (type) => {
    const descriptions = {
      fuel: "zaznamenání tankování",
      damage: "nahlášení poškození",
      handover: "předávací protokol"
    };
    return descriptions[type] || "";
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
          <h1 className="font-['Manrope'] text-2xl lg:text-3xl font-bold text-[#18181B] tracking-tight">
            Vozidla
          </h1>
          <p className="text-[#52525B] mt-1">
            Správa vozového parku
          </p>
        </div>
        <Button
          onClick={() => { resetForm(); setShowModal(true); }}
          className="bg-[#002FA7] hover:bg-[#002480]"
          data-testid="add-vehicle-btn"
        >
          <Plus size={20} className="mr-2" />
          Přidat vozidlo
        </Button>
      </div>

      {/* Vehicles Grid */}
      {vehicles.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {vehicles.map((vehicle) => (
            <div
              key={vehicle.vehicle_id}
              className="bg-white border border-[#E4E4E7] rounded-md p-6 card-hover"
              data-testid={`vehicle-card-${vehicle.vehicle_id}`}
            >
              <div className="flex items-start justify-between mb-4">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 bg-[#F4F4F5] rounded-md flex items-center justify-center">
                    <Car size={24} weight="duotone" className="text-[#002FA7]" />
                  </div>
                  <div>
                    <h3 className="font-semibold text-[#18181B]">
                      {vehicle.brand} {vehicle.model}
                    </h3>
                    <p className="text-sm text-[#52525B]">{vehicle.registration_plate}</p>
                  </div>
                </div>
              </div>

              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-[#52525B]">Rok</span>
                  <span className="font-medium text-[#18181B]">{vehicle.year}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-[#52525B]">Tachometr</span>
                  <span className="font-medium text-[#18181B]">{vehicle.odometer?.toLocaleString("cs-CZ")} km</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-[#52525B]">Palivo</span>
                  <span className="font-medium text-[#18181B]">{vehicle.fuel_type}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-[#52525B]">Instruktor</span>
                  <span className="font-medium text-[#18181B]">
                    {getInstructorName(vehicle.assigned_instructor_id)}
                  </span>
                </div>
              </div>

              <div className="flex gap-2 mt-4 pt-4 border-t border-[#E4E4E7]">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => openQRModal(vehicle, "fuel")}
                  className="flex-1"
                  data-testid={`qr-fuel-${vehicle.vehicle_id}`}
                >
                  <QrCode size={16} className="mr-1" />
                  Tankování
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => openQRModal(vehicle, "damage")}
                  className="flex-1"
                  data-testid={`qr-damage-${vehicle.vehicle_id}`}
                >
                  <QrCode size={16} className="mr-1" />
                  Poškození
                </Button>
              </div>

              <div className="mt-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => openQRModal(vehicle, "handover")}
                  className="w-full bg-[#002FA7]/5 border-[#002FA7]/20 text-[#002FA7] hover:bg-[#002FA7]/10"
                  data-testid={`qr-handover-${vehicle.vehicle_id}`}
                >
                  <Handshake size={16} className="mr-1" />
                  Předávka vozidla
                </Button>
              </div>

              <div className="flex gap-2 mt-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => openEditModal(vehicle)}
                  className="flex-1"
                  data-testid={`edit-vehicle-${vehicle.vehicle_id}`}
                >
                  <Pencil size={16} className="mr-1" />
                  Upravit
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => { setSelectedVehicle(vehicle); setShowDeleteDialog(true); }}
                  className="text-[#991B1B] hover:bg-red-50"
                  data-testid={`delete-vehicle-${vehicle.vehicle_id}`}
                >
                  <Trash size={16} />
                </Button>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="bg-white border border-[#E4E4E7] rounded-md p-12 text-center">
          <Car size={48} weight="duotone" className="mx-auto text-[#A1A1AA] mb-4" />
          <h3 className="font-semibold text-[#18181B] mb-2">Žádná vozidla</h3>
          <p className="text-[#52525B] mb-4">Začněte přidáním prvního vozidla</p>
          <Button
            onClick={() => { resetForm(); setShowModal(true); }}
            className="bg-[#002FA7] hover:bg-[#002480]"
          >
            <Plus size={20} className="mr-2" />
            Přidat vozidlo
          </Button>
        </div>
      )}

      {/* Add/Edit Modal */}
      <Dialog open={showModal} onOpenChange={setShowModal}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="font-['Manrope']">
              {selectedVehicle ? "Upravit vozidlo" : "Nové vozidlo"}
            </DialogTitle>
          </DialogHeader>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label htmlFor="brand">Značka *</Label>
                <Input
                  id="brand"
                  value={formData.brand}
                  onChange={(e) => setFormData({ ...formData, brand: e.target.value })}
                  required
                  data-testid="vehicle-brand-input"
                />
              </div>
              <div>
                <Label htmlFor="model">Model *</Label>
                <Input
                  id="model"
                  value={formData.model}
                  onChange={(e) => setFormData({ ...formData, model: e.target.value })}
                  required
                  data-testid="vehicle-model-input"
                />
              </div>
            </div>

            <div>
              <Label htmlFor="registration_plate">SPZ *</Label>
              <Input
                id="registration_plate"
                value={formData.registration_plate}
                onChange={(e) => setFormData({ ...formData, registration_plate: e.target.value.toUpperCase() })}
                required
                data-testid="vehicle-plate-input"
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label htmlFor="year">Rok výroby *</Label>
                <Input
                  id="year"
                  type="number"
                  min="1990"
                  max={new Date().getFullYear() + 1}
                  value={formData.year}
                  onChange={(e) => setFormData({ ...formData, year: parseInt(e.target.value) })}
                  required
                  data-testid="vehicle-year-input"
                />
              </div>
              <div>
                <Label htmlFor="odometer">Tachometr (km)</Label>
                <Input
                  id="odometer"
                  type="number"
                  min="0"
                  value={formData.odometer}
                  onChange={(e) => setFormData({ ...formData, odometer: parseInt(e.target.value) || 0 })}
                  data-testid="vehicle-odometer-input"
                />
              </div>
            </div>

            <div>
              <Label htmlFor="vin">VIN</Label>
              <Input
                id="vin"
                value={formData.vin}
                onChange={(e) => setFormData({ ...formData, vin: e.target.value.toUpperCase() })}
                data-testid="vehicle-vin-input"
              />
            </div>

            <div>
              <Label htmlFor="fuel_type">Typ paliva</Label>
              <Select
                value={formData.fuel_type}
                onValueChange={(value) => setFormData({ ...formData, fuel_type: value })}
              >
                <SelectTrigger data-testid="vehicle-fuel-select">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="benzín">Benzín</SelectItem>
                  <SelectItem value="nafta">Nafta</SelectItem>
                  <SelectItem value="LPG">LPG</SelectItem>
                  <SelectItem value="elektro">Elektro</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div>
              <Label htmlFor="instructor">Přiřazený instruktor</Label>
              <Select
                value={formData.assigned_instructor_id || "none"}
                onValueChange={(value) => setFormData({ ...formData, assigned_instructor_id: value === "none" ? "" : value })}
              >
                <SelectTrigger data-testid="vehicle-instructor-select">
                  <SelectValue placeholder="Vyberte instruktora" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">Bez instruktora</SelectItem>
                  {instructors.map((instructor) => (
                    <SelectItem key={instructor.instructor_id} value={instructor.instructor_id}>
                      {instructor.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setShowModal(false)}>
                Zrušit
              </Button>
              <Button type="submit" className="bg-[#002FA7] hover:bg-[#002480]" data-testid="vehicle-submit-btn">
                {selectedVehicle ? "Uložit" : "Přidat"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* QR Code Modal */}
      <Dialog open={showQRModal} onOpenChange={setShowQRModal}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle className="font-['Manrope']">
              {getQRTitle(qrType)}
            </DialogTitle>
          </DialogHeader>
          {selectedVehicle && (
            <div className="text-center">
              <p className="text-sm text-[#52525B] mb-4">
                {selectedVehicle.brand} {selectedVehicle.model} ({selectedVehicle.registration_plate})
              </p>
              <div className="bg-white p-6 inline-block rounded-lg border border-[#E4E4E7]">
                <QRCodeSVG
                  value={getQRUrl(selectedVehicle, qrType)}
                  size={200}
                  level="H"
                />
              </div>
              <p className="text-xs text-[#52525B] mt-4">
                Naskenujte pro {getQRDescription(qrType)}
              </p>
              {qrType === "handover" && (
                <p className="text-xs text-[#002FA7] mt-2 font-medium">
                  Obsahuje kontrolu kapalin a 6 povinných fotografií
                </p>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>

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
            <AlertDialogAction
              onClick={handleDelete}
              className="bg-[#FF2400] hover:bg-[#CC1D00]"
              data-testid="confirm-delete-btn"
            >
              Smazat
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
