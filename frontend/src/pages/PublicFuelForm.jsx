import { useState, useEffect } from "react";
import { useParams } from "react-router-dom";
import axios from "axios";
import { GasPump, Check, Car } from "@phosphor-icons/react";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { format } from "date-fns";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

export default function PublicFuelForm() {
  const { qrCode } = useParams();
  const [vehicle, setVehicle] = useState(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState(null);
  const [formData, setFormData] = useState({
    date: format(new Date(), "yyyy-MM-dd"),
    odometer: 0,
    liters: 0,
    price_per_liter: 38.90,
    total_price: 0,
    fuel_station: "",
    notes: ""
  });

  useEffect(() => {
    fetchVehicle();
  }, [qrCode]);

  const fetchVehicle = async () => {
    try {
      const res = await axios.get(`${API}/public/vehicle/${qrCode}`);
      setVehicle(res.data);
      setFormData(prev => ({ ...prev, odometer: res.data.odometer || 0 }));
    } catch (err) {
      setError("Vozidlo nenalezeno nebo neplatný QR kód");
    } finally {
      setLoading(false);
    }
  };

  const handleLitersChange = (liters) => {
    setFormData({
      ...formData,
      liters,
      total_price: Math.round(liters * formData.price_per_liter * 100) / 100
    });
  };

  const handlePriceChange = (price) => {
    setFormData({
      ...formData,
      price_per_liter: price,
      total_price: Math.round(formData.liters * price * 100) / 100
    });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      await axios.post(`${API}/public/fuel`, {
        vehicle_id: vehicle.vehicle_id,
        ...formData
      });
      setSuccess(true);
    } catch (err) {
      setError("Nepodařilo se odeslat záznam");
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
          <h1 className="text-xl font-bold text-[#18181B] mb-2">Tankování zaznamenáno</h1>
          <p className="text-[#52525B]">Děkujeme za záznam tankování.</p>
          <p className="text-sm text-[#52525B] mt-4">{vehicle.brand} {vehicle.model} ({vehicle.registration_plate})</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#F4F4F5] p-4" data-testid="public-fuel-form">
      <div className="max-w-md mx-auto">
        {/* Header */}
        <div className="bg-[#002FA7] text-white rounded-t-lg p-6 text-center">
          <GasPump size={48} weight="duotone" className="mx-auto mb-3" />
          <h1 className="text-xl font-bold">Záznam tankování</h1>
          <p className="text-sm opacity-80 mt-1">
            {vehicle.brand} {vehicle.model}
          </p>
          <p className="text-lg font-semibold mt-1">{vehicle.registration_plate}</p>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="bg-white rounded-b-lg p-6 space-y-4">
          <div>
            <Label>Datum</Label>
            <Input
              type="date"
              value={formData.date}
              onChange={(e) => setFormData({ ...formData, date: e.target.value })}
              required
            />
          </div>

          <div>
            <Label>Stav tachometru (km)</Label>
            <Input
              type="number"
              min="0"
              value={formData.odometer}
              onChange={(e) => setFormData({ ...formData, odometer: parseInt(e.target.value) || 0 })}
              required
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label>Litry</Label>
              <Input
                type="number"
                min="0"
                step="0.01"
                value={formData.liters}
                onChange={(e) => handleLitersChange(parseFloat(e.target.value) || 0)}
                required
              />
            </div>
            <div>
              <Label>Cena za litr (Kč)</Label>
              <Input
                type="number"
                min="0"
                step="0.01"
                value={formData.price_per_liter}
                onChange={(e) => handlePriceChange(parseFloat(e.target.value) || 0)}
                required
              />
            </div>
          </div>

          <div className="bg-[#FFC000] p-4 rounded-md text-center">
            <span className="text-sm">Celková cena: </span>
            <span className="text-xl font-bold">{formData.total_price.toLocaleString("cs-CZ")} Kč</span>
          </div>

          <div>
            <Label>Čerpací stanice</Label>
            <Input
              value={formData.fuel_station}
              onChange={(e) => setFormData({ ...formData, fuel_station: e.target.value })}
              placeholder="např. Shell, OMV..."
            />
          </div>

          <div>
            <Label>Poznámky</Label>
            <Input
              value={formData.notes}
              onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
              placeholder="Volitelné poznámky"
            />
          </div>

          {error && <p className="text-red-500 text-sm text-center">{error}</p>}

          <Button
            type="submit"
            className="w-full bg-[#002FA7] hover:bg-[#002480] py-6 text-lg"
            disabled={submitting || formData.liters <= 0}
          >
            {submitting ? "Odesílám..." : "Zaznamenat tankování"}
          </Button>
        </form>
      </div>
    </div>
  );
}
