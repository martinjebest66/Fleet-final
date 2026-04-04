import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { API } from "../App";
import { MapPin, Download, Play, ArrowsClockwise, Check } from "@phosphor-icons/react";
import { Button } from "../components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Label } from "../components/ui/label";
import { toast } from "sonner";
import { MapContainer, TileLayer, Polyline, Marker, Popup } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import L from "leaflet";

// Fix for default markers
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon-2x.png",
  iconUrl: "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon.png",
  shadowUrl: "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png",
});

export default function GPSTracking() {
  const [trips, setTrips] = useState([]);
  const [vehicles, setVehicles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [importing, setImporting] = useState(false);
  const [selectedVehicle, setSelectedVehicle] = useState("");
  const [selectedTrip, setSelectedTrip] = useState(null);

  const fetchData = useCallback(async () => {
    try {
      const params = selectedVehicle && selectedVehicle !== "all" ? `?vehicle_id=${selectedVehicle}` : "";
      const [tripsRes, vehiclesRes] = await Promise.all([
        axios.get(`${API}/gps/trips${params}`, { withCredentials: true }),
        axios.get(`${API}/vehicles`, { withCredentials: true })
      ]);
      setTrips(tripsRes.data);
      setVehicles(vehiclesRes.data);
    } catch (error) { toast.error("Nepodařilo se načíst GPS data"); } 
    finally { setLoading(false); }
  }, [selectedVehicle]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleImportMock = async (vehicleId) => {
    if (!vehicleId) { toast.error("Vyberte vozidlo"); return; }
    setImporting(true);
    try {
      await axios.post(`${API}/gps/import-mock?vehicle_id=${vehicleId}`, {}, { withCredentials: true });
      toast.success("GPS data importována");
      fetchData();
    } catch (error) { toast.error("Nepodařilo se importovat data"); } 
    finally { setImporting(false); }
  };

  const handleSyncToLogbook = async (tripId) => {
    try {
      await axios.post(`${API}/gps/trips/${tripId}/sync-to-logbook`, {}, { withCredentials: true });
      toast.success("Synchronizováno do knihy jízd");
      fetchData();
    } catch (error) { toast.error("Nepodařilo se synchronizovat"); }
  };

  const formatDuration = (start, end) => {
    const startDate = new Date(start);
    const endDate = new Date(end);
    const diff = Math.abs(endDate - startDate);
    const hours = Math.floor(diff / 3600000);
    const minutes = Math.floor((diff % 3600000) / 60000);
    return hours > 0 ? `${hours}h ${minutes}m` : `${minutes}m`;
  };

  if (loading) return <div className="flex items-center justify-center h-64"><div className="loading-spinner"></div></div>;

  const mapCenter = selectedTrip?.route_points?.length > 0
    ? [selectedTrip.route_points[0].lat, selectedTrip.route_points[0].lng]
    : [50.0755, 14.4378]; // Praha default

  const routePositions = selectedTrip?.route_points?.map(p => [p.lat, p.lng]) || [];

  return (
    <div className="space-y-6" data-testid="gps-page">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="font-['Manrope'] text-2xl lg:text-3xl font-bold text-[#18181B] tracking-tight">GPS sledování</h1>
          <p className="text-[#52525B] mt-1">Import a vizualizace dat z Teltonika FMB003</p>
        </div>
        <div className="flex gap-2">
          <Select value={selectedVehicle} onValueChange={setSelectedVehicle}>
            <SelectTrigger className="w-48"><SelectValue placeholder="Vyberte vozidlo" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Všechna vozidla</SelectItem>
              {vehicles.map(v => <SelectItem key={v.vehicle_id} value={v.vehicle_id}>{v.brand} {v.model}</SelectItem>)}
            </SelectContent>
          </Select>
          <Button onClick={() => handleImportMock(selectedVehicle !== "all" ? selectedVehicle : vehicles[0]?.vehicle_id)} className="bg-[#002FA7] hover:bg-[#002480]" disabled={importing || vehicles.length === 0}>
            <Download size={20} className="mr-2" />{importing ? "Importuji..." : "Import GPS"}
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Trip List */}
        <div className="lg:col-span-1 space-y-4">
          <h3 className="font-semibold text-[#18181B]">GPS záznamy ({trips.length})</h3>
          {trips.length > 0 ? (
            <div className="space-y-2 max-h-[600px] overflow-y-auto">
              {trips.map(trip => (
                <div
                  key={trip.trip_id}
                  onClick={() => setSelectedTrip(trip)}
                  className={`bg-white border rounded-md p-4 cursor-pointer transition-all ${selectedTrip?.trip_id === trip.trip_id ? "border-[#002FA7] ring-2 ring-[#002FA7]/20" : "border-[#E4E4E7] hover:border-[#A1A1AA]"}`}
                >
                  <div className="flex items-start justify-between mb-2">
                    <div>
                      <p className="font-medium text-[#18181B]">{new Date(trip.start_time).toLocaleDateString("cs-CZ")}</p>
                      <p className="text-sm text-[#52525B]">{new Date(trip.start_time).toLocaleTimeString("cs-CZ", { hour: "2-digit", minute: "2-digit" })} - {new Date(trip.end_time).toLocaleTimeString("cs-CZ", { hour: "2-digit", minute: "2-digit" })}</p>
                    </div>
                    {trip.synced_to_logbook ? (
                      <span className="badge badge-success text-xs"><Check size={12} className="mr-1" />Sync</span>
                    ) : (
                      <Button size="sm" variant="outline" onClick={(e) => { e.stopPropagation(); handleSyncToLogbook(trip.trip_id); }} className="text-xs h-7">
                        <ArrowsClockwise size={12} className="mr-1" />Sync
                      </Button>
                    )}
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

        {/* Map */}
        <div className="lg:col-span-2">
          <div className="bg-white border border-[#E4E4E7] rounded-md overflow-hidden" style={{ height: "600px" }}>
            {selectedTrip ? (
              <div className="relative h-full">
                <div className="glass-overlay absolute top-4 left-4 z-[1000] rounded-md p-4">
                  <h4 className="font-semibold text-[#18181B]">{selectedTrip.vehicle_info}</h4>
                  <p className="text-sm text-[#52525B]">{new Date(selectedTrip.start_time).toLocaleString("cs-CZ")}</p>
                  <div className="flex gap-4 mt-2 text-sm">
                    <span className="font-medium">{(selectedTrip.distance / 1000).toFixed(1)} km</span>
                    <span>Max: {selectedTrip.max_speed} km/h</span>
                  </div>
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
                <div className="text-center">
                  <MapPin size={64} weight="duotone" className="mx-auto text-[#A1A1AA] mb-4" />
                  <p className="text-[#52525B]">Vyberte GPS záznam pro zobrazení trasy</p>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
