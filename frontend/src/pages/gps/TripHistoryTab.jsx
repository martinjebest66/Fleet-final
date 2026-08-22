import { Link } from "react-router-dom";
import { MapContainer, TileLayer, Polyline, Marker, Popup } from "react-leaflet";
import { MapPin, Download, Check, ArrowsClockwise } from "@phosphor-icons/react";
import { Button } from "../../components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../../components/ui/select";

function formatDuration(start, end) {
  const diff = Math.abs(new Date(end) - new Date(start));
  const hours = Math.floor(diff / 3600000);
  const minutes = Math.floor((diff % 3600000) / 60000);
  return hours > 0 ? `${hours}h ${minutes}m` : `${minutes}m`;
}

const SOURCE_BADGES = {
  teltonika: { label: "GPS", className: "bg-blue-100 text-blue-700" },
  ruhavik: { label: "Ruhavik", className: "bg-violet-100 text-violet-700" },
  manual: { label: "Ručně", className: "bg-zinc-100 text-zinc-700" },
  mock: { label: "Demo", className: "bg-amber-100 text-amber-700" },
};

export function TripHistoryTab({ trips, vehicles, selectedVehicle, setSelectedVehicle, selectedTrip, setSelectedTrip, selectedRoute, allowMockData, importing, handleImportMock, handleSyncToLogbook }) {
  // Route points arrive from a separate request (see GPSTracking); fall back to
  // any points already on the trip so the component works either way.
  const points = selectedRoute?.points?.length ? selectedRoute.points : (selectedTrip?.route_points || []);
  const mapCenter = points.length > 0
    ? [points[0].lat, points[0].lng]
    : [50.0755, 14.4378];
  const routePositions = points.map(p => [p.lat, p.lng]);
  const stateStart = selectedRoute?.stateStart;
  const stateEnd = selectedRoute?.stateEnd;

  const formatOdo = (state) =>
    state?.odometer_km != null
      ? `${state.odometer_km.toLocaleString("cs-CZ")} km${state.odometer_is_estimate ? " (odhad)" : ""}`
      : "—";
  const formatFuel = (state) =>
    state?.fuel_level_percent != null ? `${state.fuel_level_percent} %` : "—";

  return (
    <>
      <div className="flex gap-2 mb-4">
        <Select value={selectedVehicle} onValueChange={setSelectedVehicle}>
          <SelectTrigger className="w-48"><SelectValue placeholder="Vyberte vozidlo" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Všechna vozidla</SelectItem>
            {vehicles.map(v => <SelectItem key={v.vehicle_id} value={v.vehicle_id}>{v.brand} {v.model}</SelectItem>)}
          </SelectContent>
        </Select>
        {allowMockData && (
          <Button onClick={() => handleImportMock(selectedVehicle !== "all" ? selectedVehicle : vehicles[0]?.vehicle_id)} className="bg-[#002FA7] hover:bg-[#002480]" disabled={importing || vehicles.length === 0}>
            <Download size={20} className="mr-2" />{importing ? "Importuji..." : "Ukázková data"}
          </Button>
        )}
        <Button asChild variant="outline">
          <Link to="/ruhavik-import"><Download size={20} className="mr-2" />Import z Ruhaviku</Link>
        </Button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-1 space-y-4">
          <h3 className="font-semibold text-[#18181B]">GPS záznamy ({trips.length})</h3>
          {trips.length > 0 ? (
            <div className="space-y-2 max-h-[600px] overflow-y-auto">
              {trips.map(trip => (
                <div key={trip.trip_id} onClick={() => setSelectedTrip(trip)} className={`bg-white border rounded-md p-4 cursor-pointer transition-all ${selectedTrip?.trip_id === trip.trip_id ? "border-[#002FA7] ring-2 ring-[#002FA7]/20" : "border-[#E4E4E7] hover:border-[#A1A1AA]"}`}>
                  <div className="flex items-start justify-between mb-2">
                    <div>
                      <p className="font-medium text-[#18181B]">{new Date(trip.start_time).toLocaleDateString("cs-CZ")}</p>
                      <p className="text-sm text-[#52525B]">{new Date(trip.start_time).toLocaleTimeString("cs-CZ", { hour: "2-digit", minute: "2-digit" })} - {new Date(trip.end_time).toLocaleTimeString("cs-CZ", { hour: "2-digit", minute: "2-digit" })}</p>
                    </div>
                    <div className="flex items-center gap-1">
                    {trip.source && SOURCE_BADGES[trip.source] && (
                      <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded ${SOURCE_BADGES[trip.source].className}`}>
                        {SOURCE_BADGES[trip.source].label}
                      </span>
                    )}
                    {trip.synced_to_logbook ? (
                      <span className="badge badge-success text-xs"><Check size={12} className="mr-1" />Sync</span>
                    ) : (
                      <Button size="sm" variant="outline" onClick={(e) => { e.stopPropagation(); handleSyncToLogbook(trip.trip_id); }} className="text-xs h-7"><ArrowsClockwise size={12} className="mr-1" />Sync</Button>
                    )}
                    </div>
                  </div>
                  <div className="text-sm space-y-1">
                    <p className="text-[#52525B] truncate"><MapPin size={14} className="inline mr-1" />{trip.start_location?.address}</p>
                    <p className="text-[#52525B] truncate">→ {trip.end_location?.address}</p>
                  </div>
                  <div className="flex gap-4 mt-2 text-xs text-[#52525B]">
                    <span>{(trip.distance / 1000).toFixed(1)} km</span>
                    <span>{formatDuration(trip.start_time, trip.end_time)}</span>
                    <span>Ø {trip.avg_speed} km/h</span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="bg-white border border-[#E4E4E7] rounded-md p-8 text-center">
              <MapPin size={48} weight="duotone" className="mx-auto text-[#A1A1AA] mb-4" />
              <p className="text-[#52525B]">Žádné GPS záznamy</p>
              <p className="text-sm text-[#52525B] mt-1">Importujte data z trackeru</p>
            </div>
          )}
        </div>
        <div className="lg:col-span-2">
          <div className="bg-white border border-[#E4E4E7] rounded-md overflow-hidden" style={{ height: "600px" }}>
            {selectedTrip ? (
              <div className="relative h-full">
                <div className="absolute top-4 left-4 z-[1000] bg-white/90 backdrop-blur-sm rounded-md p-4 shadow-lg border border-[#E4E4E7]">
                  <h4 className="font-semibold text-[#18181B]">{selectedTrip.vehicle_info}</h4>
                  <p className="text-sm text-[#52525B]">{new Date(selectedTrip.start_time).toLocaleString("cs-CZ")}</p>
                  <div className="flex gap-4 mt-2 text-sm">
                    <span className="font-medium">{(selectedTrip.distance / 1000).toFixed(1)} km</span>
                    <span>Max: {selectedTrip.max_speed} km/h</span>
                  </div>
                  {(stateStart || stateEnd) && (
                    <table className="mt-3 text-xs border-t border-[#E4E4E7] pt-2 w-full"
                           data-testid="trip-state-table">
                      <thead>
                        <tr className="text-[#A1A1AA]"><th className="text-left font-normal pr-3"></th>
                          <th className="text-right font-normal pr-3">Tachometr</th>
                          <th className="text-right font-normal">Palivo</th></tr>
                      </thead>
                      <tbody>
                        <tr>
                          <td className="text-[#52525B] pr-3">Začátek</td>
                          <td className="text-right pr-3 font-medium">{formatOdo(stateStart)}</td>
                          <td className="text-right font-medium">{formatFuel(stateStart)}</td>
                        </tr>
                        <tr>
                          <td className="text-[#52525B] pr-3">Konec</td>
                          <td className="text-right pr-3 font-medium">{formatOdo(stateEnd)}</td>
                          <td className="text-right font-medium">{formatFuel(stateEnd)}</td>
                        </tr>
                      </tbody>
                    </table>
                  )}
                </div>
                <MapContainer center={mapCenter} zoom={13} style={{ height: "100%", width: "100%" }} scrollWheelZoom={true}>
                  <TileLayer attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
                  {routePositions.length > 0 && (
                    <>
                      <Polyline positions={routePositions} color="#002FA7" weight={4} />
                      <Marker position={routePositions[0]}><Popup>Start: {selectedTrip.start_location?.address}</Popup></Marker>
                      <Marker position={routePositions[routePositions.length - 1]}><Popup>Cíl: {selectedTrip.end_location?.address}</Popup></Marker>
                    </>
                  )}
                </MapContainer>
              </div>
            ) : (
              <div className="h-full flex items-center justify-center bg-[#F4F4F5]">
                <div className="text-center"><MapPin size={64} weight="duotone" className="mx-auto text-[#A1A1AA] mb-4" /><p className="text-[#52525B]">Vyberte GPS záznam pro zobrazení trasy</p></div>
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
