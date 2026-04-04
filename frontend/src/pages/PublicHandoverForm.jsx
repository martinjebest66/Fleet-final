import { useState, useEffect, useRef, useCallback } from "react";
import { useParams } from "react-router-dom";
import axios from "axios";
import { Handshake, Check, Car, Camera, ArrowRight, ArrowLeft, X, CheckCircle, Warning } from "@phosphor-icons/react";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Checkbox } from "../components/ui/checkbox";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Textarea } from "../components/ui/textarea";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

// Photo steps configuration
const PHOTO_STEPS = [
  { id: "front", label: "Přední strana", instruction: "Vyfoťte vozidlo zepředu (čelní pohled)" },
  { id: "rear", label: "Zadní strana", instruction: "Vyfoťte vozidlo zezadu" },
  { id: "left", label: "Levá strana", instruction: "Vyfoťte vozidlo z levé strany" },
  { id: "right", label: "Pravá strana", instruction: "Vyfoťte vozidlo z pravé strany" },
  { id: "interior", label: "Interiér", instruction: "Vyfoťte interiér vozidla (sedadla, přístrojovka)" },
  { id: "dashboard", label: "Palubní deska", instruction: "Vyfoťte palubní desku s ukazatelem paliva a tachometrem" }
];

// Fluid check items
const FLUID_CHECKS = [
  { id: "engine_oil", label: "Motorový olej", description: "Zkontrolován a doplněn" },
  { id: "coolant", label: "Chladicí kapalina", description: "Zkontrolována a doplněna" },
  { id: "brake_fluid", label: "Brzdová kapalina", description: "Zkontrolována a doplněna" },
  { id: "windshield_washer", label: "Kapalina ostřikovačů", description: "Zkontrolována a doplněna" },
  { id: "other_fluids", label: "Ostatní provozní kapaliny", description: "Zkontrolovány (servo, převodovka)" }
];

export default function PublicHandoverForm() {
  const { qrCode } = useParams();
  const [vehicle, setVehicle] = useState(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState(null);
  
  // Form state
  const [currentStep, setCurrentStep] = useState(0); // 0=info, 1=fluids, 2-7=photos, 8=review
  const [formData, setFormData] = useState({
    handler_name: "",
    handler_type: "převzetí",
    odometer: 0,
    fuel_level: 50,
    notes: ""
  });
  const [fluidChecks, setFluidChecks] = useState({
    engine_oil: false,
    coolant: false,
    brake_fluid: false,
    windshield_washer: false,
    other_fluids: false,
    other_fluids_note: ""
  });
  const [photos, setPhotos] = useState({});
  const [uploadingPhoto, setUploadingPhoto] = useState(false);
  
  const fileInputRef = useRef(null);

  const fetchVehicle = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/public/vehicle/${qrCode}`);
      setVehicle(res.data);
      setFormData(prev => ({ ...prev, odometer: res.data.odometer || 0 }));
    } catch (err) {
      setError("Vozidlo nenalezeno nebo neplatný QR kód");
    } finally {
      setLoading(false);
    }
  }, [qrCode]);

  useEffect(() => {
    fetchVehicle();
  }, [fetchVehicle]);

  const handlePhotoCapture = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploadingPhoto(true);
    const fd = new FormData();
    fd.append("file", file);

    try {
      const res = await axios.post(`${API}/public/upload`, fd, {
        headers: { "Content-Type": "multipart/form-data" }
      });
      
      const photoStep = PHOTO_STEPS[currentStep - 2]; // Step 2 is first photo
      setPhotos(prev => ({
        ...prev,
        [photoStep.id]: {
          photo_type: photoStep.id,
          photo_url: res.data.url,
          timestamp: new Date().toISOString()
        }
      }));
    } catch (err) {
      console.error("Upload failed:", err);
    } finally {
      setUploadingPhoto(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const retakePhoto = () => {
    const photoStep = PHOTO_STEPS[currentStep - 2];
    setPhotos(prev => {
      const newPhotos = { ...prev };
      delete newPhotos[photoStep.id];
      return newPhotos;
    });
  };

  const canProceed = () => {
    switch (currentStep) {
      case 0: // Info step
        return formData.handler_name.trim().length > 0 && formData.odometer > 0;
      case 1: // Fluids step
        return Object.values(fluidChecks).slice(0, 5).every(v => v === true);
      case 2: case 3: case 4: case 5: case 6: case 7: // Photo steps
        const photoStep = PHOTO_STEPS[currentStep - 2];
        return !!photos[photoStep.id];
      case 8: // Review step
        return true;
      default:
        return false;
    }
  };

  const handleSubmit = async () => {
    setSubmitting(true);
    setError(null);

    try {
      const photosList = PHOTO_STEPS.map(step => photos[step.id]);
      
      await axios.post(`${API}/public/qr-handover`, {
        vehicle_id: vehicle.vehicle_id,
        handler_name: formData.handler_name,
        handler_type: formData.handler_type,
        odometer: formData.odometer,
        fuel_level: formData.fuel_level,
        fluid_checks: fluidChecks,
        photos: photosList,
        notes: formData.notes
      });
      
      setSuccess(true);
    } catch (err) {
      setError(err.response?.data?.detail || "Nepodařilo se odeslat protokol");
    } finally {
      setSubmitting(false);
    }
  };

  const nextStep = () => {
    if (currentStep < 8) setCurrentStep(prev => prev + 1);
  };

  const prevStep = () => {
    if (currentStep > 0) setCurrentStep(prev => prev - 1);
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-[#F4F4F5] flex items-center justify-center p-4">
        <div className="loading-spinner"></div>
      </div>
    );
  }

  if (error && !vehicle) {
    return (
      <div className="min-h-screen bg-[#F4F4F5] flex items-center justify-center p-4">
        <div className="bg-white rounded-lg p-8 max-w-md w-full text-center">
          <div className="w-16 h-16 bg-red-100 rounded-full flex items-center justify-center mx-auto mb-4">
            <Car size={32} className="text-red-500" />
          </div>
          <h1 className="text-xl font-bold text-[#18181B] mb-2">Chyba</h1>
          <p className="text-[#52525B]">{error}</p>
        </div>
      </div>
    );
  }

  if (success) {
    return (
      <div className="min-h-screen bg-[#F4F4F5] flex items-center justify-center p-4">
        <div className="bg-white rounded-lg p-8 max-w-md w-full text-center">
          <div className="w-20 h-20 bg-green-100 rounded-full flex items-center justify-center mx-auto mb-4">
            <CheckCircle size={48} className="text-green-500" />
          </div>
          <h1 className="text-xl font-bold text-[#18181B] mb-2">Protokol odeslán</h1>
          <p className="text-[#52525B]">Předávací protokol byl úspěšně vytvořen.</p>
          <div className="mt-4 p-4 bg-[#F4F4F5] rounded-lg">
            <p className="font-semibold">{vehicle.brand} {vehicle.model}</p>
            <p className="text-sm text-[#52525B]">{vehicle.registration_plate}</p>
          </div>
        </div>
      </div>
    );
  }

  // Progress indicator
  const totalSteps = 9;
  const progress = ((currentStep + 1) / totalSteps) * 100;

  return (
    <div className="min-h-screen bg-[#F4F4F5]" data-testid="public-handover-form">
      {/* Header */}
      <div className="bg-[#002FA7] text-white p-4 sticky top-0 z-10">
        <div className="max-w-md mx-auto">
          <div className="flex items-center gap-3 mb-3">
            <Handshake size={28} weight="duotone" />
            <div>
              <h1 className="font-bold">Předávací protokol</h1>
              <p className="text-sm opacity-80">{vehicle.brand} {vehicle.model} • {vehicle.registration_plate}</p>
            </div>
          </div>
          {/* Progress bar */}
          <div className="h-1 bg-white/20 rounded-full overflow-hidden">
            <div 
              className="h-full bg-white transition-all duration-300" 
              style={{ width: `${progress}%` }}
            />
          </div>
          <p className="text-xs text-center mt-2 opacity-80">Krok {currentStep + 1} z {totalSteps}</p>
        </div>
      </div>

      {/* Content */}
      <div className="max-w-md mx-auto p-4 pb-24">
        {/* Step 0: Basic Info */}
        {currentStep === 0 && (
          <div className="bg-white rounded-lg p-6 space-y-4 animate-fade-in">
            <h2 className="text-lg font-bold text-[#18181B]">Základní údaje</h2>
            
            <div>
              <Label>Vaše jméno *</Label>
              <Input
                value={formData.handler_name}
                onChange={(e) => setFormData({ ...formData, handler_name: e.target.value })}
                placeholder="Jan Novák"
                className="mt-1"
              />
            </div>

            <div>
              <Label>Typ předávky *</Label>
              <Select
                value={formData.handler_type}
                onValueChange={(v) => setFormData({ ...formData, handler_type: v })}
              >
                <SelectTrigger className="mt-1">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="převzetí">Převzetí vozidla</SelectItem>
                  <SelectItem value="předání">Předání vozidla</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div>
              <Label>Stav tachometru (km) *</Label>
              <Input
                type="number"
                min="0"
                value={formData.odometer}
                onChange={(e) => setFormData({ ...formData, odometer: parseInt(e.target.value) || 0 })}
                className="mt-1"
              />
            </div>

            <div>
              <Label>Stav paliva (%)</Label>
              <div className="flex items-center gap-4 mt-1">
                <Input
                  type="range"
                  min="0"
                  max="100"
                  step="5"
                  value={formData.fuel_level}
                  onChange={(e) => setFormData({ ...formData, fuel_level: parseInt(e.target.value) })}
                  className="flex-1"
                />
                <span className="w-12 text-center font-bold">{formData.fuel_level}%</span>
              </div>
            </div>
          </div>
        )}

        {/* Step 1: Fluid Checks */}
        {currentStep === 1 && (
          <div className="bg-white rounded-lg p-6 space-y-4 animate-fade-in">
            <h2 className="text-lg font-bold text-[#18181B]">Kontrola provozních kapalin</h2>
            <p className="text-sm text-[#52525B]">Potvrďte, že jste zkontrolovali a případně doplnili všechny provozní kapaliny:</p>
            
            <div className="space-y-3">
              {FLUID_CHECKS.map((fluid) => (
                <label
                  key={fluid.id}
                  className={`flex items-start gap-3 p-4 border rounded-lg cursor-pointer transition-all ${
                    fluidChecks[fluid.id] 
                      ? "border-[#002FA7] bg-[#002FA7]/5" 
                      : "border-[#E4E4E7] hover:border-[#A1A1AA]"
                  }`}
                >
                  <Checkbox
                    checked={fluidChecks[fluid.id]}
                    onCheckedChange={(checked) => setFluidChecks({ ...fluidChecks, [fluid.id]: checked })}
                    className="mt-0.5"
                  />
                  <div className="flex-1">
                    <p className="font-medium text-[#18181B]">{fluid.label}</p>
                    <p className="text-sm text-[#52525B]">{fluid.description}</p>
                  </div>
                  {fluidChecks[fluid.id] && (
                    <Check size={20} className="text-[#16A34A]" />
                  )}
                </label>
              ))}
            </div>

            {!Object.values(fluidChecks).slice(0, 5).every(v => v === true) && (
              <div className="flex items-center gap-2 p-3 bg-amber-50 border border-amber-200 rounded-lg">
                <Warning size={20} className="text-amber-600" />
                <p className="text-sm text-amber-800">Všechny položky musí být zaškrtnuté</p>
              </div>
            )}
          </div>
        )}

        {/* Steps 2-7: Photo Capture */}
        {currentStep >= 2 && currentStep <= 7 && (
          <div className="bg-white rounded-lg p-6 space-y-4 animate-fade-in">
            {(() => {
              const photoStep = PHOTO_STEPS[currentStep - 2];
              const currentPhoto = photos[photoStep.id];
              
              return (
                <>
                  <div className="text-center">
                    <div className="inline-flex items-center gap-2 bg-[#F4F4F5] px-4 py-2 rounded-full mb-4">
                      <Camera size={20} className="text-[#002FA7]" />
                      <span className="font-semibold">Foto {currentStep - 1} z 6</span>
                    </div>
                    <h2 className="text-lg font-bold text-[#18181B]">{photoStep.label}</h2>
                    <p className="text-sm text-[#52525B] mt-1">{photoStep.instruction}</p>
                  </div>

                  {currentPhoto ? (
                    <div className="relative">
                      <img
                        src={currentPhoto.photo_url}
                        alt={photoStep.label}
                        className="w-full h-64 object-cover rounded-lg"
                      />
                      <div className="absolute top-2 right-2 bg-green-500 text-white px-3 py-1 rounded-full text-sm font-medium flex items-center gap-1">
                        <Check size={16} />
                        Pořízeno
                      </div>
                      <Button
                        variant="outline"
                        onClick={retakePhoto}
                        className="absolute bottom-2 right-2 bg-white"
                      >
                        <Camera size={16} className="mr-1" />
                        Pořídit znovu
                      </Button>
                    </div>
                  ) : (
                    <div 
                      onClick={() => fileInputRef.current?.click()}
                      className="border-2 border-dashed border-[#E4E4E7] rounded-lg p-8 text-center cursor-pointer hover:border-[#002FA7] hover:bg-[#002FA7]/5 transition-all"
                    >
                      {uploadingPhoto ? (
                        <div className="loading-spinner mx-auto"></div>
                      ) : (
                        <>
                          <Camera size={48} className="mx-auto text-[#A1A1AA] mb-4" />
                          <p className="text-[#52525B] mb-2">Klikněte pro pořízení fotografie</p>
                          <p className="text-xs text-[#A1A1AA]">Nebo přetáhněte soubor</p>
                        </>
                      )}
                    </div>
                  )}

                  <input
                    ref={fileInputRef}
                    type="file"
                    accept="image/*"
                    capture="environment"
                    onChange={handlePhotoCapture}
                    className="hidden"
                  />

                  {/* Photo thumbnails progress */}
                  <div className="flex gap-2 justify-center">
                    {PHOTO_STEPS.map((step, idx) => (
                      <div
                        key={step.id}
                        className={`w-10 h-10 rounded-lg overflow-hidden border-2 ${
                          idx === currentStep - 2 
                            ? "border-[#002FA7]" 
                            : photos[step.id] 
                              ? "border-green-500" 
                              : "border-[#E4E4E7]"
                        }`}
                      >
                        {photos[step.id] ? (
                          <img
                            src={photos[step.id].photo_url}
                            alt={step.label}
                            className="w-full h-full object-cover"
                          />
                        ) : (
                          <div className="w-full h-full bg-[#F4F4F5] flex items-center justify-center">
                            <span className="text-xs text-[#A1A1AA]">{idx + 1}</span>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </>
              );
            })()}
          </div>
        )}

        {/* Step 8: Review */}
        {currentStep === 8 && (
          <div className="space-y-4 animate-fade-in">
            <div className="bg-white rounded-lg p-6">
              <h2 className="text-lg font-bold text-[#18181B] mb-4">Kontrola před odesláním</h2>
              
              <div className="space-y-3">
                <div className="flex justify-between py-2 border-b border-[#E4E4E7]">
                  <span className="text-[#52525B]">Jméno</span>
                  <span className="font-medium">{formData.handler_name}</span>
                </div>
                <div className="flex justify-between py-2 border-b border-[#E4E4E7]">
                  <span className="text-[#52525B]">Typ</span>
                  <span className="font-medium capitalize">{formData.handler_type}</span>
                </div>
                <div className="flex justify-between py-2 border-b border-[#E4E4E7]">
                  <span className="text-[#52525B]">Tachometr</span>
                  <span className="font-medium">{formData.odometer.toLocaleString("cs-CZ")} km</span>
                </div>
                <div className="flex justify-between py-2 border-b border-[#E4E4E7]">
                  <span className="text-[#52525B]">Palivo</span>
                  <span className="font-medium">{formData.fuel_level}%</span>
                </div>
                <div className="flex justify-between py-2 border-b border-[#E4E4E7]">
                  <span className="text-[#52525B]">Kapaliny</span>
                  <span className="font-medium text-green-600">✓ Zkontrolovány</span>
                </div>
                <div className="flex justify-between py-2">
                  <span className="text-[#52525B]">Fotografie</span>
                  <span className="font-medium text-green-600">✓ 6/6 pořízeno</span>
                </div>
              </div>
            </div>

            {/* Photo grid */}
            <div className="bg-white rounded-lg p-6">
              <h3 className="font-semibold text-[#18181B] mb-3">Pořízené fotografie</h3>
              <div className="grid grid-cols-3 gap-2">
                {PHOTO_STEPS.map((step) => (
                  <div key={step.id} className="relative aspect-square">
                    <img
                      src={photos[step.id]?.photo_url}
                      alt={step.label}
                      className="w-full h-full object-cover rounded-lg"
                    />
                    <div className="absolute bottom-0 left-0 right-0 bg-black/60 text-white text-xs p-1 text-center rounded-b-lg">
                      {step.label}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Notes */}
            <div className="bg-white rounded-lg p-6">
              <Label>Poznámky (volitelné)</Label>
              <Textarea
                value={formData.notes}
                onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
                placeholder="Další poznámky k předávce..."
                rows={3}
                className="mt-2"
              />
            </div>

            {error && (
              <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700 text-sm">
                {error}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Bottom Navigation */}
      <div className="fixed bottom-0 left-0 right-0 bg-white border-t border-[#E4E4E7] p-4">
        <div className="max-w-md mx-auto flex gap-3">
          {currentStep > 0 && (
            <Button
              variant="outline"
              onClick={prevStep}
              className="flex-1"
            >
              <ArrowLeft size={20} className="mr-2" />
              Zpět
            </Button>
          )}
          
          {currentStep < 8 ? (
            <Button
              onClick={nextStep}
              disabled={!canProceed()}
              className="flex-1 bg-[#002FA7] hover:bg-[#002480]"
            >
              Pokračovat
              <ArrowRight size={20} className="ml-2" />
            </Button>
          ) : (
            <Button
              onClick={handleSubmit}
              disabled={submitting}
              className="flex-1 bg-[#16A34A] hover:bg-[#15803D]"
            >
              {submitting ? (
                <>
                  <div className="loading-spinner w-5 h-5 mr-2"></div>
                  Odesílám...
                </>
              ) : (
                <>
                  <Check size={20} className="mr-2" />
                  Odeslat protokol
                </>
              )}
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
