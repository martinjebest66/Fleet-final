import { useState, useEffect, useCallback } from "react";
import { useParams } from "react-router-dom";
import axios from "axios";
import { Warning, Check, Car, Camera, X } from "@phosphor-icons/react";
import { Button } from "../components/ui/button";
import { toast } from "sonner";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Textarea } from "../components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

export default function PublicDamageForm() {
  const { qrCode } = useParams();
  const [vehicle, setVehicle] = useState(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState(null);
  const [formData, setFormData] = useState({
    description: "",
    severity: "střední",
    location_on_vehicle: "",
    photos: [],
    reported_by: "",
    notes: ""
  });

  const fetchVehicle = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/public/vehicle/${qrCode}`);
      setVehicle(res.data);
    } catch (err) {
      setError("Vozidlo nenalezeno nebo neplatný QR kód");
    } finally {
      setLoading(false);
    }
  }, [qrCode]);

  useEffect(() => {
    fetchVehicle();
  }, [fetchVehicle]);

  const handlePhotoUpload = async (e) => {
    const files = Array.from(e.target.files);
    for (const file of files) {
      const fd = new FormData();
      fd.append("file", file);
      try {
        const res = await axios.post(`${API}/public/upload`, fd, {
          headers: { "Content-Type": "multipart/form-data" }
        });
        setFormData(prev => ({ ...prev, photos: [...prev.photos, res.data.url] }));
      } catch (err) {
        toast.error("Nahrávání fotky selhalo");
      }
    }
  };

  const removePhoto = (index) => {
    setFormData(prev => ({
      ...prev,
      photos: prev.photos.filter((_, i) => i !== index)
    }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      await axios.post(`${API}/public/damages`, {
        vehicle_id: vehicle.vehicle_id,
        ...formData
      });
      setSuccess(true);
    } catch (err) {
      setError("Nepodařilo se odeslat hlášení");
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
          <div className="w-16 h-16 bg-green-100 rounded-full flex items-center justify-center mx-auto mb-4">
            <Check size={32} className="text-green-500" />
          </div>
          <h1 className="text-xl font-bold text-[#18181B] mb-2">Poškození nahlášeno</h1>
          <p className="text-[#52525B]">Děkujeme za nahlášení poškození. Bude zpracováno.</p>
          <p className="text-sm text-[#52525B] mt-4">{vehicle.brand} {vehicle.model} ({vehicle.registration_plate})</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#F4F4F5] p-4" data-testid="public-damage-form">
      <div className="max-w-md mx-auto">
        {/* Header */}
        <div className="bg-[#FF2400] text-white rounded-t-lg p-6 text-center">
          <Warning size={48} weight="duotone" className="mx-auto mb-3" />
          <h1 className="text-xl font-bold">Hlášení poškození</h1>
          <p className="text-sm opacity-80 mt-1">
            {vehicle.brand} {vehicle.model}
          </p>
          <p className="text-lg font-semibold mt-1">{vehicle.registration_plate}</p>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="bg-white rounded-b-lg p-6 space-y-4">
          <div>
            <Label>Popis poškození *</Label>
            <Textarea
              value={formData.description}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              required
              rows={3}
              placeholder="Popište co se stalo..."
            />
          </div>

          <div>
            <Label>Závažnost</Label>
            <Select
              value={formData.severity}
              onValueChange={(v) => setFormData({ ...formData, severity: v })}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="nízká">Nízká (kosmetická vada)</SelectItem>
                <SelectItem value="střední">Střední (funkční, ale poškozené)</SelectItem>
                <SelectItem value="vysoká">Vysoká (vozidlo není provozuschopné)</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div>
            <Label>Umístění na vozidle *</Label>
            <Input
              value={formData.location_on_vehicle}
              onChange={(e) => setFormData({ ...formData, location_on_vehicle: e.target.value })}
              required
              placeholder="např. přední nárazník, pravé zrcátko..."
            />
          </div>

          <div>
            <Label>Fotografie</Label>
            <div className="border-2 border-dashed border-[#E4E4E7] rounded-md p-6 text-center">
              <Camera size={32} className="mx-auto text-[#A1A1AA] mb-2" />
              <p className="text-sm text-[#52525B] mb-2">Přidejte fotografie poškození</p>
              <Input
                type="file"
                accept="image/*"
                multiple
                capture="environment"
                onChange={handlePhotoUpload}
                className="cursor-pointer"
              />
            </div>
            {formData.photos.length > 0 && (
              <div className="flex gap-2 mt-3 flex-wrap">
                {formData.photos.map((photo, idx) => (
                  <div key={`photo-${photo}`} className="relative">
                    <img
                      src={photo}
                      alt={`Foto ${idx + 1}`}
                      className="w-20 h-20 object-cover rounded-md border"
                    />
                    <button
                      type="button"
                      onClick={() => removePhoto(idx)}
                      className="absolute -top-2 -right-2 w-6 h-6 bg-[#FF2400] text-white rounded-full flex items-center justify-center"
                    >
                      <X size={14} />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div>
            <Label>Vaše jméno</Label>
            <Input
              value={formData.reported_by}
              onChange={(e) => setFormData({ ...formData, reported_by: e.target.value })}
              placeholder="Jméno a příjmení"
            />
          </div>

          <div>
            <Label>Poznámky</Label>
            <Textarea
              value={formData.notes}
              onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
              rows={2}
              placeholder="Další informace..."
            />
          </div>

          {error && <p className="text-red-500 text-sm text-center">{error}</p>}

          <Button
            type="submit"
            className="w-full bg-[#FF2400] hover:bg-[#CC1D00] py-6 text-lg"
            disabled={submitting || !formData.description || !formData.location_on_vehicle}
          >
            {submitting ? "Odesílám..." : "Nahlásit poškození"}
          </Button>
        </form>
      </div>
    </div>
  );
}
