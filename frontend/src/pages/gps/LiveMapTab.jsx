import { MapContainer, TileLayer, Marker, Popup, useMap } from "react-leaflet";
import { useEffect } from "react";
import L from "leaflet";
import { Car, Broadcast, Play, ArrowsClockwise } from "@phosphor-icons/react";
import { Button } from "../../components/ui/button";

const VEHICLE_ICON_ACTIVE = new L.DivIcon({
  html: `<div style="background:#16A34A;width:32px;height:32px;border-radius:50%;display:flex;align-items:center;justify-content:center;border:3px solid white;box-shadow:0 2px 6px rgba(0,0,0,0.3)"><svg width="16" height="16" viewBox="0 0 256 256" fill="white"><path d="M240,112H229.2L201.42,49.5A16,16,0,0,0,186.8,40H69.2a16,16,0,0,0-14.62,9.5L26.8,112H16a8,8,0,0,0,0,16h8v80a16,16,0,0,0,16,16H64a16,16,0,0,0,16-16V192h96v16a16,16,0,0,0,16,16h24a16,16,0,0,0,16-16V128h8a8,8,0,0,0,0-16ZM69.2,56H186.8l24.89,56H44.31ZM80,160H56a8,8,0,0,1,0-16H80a8,8,0,0,1,0,16Zm120,0H176a8,8,0,0,1,0-16h24a8,8,0,0,1,0,16Z"/></svg></div>`,
  className: "",
  iconSize: [32, 32],
  iconAnchor: [16, 16],
});

const VEHICLE_ICON_INACTIVE = new L.DivIcon({
  html: `<div style="background:#A1A1AA;width:32px;height:32px;border-radius:50%;display:flex;align-items:center;justify-content:center;border:3px solid white;box-shadow:0 2px 6px rgba(0,0,0,0.3)"><svg width="16" height="16" viewBox="0 0 256 256" fill="white"><path d="M240,112H229.2L201.42,49.5A16,16,0,0,0,186.8,40H69.2a16,16,0,0,0-14.62,9.5L26.8,112H16a8,8,0,0,0,0,16h8v80a16,16,0,0,0,16,16H64a16,16,0,0,0,16-16V192h96v16a16,16,0,0,0,16,16h24a16,16,0,0,0,16-16V128h8a8,8,0,0,0,0-16ZM69.2,56H186.8l24.89,56H44.31ZM80,160H56a8,8,0,0,1,0-16H80a8,8,0,0,1,0,16Zm120,0H176a8,8,0,0,1,0-16h24a8,8,0,0,1,0,16Z"/></svg></div>`,
  className: "",
  iconSize: [32, 32],
  iconAnchor: [16, 16],
});

function FitBounds({ positions }) {
  const map = useMap();
  useEffect(() => {
    if (positions.length > 0) {
      const bounds = L.latLngBounds(positions.map(p => [p.lat, p.lng]));
      map.fitBounds(bounds, { padding: [40, 40], maxZoom: 14 });
    }
  }, [map, positions]);
  return null;
}

export function LiveMapTab({ livePositions, liveLoading, autoRefresh, setAutoRefresh, simulateAndFetch, refresh, allowMockData }) {
  const validPositions = livePositions.filter(p => p.lat && p.lng);

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3 flex-wrap">
        <Button onClick={refresh} variant="outline" disabled={liveLoading} data-testid="refresh-positions-btn">
          <ArrowsClockwise size={18} className="mr-2" />Obnovit pozice
        </Button>
        <Button onClick={() => setAutoRefresh(!autoRefresh)} variant={autoRefresh ? "default" : "outline"} className={autoRefresh ? "bg-[#16A34A] hover:bg-[#15803D]" : ""} data-testid="auto-refresh-btn">
          <Broadcast size={18} className="mr-2" />{autoRefresh ? "Auto-refresh ON (15s)" : "Auto-refresh OFF"}
        </Button>
        {/* Demo generator; disabled outside development because it writes into
            the same collection as real tracker data. */}
        {allowMockData && (
          <Button onClick={simulateAndFetch} variant="outline" disabled={liveLoading} data-testid="simulate-btn">
            <Play size={18} className="mr-2" />Simulovat pohyb
          </Button>
        )}
        {liveLoading && <div className="loading-spinner w-5 h-5"></div>}
        <span className="text-sm text-[#52525B]">{validPositions.length} vozidel na mapě</span>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
        <div className="space-y-2 max-h-[600px] overflow-y-auto">
          {livePositions.map(pos => (
            <div key={pos.vehicle_id} className="bg-white border border-[#E4E4E7] rounded-md p-3" data-testid={`live-vehicle-${pos.vehicle_id}`}>
              <div className="flex items-center gap-2 mb-1">
                <div className={`w-2.5 h-2.5 rounded-full ${pos.ignition ? "bg-[#16A34A] animate-pulse" : "bg-[#A1A1AA]"}`} />
                <span className="font-medium text-sm text-[#18181B] truncate">{pos.vehicle_info}</span>
              </div>
              {pos.lat ? (
                <div className="text-xs text-[#52525B] space-y-0.5">
                  <p>{pos.speed} km/h {pos.ignition ? "- v pohybu" : "- stojí"}</p>
                  <p className="text-[10px] text-[#A1A1AA]">{pos.timestamp ? new Date(pos.timestamp).toLocaleString("cs-CZ") : "-"}</p>
                </div>
              ) : (
                <p className="text-xs text-[#A1A1AA]">Žádná pozice</p>
              )}
            </div>
          ))}
          {livePositions.length === 0 && (
            <div className="bg-white border border-[#E4E4E7] rounded-md p-6 text-center">
              <Car size={32} className="mx-auto text-[#A1A1AA] mb-2" />
              <p className="text-sm text-[#52525B]">Žádná vozidla</p>
            </div>
          )}
          {livePositions.length > 0 && validPositions.length === 0 && (
            <div className="bg-amber-50 border border-amber-200 rounded-md p-3 text-xs text-amber-800">
              Vozidla zatím nemají žádnou GPS pozici. Zkontrolujte, že je tracker
              zaregistrovaný v záložce <strong>Zařízení</strong> a že posílá data
              na port 5027.
            </div>
          )}
        </div>
        <div className="lg:col-span-3">
          <div className="bg-white border border-[#E4E4E7] rounded-md overflow-hidden" style={{ height: "600px" }}>
            <MapContainer center={[50.0755, 14.4378]} zoom={12} style={{ height: "100%", width: "100%" }} scrollWheelZoom={true}>
              <TileLayer attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
              {validPositions.length > 0 && <FitBounds positions={validPositions} />}
              {validPositions.map(pos => (
                <Marker key={pos.vehicle_id} position={[pos.lat, pos.lng]} icon={pos.ignition ? VEHICLE_ICON_ACTIVE : VEHICLE_ICON_INACTIVE}>
                  <Popup>
                    <div className="text-sm"><p className="font-semibold">{pos.vehicle_info}</p><p>{pos.speed} km/h {pos.ignition ? "- v pohybu" : "- stojí"}</p><p className="text-xs text-gray-500">{pos.timestamp ? new Date(pos.timestamp).toLocaleString("cs-CZ") : ""}</p></div>
                  </Popup>
                </Marker>
              ))}
            </MapContainer>
          </div>
        </div>
      </div>
    </div>
  );
}
