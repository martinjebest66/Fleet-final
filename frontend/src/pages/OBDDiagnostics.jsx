import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { API } from "../App";
import { Engine, Thermometer, GasPump, Gauge, Lightning, Car, Warning, ArrowsClockwise } from "@phosphor-icons/react";
import { Button } from "../components/ui/button";
import { toast } from "sonner";

const OBD_DISPLAY = [
  { key: "engine_rpm", label: "Otáčky motoru", unit: "rpm", icon: Engine, color: "#002FA7", max: 8000 },
  { key: "coolant_temp", label: "Teplota chladiva", unit: "°C", icon: Thermometer, color: "#DC2626", max: 130 },
  { key: "fuel_level", label: "Stav paliva", unit: "%", icon: GasPump, color: "#16A34A", max: 100 },
  { key: "oem_fuel_level", label: "Palivo (OEM)", unit: "%", icon: GasPump, color: "#16A34A", max: 100 },
  { key: "engine_load", label: "Zátěž motoru", unit: "%", icon: Gauge, color: "#F59E0B", max: 100 },
  { key: "throttle_position", label: "Pozice škrtidla", unit: "%", icon: Gauge, color: "#8B5CF6", max: 100 },
  { key: "vehicle_speed", label: "Rychlost (OBD)", unit: "km/h", icon: Car, color: "#002FA7", max: 200 },
  { key: "battery_voltage", label: "Napětí baterie", unit: "mV", icon: Lightning, color: "#F59E0B", max: 16000 },
  { key: "ext_voltage", label: "Ext. napětí", unit: "mV", icon: Lightning, color: "#F59E0B", max: 30000 },
  { key: "intake_air_temp", label: "Teplota sání", unit: "°C", icon: Thermometer, color: "#06B6D4", max: 100 },
  { key: "fuel_rate", label: "Spotřeba", unit: "l/h", icon: GasPump, color: "#EC4899", max: 30 },
  { key: "dtc_count", label: "DTC chyby", unit: "", icon: Warning, color: "#DC2626", max: 10 },
];

function GaugeCard({ label, value, unit, icon: Icon, color, max }) {
  const pct = max > 0 ? Math.min((value / max) * 100, 100) : 0;
  const displayValue = unit === "mV" ? (value / 1000).toFixed(1) : value;
  const displayUnit = unit === "mV" ? "V" : unit;

  return (
    <div className="bg-white border border-[#E4E4E7] rounded-md p-4">
      <div className="flex items-center gap-2 mb-3">
        <Icon size={18} style={{ color }} />
        <span className="text-xs text-[#52525B] font-medium">{label}</span>
      </div>
      <p className="text-2xl font-bold text-[#18181B]">
        {displayValue} <span className="text-sm font-normal text-[#A1A1AA]">{displayUnit}</span>
      </p>
      <div className="mt-2 h-1.5 bg-[#F4F4F5] rounded-full overflow-hidden">
        <div className="h-full rounded-full transition-all duration-500" style={{ width: `${pct}%`, backgroundColor: color }} />
      </div>
    </div>
  );
}

export default function OBDDiagnostics() {
  const [obdData, setObdData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [detecting, setDetecting] = useState({});

  const fetchOBD = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/obd/vehicles`, { withCredentials: true });
      setObdData(res.data);
    } catch { /* */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchOBD(); }, [fetchOBD]);

  const handleDetectTrips = async (vehicleId) => {
    setDetecting(prev => ({ ...prev, [vehicleId]: true }));
    try {
      const res = await axios.post(`${API}/gps/detect-trips/${vehicleId}`, {}, { withCredentials: true });
      toast.success(res.data.message);
    } catch { toast.error("Detekce selhala"); }
    finally { setDetecting(prev => ({ ...prev, [vehicleId]: false })); }
  };

  if (loading) return <div className="flex items-center justify-center h-64"><div className="loading-spinner"></div></div>;

  return (
    <div className="space-y-6" data-testid="obd-diagnostics-page">
      <div>
        <h1 className="font-['Manrope'] text-2xl lg:text-3xl font-bold text-[#18181B] tracking-tight">OBD-II Diagnostika</h1>
        <p className="text-[#52525B] mt-1">Live data z palubních počítačů vozidel</p>
      </div>

      {obdData.length > 0 ? (
        <div className="space-y-8">
          {obdData.map(vehicle => {
            const data = vehicle.data || {};
            const hasData = Object.keys(data).length > 0;

            return (
              <div key={vehicle.vehicle_id} className="space-y-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <Car size={24} className="text-[#002FA7]" />
                    <div>
                      <h2 className="font-semibold text-lg text-[#18181B]">{vehicle.vehicle_info || vehicle.vehicle_id}</h2>
                      <p className="text-xs text-[#A1A1AA]">
                        {vehicle.timestamp ? `Poslední aktualizace: ${new Date(vehicle.timestamp).toLocaleString("cs-CZ")}` : "Žádná data"}
                      </p>
                    </div>
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handleDetectTrips(vehicle.vehicle_id)}
                    disabled={detecting[vehicle.vehicle_id]}
                    data-testid={`detect-trips-${vehicle.vehicle_id}`}
                  >
                    <ArrowsClockwise size={16} className="mr-1" />
                    {detecting[vehicle.vehicle_id] ? "Detekuji..." : "Detekovat jízdy"}
                  </Button>
                </div>

                {hasData ? (
                  <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6 gap-3">
                    {OBD_DISPLAY.map(param => {
                      const val = data[param.key];
                      if (!val) return null;
                      const numValue = typeof val === "object" ? val.value : val;
                      return (
                        <GaugeCard
                          key={param.key}
                          label={param.label}
                          value={numValue}
                          unit={param.unit}
                          icon={param.icon}
                          color={param.color}
                          max={param.max}
                        />
                      );
                    })}
                  </div>
                ) : (
                  <div className="bg-[#F4F4F5] rounded-md p-6 text-center text-sm text-[#52525B]">
                    Čekám na OBD-II data z trackeru...
                  </div>
                )}
              </div>
            );
          })}
        </div>
      ) : (
        <div className="bg-white border border-[#E4E4E7] rounded-md p-12 text-center">
          <Engine size={48} weight="duotone" className="mx-auto text-[#A1A1AA] mb-4" />
          <h3 className="font-semibold text-[#18181B] mb-2">Žádná OBD-II data</h3>
          <p className="text-[#52525B] mb-4">Připojte Teltonika FMB003 k OBD portu vozidla a zaregistrujte tracker</p>
          <p className="text-sm text-[#A1A1AA]">Data se zobrazí automaticky po přijetí prvních záznamů z trackeru</p>
        </div>
      )}
    </div>
  );
}
