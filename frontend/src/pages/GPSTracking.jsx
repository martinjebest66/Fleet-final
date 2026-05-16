import { useState, useEffect, useCallback, useRef } from "react";
import axios from "axios";
import { API } from "../App";
import { MapPin, Download, Play, ArrowsClockwise, Check, Broadcast, Path, Car, Cpu, Plus, Trash, WifiHigh, WifiSlash, TestTube } from "@phosphor-icons/react";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "../components/ui/dialog";
import { toast } from "sonner";
import { MapContainer, TileLayer, Polyline, Marker, Popup, useMap } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import L from "leaflet";

delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon-2x.png",
  iconUrl: "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon.png",
  shadowUrl: "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png",
});

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

export default function GPSTracking() {
  const [tab, setTab] = useState("live");
  const [trips, setTrips] = useState([]);
  const [vehicles, setVehicles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [importing, setImporting] = useState(false);
  const [selectedVehicle, setSelectedVehicle] = useState("");
  const [selectedTrip, setSelectedTrip] = useState(null);

  // Live tracking state
  const [livePositions, setLivePositions] = useState([]);
  const [liveLoading, setLiveLoading] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(false);
  const intervalRef = useRef(null);

  // Device management state
  const [devices, setDevices] = useState([]);
  const [tcpStatus, setTcpStatus] = useState(null);
  const [showDeviceModal, setShowDeviceModal] = useState(false);
  const [deviceForm, setDeviceForm] = useState({ imei: "", vehicle_id: "", name: "" });
  const [testing, setTesting] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      const params = selectedVehicle && selectedVehicle !== "all" ? `?vehicle_id=${selectedVehicle}` : "";
      const [tripsRes, vehiclesRes] = await Promise.all([
        axios.get(`${API}/gps/trips${params}`, { withCredentials: true }),
        axios.get(`${API}/vehicles`, { withCredentials: true })
      ]);
      setTrips(tripsRes.data);
      setVehicles(vehiclesRes.data);
    } catch { toast.error("Nepodařilo se načíst GPS data"); }
    finally { setLoading(false); }
  }, [selectedVehicle]);

  const fetchDevices = useCallback(async () => {
    try {
      const [devRes, statusRes] = await Promise.all([
        axios.get(`${API}/gps/devices`, { withCredentials: true }),
        axios.get(`${API}/gps/tcp-status`, { withCredentials: true })
      ]);
      setDevices(devRes.data);
      setTcpStatus(statusRes.data);
    } catch { /* ignore - user may not be on devices tab */ }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);
  useEffect(() => { if (tab === "devices") fetchDevices(); }, [tab, fetchDevices]);

  const fetchLivePositions = useCallback(async () => {
    setLiveLoading(true);
    try {
      const res = await axios.get(`${API}/gps/live-positions`, { withCredentials: true });
      setLivePositions(res.data);
    } catch { toast.error("Nepodařilo se načíst live pozice"); }
    finally { setLiveLoading(false); }
  }, []);

  const simulateAndFetch = useCallback(async () => {
    try {
      await axios.post(`${API}/gps/simulate-live`, {}, { withCredentials: true });
      await fetchLivePositions();
    } catch { toast.error("Simulace selhala"); }
  }, [fetchLivePositions]);

  useEffect(() => { if (tab === "live") fetchLivePositions(); }, [tab, fetchLivePositions]);

  useEffect(() => {
    if (autoRefresh && tab === "live") {
      intervalRef.current = setInterval(simulateAndFetch, 5000);
    }
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [autoRefresh, tab, simulateAndFetch]);

  const handleImportMock = async (vehicleId) => {
    if (!vehicleId) { toast.error("Vyberte vozidlo"); return; }
    setImporting(true);
    try {
      await axios.post(`${API}/gps/import-mock?vehicle_id=${vehicleId}`, {}, { withCredentials: true });
      toast.success("GPS data importována");
      fetchData();
    } catch { toast.error("Nepodařilo se importovat data"); }
    finally { setImporting(false); }
  };

  const handleSyncToLogbook = async (tripId) => {
    try {
      await axios.post(`${API}/gps/trips/${tripId}/sync-to-logbook`, {}, { withCredentials: true });
      toast.success("Synchronizováno do knihy jízd");
      fetchData();
    } catch { toast.error("Nepodařilo se synchronizovat"); }
  };

  const handleAddDevice = async (e) => {
    e.preventDefault();
    try {
      await axios.post(`${API}/gps/devices`, deviceForm, { withCredentials: true });
      toast.success("Zařízení registrováno");
      setShowDeviceModal(false);
      setDeviceForm({ imei: "", vehicle_id: "", name: "" });
      fetchDevices();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Nepodařilo se registrovat");
    }
  };

  const handleDeleteDevice = async (deviceId) => {
    try {
      await axios.delete(`${API}/gps/devices/${deviceId}`, { withCredentials: true });
      toast.success("Zařízení odstraněno");
      fetchDevices();
    } catch { toast.error("Nepodařilo se odstranit"); }
  };

  const handleTestDevice = async (device) => {
    setTesting(true);
    try {
      const res = await axios.post(`${API}/gps/test-teltonika?imei=${device.imei}&lat=50.0755&lng=14.4378&speed=45`, {}, { withCredentials: true });
      if (res.data.success) {
        toast.success(`Test OK: ${res.data.records_acked} záznam(y) přijaty`);
        fetchDevices();
        fetchLivePositions();
      } else {
        toast.error(`Test selhal: ${res.data.error}`);
      }
    } catch { toast.error("Nepodařilo se provést test"); }
    finally { setTesting(false); }
  };

  const formatDuration = (start, end) => {
    const diff = Math.abs(new Date(end) - new Date(start));
    const hours = Math.floor(diff / 3600000);
    const minutes = Math.floor((diff % 3600000) / 60000);
    return hours > 0 ? `${hours}h ${minutes}m` : `${minutes}m`;
  };

  if (loading) return <div className="flex items-center justify-center h-64"><div className="loading-spinner"></div></div>;

  const mapCenter = selectedTrip?.route_points?.length > 0
    ? [selectedTrip.route_points[0].lat, selectedTrip.route_points[0].lng]
    : [50.0755, 14.4378];
  const routePositions = selectedTrip?.route_points?.map(p => [p.lat, p.lng]) || [];
  const validLivePositions = livePositions.filter(p => p.lat && p.lng);

  return (
    <div className="space-y-6" data-testid="gps-page">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="font-['Manrope'] text-2xl lg:text-3xl font-bold text-[#18181B] tracking-tight">GPS sledování</h1>
          <p className="text-[#52525B] mt-1">Live mapa, historie tras a správa trackerů</p>
        </div>
        <div className="flex gap-2">
          {tab === "history" && (
            <>
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
            </>
          )}
          {tab === "devices" && (
            <Button onClick={() => setShowDeviceModal(true)} className="bg-[#002FA7] hover:bg-[#002480]" data-testid="add-device-btn">
              <Plus size={20} className="mr-2" />Přidat tracker
            </Button>
          )}
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 bg-[#F4F4F5] p-1 rounded-lg w-fit">
        <button onClick={() => setTab("live")} className={`flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-all ${tab === "live" ? "bg-white text-[#18181B] shadow-sm" : "text-[#52525B] hover:text-[#18181B]"}`} data-testid="tab-live">
          <Broadcast size={18} />Live mapa
        </button>
        <button onClick={() => setTab("history")} className={`flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-all ${tab === "history" ? "bg-white text-[#18181B] shadow-sm" : "text-[#52525B] hover:text-[#18181B]"}`} data-testid="tab-history">
          <Path size={18} />Historie tras
        </button>
        <button onClick={() => setTab("devices")} className={`flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-all ${tab === "devices" ? "bg-white text-[#18181B] shadow-sm" : "text-[#52525B] hover:text-[#18181B]"}`} data-testid="tab-devices">
          <Cpu size={18} />Trackery
        </button>
      </div>

      {/* ═══ LIVE MAP TAB ═══ */}
      {tab === "live" && (
        <div className="space-y-4">
          <div className="flex items-center gap-3 flex-wrap">
            <Button onClick={simulateAndFetch} variant="outline" disabled={liveLoading} data-testid="simulate-btn">
              <Play size={18} className="mr-2" />Simulovat pohyb
            </Button>
            <Button onClick={() => setAutoRefresh(!autoRefresh)} variant={autoRefresh ? "default" : "outline"} className={autoRefresh ? "bg-[#16A34A] hover:bg-[#15803D]" : ""} data-testid="auto-refresh-btn">
              <Broadcast size={18} className="mr-2" />{autoRefresh ? "Auto-refresh ON (5s)" : "Auto-refresh OFF"}
            </Button>
            {liveLoading && <div className="loading-spinner w-5 h-5"></div>}
            <span className="text-sm text-[#52525B]">{validLivePositions.length} vozidel na mapě</span>
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
            </div>
            <div className="lg:col-span-3">
              <div className="bg-white border border-[#E4E4E7] rounded-md overflow-hidden" style={{ height: "600px" }}>
                <MapContainer center={[50.0755, 14.4378]} zoom={12} style={{ height: "100%", width: "100%" }} scrollWheelZoom={true}>
                  <TileLayer attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
                  {validLivePositions.length > 0 && <FitBounds positions={validLivePositions} />}
                  {validLivePositions.map(pos => (
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
      )}

      {/* ═══ HISTORY TAB ═══ */}
      {tab === "history" && (
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
                      {trip.synced_to_logbook ? (
                        <span className="badge badge-success text-xs"><Check size={12} className="mr-1" />Sync</span>
                      ) : (
                        <Button size="sm" variant="outline" onClick={(e) => { e.stopPropagation(); handleSyncToLogbook(trip.trip_id); }} className="text-xs h-7"><ArrowsClockwise size={12} className="mr-1" />Sync</Button>
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
      )}

      {/* ═══ DEVICES TAB ═══ */}
      {tab === "devices" && (
        <div className="space-y-6">
          {/* TCP Server Status */}
          {tcpStatus && (
            <div className="bg-white border border-[#E4E4E7] rounded-md p-6">
              <div className="flex items-center justify-between mb-4">
                <h3 className="font-semibold text-[#18181B] flex items-center gap-2">
                  <Cpu size={20} className="text-[#002FA7]" />
                  Teltonika TCP Server
                </h3>
                <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-sm font-medium ${tcpStatus.running ? "bg-green-50 text-green-700" : "bg-red-50 text-red-700"}`}>
                  {tcpStatus.running ? <WifiHigh size={16} /> : <WifiSlash size={16} />}
                  {tcpStatus.running ? "Aktivní" : "Neaktivní"}
                </div>
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
                <div>
                  <p className="text-[#52525B]">Adresa</p>
                  <p className="font-medium font-mono text-[#18181B]">{tcpStatus.host}:{tcpStatus.port}</p>
                </div>
                <div>
                  <p className="text-[#52525B]">Aktivní spojení</p>
                  <p className="font-medium text-[#18181B]">{tcpStatus.active_connections}</p>
                </div>
                <div>
                  <p className="text-[#52525B]">Celkem záznamů</p>
                  <p className="font-medium text-[#18181B]">{tcpStatus.total_records_received}</p>
                </div>
                <div>
                  <p className="text-[#52525B]">Protokol</p>
                  <p className="font-medium text-[#18181B]">Codec 8 / 8 Extended</p>
                </div>
              </div>
              <div className="mt-4 p-3 bg-[#F4F4F5] rounded-md text-xs text-[#52525B]">
                Nastavte v Teltonika Configuratoru: Server IP = <span className="font-mono font-medium text-[#18181B]">vaše_veřejná_IP</span>, Port = <span className="font-mono font-medium text-[#18181B]">{tcpStatus.port}</span>, Protokol = <span className="font-mono font-medium text-[#18181B]">TCP</span>, Codec = <span className="font-mono font-medium text-[#18181B]">Codec 8 Extended</span>
              </div>
            </div>
          )}

          {/* Device List */}
          <div>
            <h3 className="font-semibold text-[#18181B] mb-4">Registrovaná zařízení ({devices.length})</h3>
            {devices.length > 0 ? (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {devices.map(device => (
                  <div key={device.device_id} className="bg-white border border-[#E4E4E7] rounded-md p-5" data-testid={`device-${device.device_id}`}>
                    <div className="flex items-center justify-between mb-3">
                      <div className="flex items-center gap-2">
                        <Cpu size={20} className="text-[#002FA7]" />
                        <span className="font-semibold text-[#18181B]">{device.name}</span>
                      </div>
                      <div className={`w-2.5 h-2.5 rounded-full ${device.status === "online" ? "bg-[#16A34A] animate-pulse" : "bg-[#A1A1AA]"}`} />
                    </div>
                    <div className="space-y-2 text-sm">
                      <div className="flex justify-between">
                        <span className="text-[#52525B]">IMEI</span>
                        <span className="font-mono text-[#18181B]">{device.imei}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-[#52525B]">Vozidlo</span>
                        <span className="text-[#18181B]">{device.vehicle_info || "-"}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-[#52525B]">Stav</span>
                        <span className={device.status === "online" ? "text-green-600 font-medium" : "text-[#A1A1AA]"}>{device.status === "online" ? "Online" : "Offline"}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-[#52525B]">Poslední spojení</span>
                        <span className="text-[#18181B]">{device.last_seen ? new Date(device.last_seen).toLocaleString("cs-CZ") : "-"}</span>
                      </div>
                    </div>
                    <div className="flex gap-2 mt-4 pt-3 border-t border-[#E4E4E7]">
                      <Button variant="outline" size="sm" onClick={() => handleTestDevice(device)} disabled={testing} className="flex-1" data-testid={`test-device-${device.device_id}`}>
                        <TestTube size={16} className="mr-1" />{testing ? "..." : "Test"}
                      </Button>
                      <Button variant="outline" size="sm" onClick={() => handleDeleteDevice(device.device_id)} className="text-[#991B1B] hover:bg-red-50" data-testid={`delete-device-${device.device_id}`}>
                        <Trash size={16} />
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="bg-white border border-[#E4E4E7] rounded-md p-12 text-center">
                <Cpu size={48} weight="duotone" className="mx-auto text-[#A1A1AA] mb-4" />
                <h3 className="font-semibold text-[#18181B] mb-2">Žádné trackery</h3>
                <p className="text-[#52525B] mb-4">Registrujte GPS tracker a přiřaďte ho k vozidlu</p>
                <Button onClick={() => setShowDeviceModal(true)} className="bg-[#002FA7] hover:bg-[#002480]">
                  <Plus size={20} className="mr-2" />Přidat tracker
                </Button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ═══ ADD DEVICE MODAL ═══ */}
      <Dialog open={showDeviceModal} onOpenChange={setShowDeviceModal}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="font-['Manrope']">Registrace GPS trackeru</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleAddDevice} className="space-y-4">
            <div>
              <Label htmlFor="imei">IMEI číslo *</Label>
              <Input id="imei" value={deviceForm.imei} onChange={(e) => setDeviceForm({ ...deviceForm, imei: e.target.value })} placeholder="352625090000001" required className="font-mono" data-testid="device-imei-input" />
              <p className="text-xs text-[#A1A1AA] mt-1">15místný kód na štítku trackeru</p>
            </div>
            <div>
              <Label>Vozidlo *</Label>
              <Select value={deviceForm.vehicle_id} onValueChange={(v) => setDeviceForm({ ...deviceForm, vehicle_id: v })}>
                <SelectTrigger data-testid="device-vehicle-select"><SelectValue placeholder="Vyberte vozidlo" /></SelectTrigger>
                <SelectContent>
                  {vehicles.map(v => <SelectItem key={v.vehicle_id} value={v.vehicle_id}>{v.brand} {v.model} ({v.registration_plate})</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label htmlFor="device-name">Název (volitelné)</Label>
              <Input id="device-name" value={deviceForm.name} onChange={(e) => setDeviceForm({ ...deviceForm, name: e.target.value })} placeholder="FMB003 - vůz 1" data-testid="device-name-input" />
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setShowDeviceModal(false)}>Zrušit</Button>
              <Button type="submit" className="bg-[#002FA7] hover:bg-[#002480]" disabled={!deviceForm.imei || !deviceForm.vehicle_id} data-testid="device-submit-btn">Registrovat</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
