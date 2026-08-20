import { useState, useEffect, useCallback } from "react";
import { useParams } from "react-router-dom";
import axios from "axios";
import { Handshake, Check, Car, ArrowRight, ArrowLeft, CheckCircle } from "@phosphor-icons/react";
import { Button } from "../components/ui/button";
import { toast } from "sonner";
import { HandoverInfoStep } from "./handover/HandoverInfoStep";
import { HandoverFluidStep, FLUID_CHECKS } from "./handover/HandoverFluidStep";
import { HandoverPhotoStep, PHOTO_STEPS } from "./handover/HandoverPhotoStep";
import { HandoverReviewStep } from "./handover/HandoverReviewStep";

import { API, errorMessage } from "@/lib/api";
const TOTAL_STEPS = 9;

export default function PublicHandoverForm() {
  const { qrCode } = useParams();
  const [vehicle, setVehicle] = useState(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState(null);
  const [currentStep, setCurrentStep] = useState(0);
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

  const fetchVehicle = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/public/vehicle/${qrCode}`);
      setVehicle(res.data);
      setFormData(prev => ({ ...prev, odometer: res.data.odometer || 0 }));
    } catch {
      setError("Vozidlo nenalezeno nebo neplatný QR kód");
    } finally {
      setLoading(false);
    }
  }, [qrCode]);

  useEffect(() => { fetchVehicle(); }, [fetchVehicle]);

  const handlePhotoCapture = async (e, photoStepId) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploadingPhoto(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const res = await axios.post(`${API}/public/upload`, fd, {
        headers: { "Content-Type": "multipart/form-data" }
      });
      setPhotos(prev => ({
        ...prev,
        [photoStepId]: { photo_type: photoStepId, photo_url: res.data.url, timestamp: new Date().toISOString() }
      }));
    } catch (err) {
      toast.error(errorMessage(err, "Nahrávání fotky selhalo"));
    } finally {
      setUploadingPhoto(false);
    }
  };

  const retakePhoto = (photoStepId) => {
    setPhotos(prev => {
      const next = { ...prev };
      delete next[photoStepId];
      return next;
    });
  };

  const canProceed = () => {
    if (currentStep === 0) return formData.handler_name.trim().length > 0 && formData.odometer > 0;
    if (currentStep === 1) return FLUID_CHECKS.every(f => fluidChecks[f.id] === true);
    if (currentStep >= 2 && currentStep <= 7) return !!photos[PHOTO_STEPS[currentStep - 2].id];
    return true;
  };

  const handleSubmit = async () => {
    setSubmitting(true);
    setError(null);
    try {
      await axios.post(`${API}/public/qr-handover`, {
        vehicle_id: vehicle.vehicle_id,
        handler_name: formData.handler_name,
        handler_type: formData.handler_type,
        odometer: formData.odometer,
        fuel_level: formData.fuel_level,
        fluid_checks: fluidChecks,
        photos: PHOTO_STEPS.map(step => photos[step.id]),
        notes: formData.notes
      });
      setSuccess(true);
    } catch (err) {
      setError(errorMessage(err, "Nepodařilo se odeslat protokol"));
    } finally {
      setSubmitting(false);
    }
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

  const progress = ((currentStep + 1) / TOTAL_STEPS) * 100;

  return (
    <div className="min-h-screen bg-[#F4F4F5]" data-testid="public-handover-form">
      {/* Header */}
      <div className="bg-[#002FA7] text-white p-4 sticky top-0 z-10">
        <div className="max-w-md mx-auto">
          <div className="flex items-center gap-3 mb-3">
            <Handshake size={28} weight="duotone" />
            <div>
              <h1 className="font-bold">Předávací protokol</h1>
              <p className="text-sm opacity-80">{vehicle.brand} {vehicle.model} - {vehicle.registration_plate}</p>
            </div>
          </div>
          <div className="h-1 bg-white/20 rounded-full overflow-hidden">
            <div className="h-full bg-white transition-all duration-300" style={{ width: `${progress}%` }} />
          </div>
          <p className="text-xs text-center mt-2 opacity-80">Krok {currentStep + 1} z {TOTAL_STEPS}</p>
        </div>
      </div>

      {/* Step content */}
      <div className="max-w-md mx-auto p-4 pb-24">
        {currentStep === 0 && <HandoverInfoStep formData={formData} setFormData={setFormData} />}
        {currentStep === 1 && <HandoverFluidStep fluidChecks={fluidChecks} setFluidChecks={setFluidChecks} />}
        {currentStep >= 2 && currentStep <= 7 && (
          <HandoverPhotoStep
            photoIndex={currentStep - 2}
            photos={photos}
            onPhotoCapture={handlePhotoCapture}
            onRetakePhoto={retakePhoto}
            uploadingPhoto={uploadingPhoto}
          />
        )}
        {currentStep === 8 && (
          <HandoverReviewStep formData={formData} setFormData={setFormData} photos={photos} error={error} />
        )}
      </div>

      {/* Bottom Navigation */}
      <div className="fixed bottom-0 left-0 right-0 bg-white border-t border-[#E4E4E7] p-4">
        <div className="max-w-md mx-auto flex gap-3">
          {currentStep > 0 && (
            <Button variant="outline" onClick={() => setCurrentStep(s => s - 1)} className="flex-1" data-testid="handover-prev-btn">
              <ArrowLeft size={20} className="mr-2" />
              Zpět
            </Button>
          )}
          {currentStep < 8 ? (
            <Button
              onClick={() => setCurrentStep(s => s + 1)}
              disabled={!canProceed()}
              className="flex-1 bg-[#002FA7] hover:bg-[#002480]"
              data-testid="handover-next-btn"
            >
              Pokračovat
              <ArrowRight size={20} className="ml-2" />
            </Button>
          ) : (
            <Button
              onClick={handleSubmit}
              disabled={submitting}
              className="flex-1 bg-[#16A34A] hover:bg-[#15803D]"
              data-testid="handover-submit-btn"
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
